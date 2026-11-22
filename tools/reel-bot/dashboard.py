"""Local dashboard for the reel bot: http://localhost:8765

Runs as a thread inside bot.py so it can see the live queue and act on it (cancel, retry,
start, new jobs). Listens on 127.0.0.1 only. Standard library only.
"""
import json, os, re, subprocess, threading, time, urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 8765
HERE = Path(__file__).resolve().parent
bot = None                     # the bot module, set by start()
_cache = {}                    # log path -> incremental parse state
_palmier = {"t": 0, "up": False}

PHASES = ["Queued", "Download", "Analyse reference", "Find footage", "Edit in Palmier", "Export", "Caption & deliver"]


# ---------- reading jobs ----------

def _read_json(p, default=None):
    try:
        return json.loads(Path(p).read_text())
    except Exception:
        return default


def _label(name, inp):
    if name == "Bash":
        d = inp.get("description") or inp.get("command", "").split("\n")[0]
        return d[:140]
    if name in ("Read", "Write", "Edit"):
        return "%s %s" % ({"Read": "Read", "Write": "Wrote", "Edit": "Edited"}[name], Path(inp.get("file_path", "")).name)
    if name == "Skill":
        return "Loaded skill " + inp.get("skill", "")
    if name.startswith("mcp__palmier-pro__"):
        return "Palmier: " + name.split("__")[-1].replace("_", " ")
    if name in ("Glob", "Grep"):
        return "Searched " + (inp.get("pattern", "") or "")[:80]
    return name


def _phase_of(name, inp):
    s = (json.dumps(inp) if not isinstance(inp, str) else inp).lower()
    if name in ("Write", "Edit") and inp.get("file_path", "").endswith("result.json"):
        return 6
    if re.search(r"(^|[\s/;&])finalize\s", s) or name.endswith("export_project") or name.endswith("manage_exports"):
        return 5
    if name.startswith("mcp__palmier-pro__") and not name.endswith(("inspect_media", "get_media", "import_media", "search_media", "manage_project")):
        return 4
    if any(k in s for k in ("photos", "osxphotos", "raw footage", "footage", "photokit")) or name.endswith(("inspect_media", "import_media", "search_media")):
        return 3
    if "analyze-reel" in s or "analysis/" in s:
        return 2
    return 0


def parse_log(path):
    """Incrementally parse a claude stream-json log."""
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError:
        return None
    st = _cache.get(str(path))
    if st is None or size < st["off"]:
        st = _cache[str(path)] = {"off": 0, "steps": [], "phase": 0, "cost": None, "limit": None,
                                  "error": None, "final": None, "rate": None}
    if size > st["off"]:
        with open(path, "rb") as f:
            f.seek(st["off"])
            data = f.read()
        cut = data.rfind(b"\n") + 1      # only whole lines
        st["off"] += cut
        for line in data[:cut].splitlines():
            try:
                o = json.loads(line)
            except Exception:
                continue
            t = o.get("type")
            ts = o.get("timestamp")
            if t == "assistant":
                for c in o.get("message", {}).get("content", []):
                    if c.get("type") == "tool_use":
                        inp = c.get("input") or {}
                        st["steps"].append({"k": "tool", "tool": c["name"], "text": _label(c["name"], inp), "t": ts})
                        st["phase"] = max(st["phase"], _phase_of(c["name"], inp))
                    elif c.get("type") == "text" and c.get("text", "").strip():
                        st["steps"].append({"k": "say", "text": c["text"].strip()[:600], "t": ts})
                if o.get("error"):
                    st["error"] = o.get("api_error") or o.get("error")
            elif t == "rate_limit_event":
                st["rate"] = o.get("rate_limit_info")
            elif t == "result" or "total_cost_usd" in o:
                st["cost"] = o.get("total_cost_usd")
                st["final"] = (o.get("result") or "")[:3000]
        if len(st["steps"]) > 400:
            st["steps"] = st["steps"][-400:]
    return st


def job_info(d, live, full=False):
    req = _read_json(d / "request.json", {}) or {}
    res = _read_json(d / "result.json")
    status = _read_json(d / "status.json")
    lg = parse_log(d / "claude.log") if (d / "claude.log").exists() else None
    name = d.name
    if name == live["current"]:
        state = "running"
    elif name in live["queue"]:
        state = "queued"
    elif status:
        state = status.get("state", "?")
        if state in ("running", "building", "downloading", "queued", "delivering"):
            state = "stopped"          # bot restarted mid-job
    elif res:
        state = "done"
    elif lg and (lg["error"] == "usage_limit_reached" or (lg["rate"] or {}).get("status") == "rejected"):
        state = "limit"
    else:
        state = "failed"
    sub = (status or {}).get("state") if state == "running" else None
    phase = 0
    if lg:
        phase = max(1, lg["phase"]) if lg["steps"] else 1
    if sub == "downloading":
        phase = 1
    if state == "done":
        phase = len(PHASES)
    outs = sorted(str(p.relative_to(d)) for p in (d / "output").glob("*.mp4") if not p.name.endswith("_tg.mp4")) if (d / "output").exists() else []
    hist = (status or {}).get("history", [])
    info = {
        "id": name, "code": req.get("code", ""), "link": req.get("link", ""),
        "source": req.get("source", "telegram"), "who": req.get("who", "you"), "kind": "idea" if not req.get("link") else "reel",
        "requirements": req.get("requirements", ""), "versions": req.get("versions"),
        "created": req.get("created"), "state": state, "sub": sub, "note": (status or {}).get("note", ""),
        "phase": phase, "phases": PHASES, "cost": lg and lg["cost"], "steps_n": len(lg["steps"]) if lg else 0,
        "last": next((s["text"] for s in reversed(lg["steps"])), "") if lg else "",
        "outputs": outs, "updated": hist[-1]["t"] if hist else None,
        "titles": [v.get("title", "") for v in (res or {}).get("versions", [])],
    }
    if full:
        info.update(result=res, history=hist, steps=(lg["steps"] if lg else [])[-250:],
                    final=lg and lg["final"], refs=sorted(p.name for p in (d / "reference").glob("*.mp4")) if (d / "reference").exists() else [])
    return info


def live_state():
    with bot.lock:
        cur = bot.current["job"]
        q = [p.name for p in bot.queue]
        pend = []
        for chat_id, p in bot.pending.items():
            x = {k: v for k, v in p.items() if k != "t"}
            x.update(chat=chat_id, who=bot.who(chat_id),
                     starts_in=max(0, int(bot.WAIT_FOR_REQS - (time.time() - p["t"]))))
            pend.append(x)
    return {"current": cur.name if cur else None, "queue": q, "pending": pend}


def palmier():
    if time.time() - _palmier["t"] > 10:
        try:
            _palmier["up"] = bot.palmier_up()
        except Exception:
            _palmier["up"] = False
        _palmier["t"] = time.time()
    return _palmier["up"]


def events(n=80):
    p = bot.JOBS / "_events.jsonl"
    if not p.exists():
        return []
    lines = p.read_text(errors="ignore").splitlines()[-n:]
    out = []
    for l in reversed(lines):
        try:
            out.append(json.loads(l))
        except Exception:
            pass
    return out


def state():
    live = live_state()
    jobs = sorted([p for p in bot.JOBS.glob("*") if p.is_dir() and not p.name.startswith("_")], reverse=True)
    infos = [job_info(d, live) for d in jobs]
    newest_rate = None
    for d in jobs:            # newest log with a rate-limit event
        st = _cache.get(str(d / "claude.log"))
        if st and st.get("rate"):
            newest_rate = dict(st["rate"])
            if newest_rate.get("resetsAt") and newest_rate["resetsAt"] < time.time():
                newest_rate["status"] = "allowed"     # the limit window has reset since
            break
    gl = [{"id": k, "name": v.get("name"), "status": v.get("status"), "since": v.get("since")}
          for k, v in bot.guests().items()]
    return {"live": live, "jobs": infos, "guests": gl, "palmier": palmier(), "rate": newest_rate,
            "bot_started": bot.STARTED, "now": datetime.now().isoformat(), "events": events()}


# ---------- actions ----------

def _job(name):
    d = (bot.JOBS / name).resolve()
    if d.parent != bot.JOBS.resolve() or not d.is_dir():
        raise ValueError("no such job")
    return d


def action(a):
    kind = a.get("action")
    if kind == "cancel":
        return "Cancelling…" if bot.cancel_current() else "Nothing is running."
    if kind == "go":
        chat_id = a.get("chat")
        if chat_id not in bot.pending:
            return "No link is waiting."
        bot.start_pending(chat_id, "started from the dashboard")
        return "Started." if chat_id == bot.cfg.get("chat_id") else "Sent for your approval."
    if kind in ("approve", "decline"):
        d = _job(a["job"])
        return bot.approve(d, "dashboard") if kind == "approve" else bot.decline(d, "dashboard")
    if kind in ("allow", "block"):
        return bot.set_guest(str(a["guest"]), "allowed" if kind == "allow" else "blocked")
    if kind == "retry":
        d = _job(a["job"])
        with bot.lock:
            if d in bot.queue or bot.current["job"] == d:
                return "Already queued or running."
            bot.queue.append(d)
        bot.set_status(d, "queued", "retry from dashboard")
        bot.ev("dashboard", "retry " + d.name)
        bot.say("🖥️ Dashboard: re-queued %s" % d.name)
        return "Re-queued."
    if kind == "unqueue":
        d = _job(a["job"])
        with bot.lock:
            if d not in bot.queue:
                return "Not in the queue."
            bot.queue.remove(d)
        bot.set_status(d, "cancelled", "removed from queue on dashboard")
        bot.ev("dashboard", "removed from queue " + d.name)
        return "Removed from queue."
    if kind == "open":
        d = _job(a["job"])
        sub = d / a.get("sub", "") if a.get("sub") else d
        subprocess.run(["open", str(sub if sub.exists() else d)])
        return "Opened in Finder."
    if kind == "new":
        text = (a.get("text") or "").strip()
        link = (a.get("link") or "").strip()
        v = a.get("versions")
        if v in ("1", "2"):
            text += "\n%s version%s" % (v, "" if v == "1" else "s")
        if link:
            m = bot.IG_RE.search(link)
            if not m:
                return "That doesn't look like an Instagram reel link."
            d = bot.new_job("https://www.instagram.com/reel/%s/" % m.group(1), m.group(1), text, source="dashboard")
        else:
            if not text.strip():
                return "Write an idea or paste a link."
            d = bot.new_job("", "idea", text, source="dashboard")
        with bot.lock:
            bot.queue.append(d)
        bot.ev("dashboard", "new job %s: %s" % (d.name, (link + " " + text).strip()[:200]))
        bot.say("🖥️ Dashboard queued %s\n%s" % (d.name, (link + "\n" + text).strip()[:500]))
        return "Queued %s" % d.name
    return "Unknown action."


# ---------- HTTP ----------

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, default=str).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            if u.path == "/":
                return self._send(200, (HERE / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/state":
                return self._send(200, state())
            if u.path == "/api/job":
                return self._send(200, job_info(_job(q["id"][0]), live_state(), full=True))
            if u.path == "/file":
                return self._file(_job(q["job"][0]), q["f"][0])
        except Exception as e:
            return self._send(400, {"error": str(e)})
        self._send(404, {"error": "not found"})

    def _file(self, d, rel):
        f = (d / rel).resolve()
        if d.resolve() not in f.parents or not f.is_file():
            return self._send(404, {"error": "not found"})
        size = f.stat().st_size
        ctype = {".mp4": "video/mp4", ".jpg": "image/jpeg", ".png": "image/png"}.get(f.suffix.lower(), "application/octet-stream")
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        m = re.match(r"bytes=(\d*)-(\d*)", rng or "")
        if m:
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            elif m.group(2):
                start = size - int(m.group(2))
            end = min(end, size - 1)
            self.send_response(206)
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        try:
            with open(f, "rb") as fh:
                fh.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = fh.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        # The custom header blocks other websites from posting here (no CORS preflight answered).
        if self.headers.get("X-Reel-Bot") != "1":
            return self._send(403, {"error": "forbidden"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            a = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/action":
                return self._send(200, {"msg": action(a)})
        except Exception as e:
            return self._send(400, {"msg": "Error: %s" % e})
        self._send(404, {"error": "not found"})


def start(bot_module):
    global bot
    bot = bot_module
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    except OSError as e:
        bot.log("dashboard not started:", e)
        return
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    bot.log("dashboard on http://localhost:%d" % PORT)
