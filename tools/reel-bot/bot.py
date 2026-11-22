#!/usr/bin/python3
"""Reel bot: share an Instagram reel on Telegram, your Mac builds it with Claude Code.

Share an Instagram reel to the bot on Telegram, add your requirements, and it builds the reel
on this Mac with Claude Code + palmier-pro, then sends the videos back with caption and
hashtags.

Standard library only. Config is in ~/.config/reel-bot/config.json:
{"token": "...", "chat_id": null, "pair_code": "1234"}
"""
import json, os, re, signal, subprocess, sys, threading, time, uuid, urllib.request, urllib.parse
from datetime import datetime
from pathlib import Path

HOME = Path.home()
REELS = Path(os.environ.get("REELS_HOME", Path(__file__).resolve().parents[2]))  # workspace root (repo folder by default)
JOBS = REELS / "Bot Jobs"
TOOLS = REELS / "tools"
BOT_DIR = TOOLS / "reel-bot"
CFG_PATH = HOME / ".config" / "reel-bot" / "config.json"
CLAUDE = str(HOME / ".local" / "bin" / "claude")
PATH_ENV = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:" + str(HOME / ".local" / "bin")
IG_RE = re.compile(r"https?://(?:www\.)?instagram\.com/(?:reel|reels|p)/([A-Za-z0-9_-]+)[^\s]*")
WAIT_FOR_REQS = 180       # seconds to wait for requirements after a link
JOB_TIMEOUT = 2 * 3600    # hard stop for one build
TG_LIMIT = 49 * 1024 * 1024

cfg = json.loads(CFG_PATH.read_text())
API = "https://api.telegram.org/bot%s/" % cfg["token"]
lock = threading.Lock()
pending = {}              # chat_id -> the link waiting for requirements
queue = []                # job dirs waiting to run
current = {"job": None, "proc": None, "cancelled": False}
STARTED = datetime.now().isoformat()
CANCEL_KB = json.dumps({"inline_keyboard": [[{"text": "🛑 Cancel this build", "callback_data": "cancel"}]]})


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def ev(kind, text, **extra):
    """Append to the activity feed the dashboard shows."""
    try:
        with open(JOBS / "_events.jsonl", "a") as f:
            f.write(json.dumps(dict(t=datetime.now().isoformat(timespec="seconds"), kind=kind, text=text[:1500], **extra), ensure_ascii=False) + "\n")
    except Exception:
        pass


def set_status(job, state, note=""):
    p = job / "status.json"
    try:
        s = json.loads(p.read_text())
    except Exception:
        s = {"history": []}
    t = datetime.now().isoformat(timespec="seconds")
    s.update(state=state, note=note, updated=t)
    s["history"].append({"state": state, "note": note, "t": t})
    p.write_text(json.dumps(s, indent=2, ensure_ascii=False))
    ev("job", "%s → %s%s" % (job.name, state, (": " + note) if note else ""), job=job.name)


def save_cfg():
    CFG_PATH.write_text(json.dumps(cfg, indent=2))
    os.chmod(CFG_PATH, 0o600)


def tg(method, data=None, files=None, timeout=60):
    url = API + method
    if files:
        boundary = uuid.uuid4().hex
        body = b""
        for k, v in (data or {}).items():
            body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (boundary, k, v)).encode()
        for k, path in files.items():
            body += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\nContent-Type: application/octet-stream\r\n\r\n" % (boundary, k, Path(path).name)).encode()
            body += Path(path).read_bytes() + b"\r\n"
        body += ("--%s--\r\n" % boundary).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    else:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(data or {}).encode())
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def send(chat_id, text, **kw):
    if not chat_id:
        return
    try:
        tg("sendMessage", dict(chat_id=chat_id, text=text[:4000], **kw))
    except Exception as e:
        log("send failed", e)


def say(text, **kw):
    """Message the owner."""
    send(cfg.get("chat_id"), text, **kw)


def guests():
    return cfg.setdefault("guests", {})


def who(chat_id):
    if chat_id == cfg.get("chat_id"):
        return "you"
    return guests().get(str(chat_id), {}).get("name", str(chat_id))


def job_req(job):
    try:
        return json.loads((job / "request.json").read_text())
    except Exception:
        return {}


def jsay(job, text, cc=True, **kw):
    """Message whoever asked for this job. For a friend's job, copy key updates to the owner."""
    to = job_req(job).get("chat_id") or cfg.get("chat_id")
    send(to, text, **kw)
    if to != cfg.get("chat_id") and cc:
        say("[%s] %s" % (who(to), text), **kw)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "PATH": PATH_ENV}, **kw)


def palmier_up():
    r = run(["curl", "-s", "-m", "3", "-o", "/dev/null", "-w", "%{http_code}", "-X", "POST",
             "http://127.0.0.1:19789/mcp", "-H", "content-type: application/json", "-d", "{}"])
    return r.stdout.strip() not in ("", "000")


def ensure_palmier():
    if palmier_up():
        return True
    run(["open", "-g", "-j", "-a", "PalmierPro"])  # background + hidden
    for _ in range(30):
        time.sleep(3)
        if palmier_up():
            time.sleep(5)
            return True
    return False


# ---------- jobs ----------

def new_job(link, code, reqs, source="telegram", chat_id=None, state="queued"):
    d = JOBS / ("%s_%s" % (datetime.now().strftime("%Y-%m-%d_%H%M"), code))
    n = 2
    while d.exists():                 # two requests in the same minute
        d = JOBS / ("%s_%s-%d" % (datetime.now().strftime("%Y-%m-%d_%H%M"), code, n))
        n += 1
    (d / "reference").mkdir(parents=True, exist_ok=True)
    (d / "output").mkdir(exist_ok=True)
    versions = 2
    m = re.search(r"\b([12])\s*(?:version|versions|ver|v)\b|\b(one|two|single)\s+version", reqs, re.I)
    if m:
        versions = 1 if (m.group(1) == "1" or (m.group(2) or "").lower() in ("one", "single")) else 2
    chat_id = chat_id or cfg.get("chat_id")
    (d / "request.json").write_text(json.dumps(
        {"link": link, "code": code, "requirements": reqs.strip() or "(none: use your judgement)",
         "versions": versions, "created": datetime.now().isoformat(), "source": source,
         "chat_id": chat_id, "who": who(chat_id)}, indent=2, ensure_ascii=False))
    set_status(d, state, "from " + (who(chat_id) if source == "guest" else source))
    return d


# ---------- approving a friend's request ----------

def approval_kb(job):
    return json.dumps({"inline_keyboard": [[{"text": "✅ Approve", "callback_data": "approve:" + job.name},
                                            {"text": "❌ Decline", "callback_data": "decline:" + job.name}]]})


def job_dir(name):
    d = (JOBS / name).resolve()
    if d.parent != JOBS.resolve() or not d.is_dir():
        return None
    return d


def job_state(job):
    try:
        return json.loads((job / "status.json").read_text()).get("state")
    except Exception:
        return None


def approve(job, by="Telegram"):
    if job_state(job) != "approval":
        return "Already handled."
    with lock:
        queue.append(job)
        pos = len(queue) + (1 if current["job"] else 0)
    set_status(job, "queued", "approved on " + by)
    req = job_req(job)
    send(req.get("chat_id"), "✅ Your request was approved. It's in the queue (position %d). I'll send the videos here when they're ready." % pos)
    say("✅ Approved %s's request. Queue position %d." % (req.get("who", "?"), pos))
    return "Approved."


def decline(job, by="Telegram"):
    if job_state(job) != "approval":
        return "Already handled."
    set_status(job, "declined", "declined on " + by)
    req = job_req(job)
    send(req.get("chat_id"), "Sorry, this one can't be built right now.")
    say("❌ Declined %s's request." % req.get("who", "?"))
    return "Declined."


def set_guest(chat_id, status):
    g = guests().get(str(chat_id))
    if not g:
        return "Unknown person."
    g["status"] = status
    save_cfg()
    ev("guest", "%s → %s" % (g["name"], status))
    if status == "allowed":
        send(chat_id, "✅ You're in! " + GUEST_HELP)
        say("✅ %s can now send requests. You'll approve each one." % g["name"])
    elif status == "blocked":
        say("🚫 %s is blocked. The bot will ignore them." % g["name"])
    return "%s %s." % (g["name"], status)


def build(job):
    req = job_req(job)
    if not req["link"]:            # /make <idea>: no reference reel
        ref = info = Path("NONE (idea build: no reference reel; build from the idea and the knowledge base)")
        jsay(job, "✅ Idea build: %d version(s). Usually 20–60 min." % req["versions"], reply_markup=CANCEL_KB)
        return run_claude(job, req, ref, info)
    set_status(job, "downloading")
    jsay(job, "⬇️ Downloading the reel…", cc=False)
    r = subprocess.run([str(TOOLS / "reel-dl"), req["link"]], capture_output=True, text=True,
                       env={**os.environ, "PATH": PATH_ENV, "REEL_DL_OUT": str(job / "reference")})
    vids = sorted((job / "reference").glob("*.mp4"))
    if not vids:
        jsay(job, "❌ Couldn't download that reel. Instagram blocked it or it's private.\n" + r.stdout[-300:])
        set_status(job, "failed", "download blocked")
        return
    ref = vids[0]
    info = ref.with_suffix(".txt")
    jsay(job, "✅ Got it (%s). Starting the edit: %d version(s). This usually takes 20–60 min; I'll message you when it's ready." % (ref.stem, req["versions"]), reply_markup=CANCEL_KB)
    run_claude(job, req, ref, info)


def run_claude(job, req, ref, info):
    if not ensure_palmier():
        jsay(job, "❌ PalmierPro didn't start on the Mac. The owner will retry it.")
        set_status(job, "failed", "PalmierPro didn't start")
        return
    scratch = Path("/private/tmp") / "reel-bot" / job.name
    scratch.mkdir(parents=True, exist_ok=True)
    prompt = (BOT_DIR / "job_prompt.md").read_text()
    for k, v in {"{JOB_DIR}": str(job), "{REF_VIDEO}": str(ref), "{REF_INFO}": str(info),
                 "{REQUIREMENTS}": req["requirements"], "{VERSIONS}": str(req["versions"]),
                 "{SCRATCH}": str(scratch)}.items():
        prompt = prompt.replace(k, v)
    cmd = [CLAUDE, "-p", prompt,
           "--permission-mode", "dontAsk",
           "--allowedTools", "Bash", "Read", "Write", "Edit", "Glob", "Grep", "Skill", "ToolSearch", "mcp__palmier-pro", "mcp__metapilot-native",
           "--disallowedTools", "mcp__palmier-pro__generate_image", "mcp__palmier-pro__generate_video",
           "mcp__palmier-pro__generate_audio", "mcp__palmier-pro__upscale_media",
           "mcp__metapilot-native__deleteProject", "mcp__metapilot-native__deleteAccountFont",
           "mcp__metapilot-native__dragSpeedPanelCurve", "mcp__metapilot-native__selectSpeedPanelPreset",
           "--add-dir", str(scratch), "--output-format", "stream-json", "--verbose"]
    with open(job / "claude.log", "w") as lf:
        current["cancelled"] = False
        p = subprocess.Popen(["caffeinate", "-i"] + cmd, cwd=str(REELS), stdout=lf, stderr=subprocess.STDOUT, start_new_session=True,
                             env={**os.environ, "PATH": PATH_ENV})
        current["proc"] = p
        set_status(job, "building")
        try:
            p.wait(timeout=JOB_TIMEOUT)
        except subprocess.TimeoutExpired:
            kill_build(p)
            jsay(job, "⏱️ The build took over 2 hours and was stopped.")
            set_status(job, "failed", "over 2 hours")
            return
        finally:
            current["proc"] = None
    if current["cancelled"]:
        jsay(job, "🛑 Build cancelled.")
        set_status(job, "cancelled")
        return
    deliver(job)


def kill_build(p):
    try:
        os.killpg(p.pid, signal.SIGTERM)   # caffeinate + claude + its ffmpeg children
        time.sleep(3)
        os.killpg(p.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def cancel_current(chat_id=None):
    """Stop the running build. A friend (chat_id given) can only stop their own."""
    if current["proc"]:
        if chat_id and chat_id != cfg.get("chat_id") and job_req(current["job"]).get("chat_id") != chat_id:
            return False
        current["cancelled"] = True
        kill_build(current["proc"])
        return True
    return False


def deliver(job):
    rp = job / "result.json"
    to = job_req(job).get("chat_id") or cfg.get("chat_id")
    if not rp.exists():
        tail = ""
        try:
            tail = (job / "claude.log").read_text(errors="ignore")[-4000:]
        except Exception:
            pass
        m = re.search(r"hit your ([^\"]*?limit[^\"]*?)(?:\"|$)", tail)
        if m or "rate_limit" in tail:
            jsay(job, "⏳ Claude usage limit reached (%s). Nothing was lost; it can be retried after the reset."
                 % (m.group(1).strip() if m else "rate limit"))
            set_status(job, "limit", m.group(1).strip() if m else "rate limit")
        else:
            jsay(job, "❌ The edit stopped without a result. It can be retried.")
            set_status(job, "failed", "no result.json")
        return
    set_status(job, "delivering")
    res = json.loads(rp.read_text())
    for i, v in enumerate(res.get("versions", []), 1):
        f = job / v["file"]
        if not f.exists():
            jsay(job, "⚠️ Version %d file missing: %s" % (i, f.name))
            continue
        out = f
        if f.stat().st_size > TG_LIMIT:   # Telegram bots can send up to 50 MB
            out = f.with_name(f.stem + "_tg.mp4")
            run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(f), "-c:v", "libx264", "-crf", "20",
                 "-preset", "slow", "-maxrate", "18M", "-bufsize", "36M", "-c:a", "aac", "-b:a", "256k",
                 "-movflags", "+faststart", str(out)])
        cap = "🎬 V%d: %s (%.1fs)\n%s" % (i, v.get("title", ""), v.get("duration_s", 0), v.get("concept", ""))
        try:
            # As a document, so Telegram doesn't re-compress it. Save to Photos from Telegram and post.
            tg("sendDocument", {"chat_id": to, "caption": cap[:1000]}, {"document": str(out)}, timeout=600)
        except Exception as e:
            jsay(job, "⚠️ Couldn't upload V%d (%s)." % (i, e))
    tags = " ".join(res.get("hashtags", []))
    kw = res.get("keywords", [])
    kw_line = (" · ".join(kw)) if isinstance(kw, list) else str(kw)
    send(to, "📋 Next message = caption + keywords + hashtags. Long-press → Copy → paste into Instagram:")
    send(to, "\n\n".join(x for x in [res.get("caption", "").strip(), kw_line, tags] if x))
    send(to, "🎵 Audio: %s\n\n📅 Posting: %s\n\n🗒️ Notes: %s" % (res.get("audio", ""), res.get("posting", ""), res.get("notes", "")))
    if to != cfg.get("chat_id"):
        say("✅ Sent %d video(s) to %s (%s). They're on the dashboard too." % (len(res.get("versions", [])), who(to), job.name))
    set_status(job, "done", "sent to " + who(to))


def worker():
    while True:
        job = None
        with lock:
            if queue and current["job"] is None:
                job = current["job"] = queue.pop(0)
        if job:
            try:
                build(job)
            except Exception as e:
                jsay(job, "❌ Job crashed: %s" % e)
                log("job error", e)
                set_status(job, "failed", "crashed: %s" % e)
            finally:
                current["job"] = None
        time.sleep(2)


def submit(chat_id, link, code, reqs, reason=""):
    """Create a job. The owner's jobs queue straight away; a friend's wait for approval."""
    if chat_id == cfg.get("chat_id"):
        job = new_job(link, code, reqs)
        with lock:
            queue.append(job)
            pos = len(queue) + (1 if current["job"] else 0)
        req = job_req(job)
        say("🚀 Queued (%s). Versions: %d. Requirements: %s%s" % (
            reason or "starting", req["versions"], req["requirements"][:300],
            "" if pos <= 1 else "\nPosition in queue: %d" % pos))
        return job
    job = new_job(link, code, reqs, source="guest", chat_id=chat_id, state="approval")
    req = job_req(job)
    send(chat_id, "📨 Sent to the owner for approval. I'll tell you when it starts.")
    say("👤 %s wants a reel built:\n%s\n\nVersions: %d\nRequirements: %s\n\nBuilds use your footage and your Claude usage."
        % (req["who"], link or "(idea, no reference reel)", req["versions"], req["requirements"][:600]),
        reply_markup=approval_kb(job))
    return job


def start_pending(chat_id, reason=""):
    with lock:
        p = pending.pop(chat_id, None)
    if p:
        submit(chat_id, p["link"], p["code"], "\n".join(p["reqs"]), reason)


def timer():
    while True:
        time.sleep(5)
        with lock:
            due = [c for c, p in pending.items() if time.time() - p["t"] > WAIT_FOR_REQS]
        for c in due:
            start_pending(c, "no more requirements, so starting")


CHAT_PROMPT = """You are the creator's reel strategist, answering them on Telegram from their Mac. Working dir is
the workspace folder. Load the reel-ideas skill and read CONTENT_LOG.md when relevant; use their real footage
(clip ids) and the knowledge base. Answer their message below. Telegram style: plain text, no markdown
tables or headings, short lines, emoji bullets fine, under 2500 characters. Read-only: never edit,
build or delete anything. If they want a reel built, tell them to share a reel link, or /make <idea>.

Their message: """
chat = {"session": None, "t": 0}


def ask(text):
    say("💭 Thinking…")
    cmd = [CLAUDE, "-p", CHAT_PROMPT + text, "--permission-mode", "dontAsk",
           "--allowedTools", "Read", "Glob", "Grep", "Skill", "--output-format", "json"]
    if chat["session"] and time.time() - chat["t"] < 1800:   # keep context for 30 min
        cmd += ["--resume", chat["session"]]
    try:
        r = subprocess.run(cmd, cwd=str(REELS), capture_output=True, text=True, timeout=600,
                           env={**os.environ, "PATH": PATH_ENV})
        out = json.loads(r.stdout)
        chat.update(session=out.get("session_id"), t=time.time())
        ans = out.get("result") or "(no answer)"
    except Exception as e:
        ans = "❌ Couldn't answer (%s)" % e
    ev("answer", ans)
    for i in range(0, len(ans), 3900):
        say(ans[i:i + 3900])


HELP = ("Share an Instagram reel here (Instagram → Share → Telegram → this bot), then type what you want, e.g.\n"
        "• \"use my trek footage, 1 version\"\n• \"aesthetic, andaman, me in it\"\n"
        "Send /go to start straight away; otherwise it starts 3 min after your last message.\n\n"
        "Or just ask anything (ideas, captions, what to shoot) and I'll answer.\n"
        "/make <idea>: build a reel from an idea, no link needed (e.g. /make i said i love hiking, beach version)\n\n"
        "/status: what's running\n/cancel: stop the current build\n/retry: rerun the last job\n"
        "/guests: who else can use the bot\n/help\n\n"
        "Friends: when someone new messages the bot, you get Allow / Block buttons. Each of their requests needs your Approve.")

GUEST_HELP = ("This is a private reel bot. Share an Instagram reel here (Instagram → Share → Telegram → this bot), "
              "then type what you want. Send /go when done (it auto-sends in 3 min).\n"
              "Or /make <idea> for a reel without a reference.\n\n"
              "Every request goes to the owner for approval first. Reels are built from the owner's footage.\n"
              "/status: your requests\n/cancel: stop your running build\n/help")


def pending_input(chat_id, text, reply):
    """Shared by owner and friends: a reel link, or requirements for the waiting link.
    Returns False if the text is neither."""
    m = IG_RE.search(text)
    if m:
        if chat_id in pending:
            start_pending(chat_id, "new link arrived, so starting the previous one")
        extra = IG_RE.sub("", text).strip()
        with lock:
            pending[chat_id] = dict(link="https://www.instagram.com/reel/%s/" % m.group(1), code=m.group(1),
                                    reqs=[extra] if extra else [], t=time.time())
        reply("👍 Reel received. Now tell me what you want: footage, mood, 1 or 2 versions, anything. "
              "Send /go when done (auto-starts in 3 min).")
        return True
    if chat_id in pending:
        with lock:
            pending[chat_id]["reqs"].append(text)
            pending[chat_id]["t"] = time.time()
        reply("📝 Noted. Add more, or /go.")
        return True
    return False


def handle_owner(text):
    owner = cfg["chat_id"]
    low = text.lower()
    if low in ("/help", "/start"):
        say(HELP)
    elif low.startswith("/make"):
        idea = text[5:].strip()
        if not idea:
            say("Usage: /make <idea + requirements>")
            return
        submit(owner, "", "idea", idea, "idea build")
    elif low == "/go":
        start_pending(owner, "you said go") if owner in pending else say("Send a reel link first.")
    elif low == "/status":
        j = current["job"]
        waiting = [d.name for d in JOBS.glob("*") if d.is_dir() and job_state(d) == "approval"]
        say(("🔧 Working on: %s%s" % (j.name, " (for %s)" % who(job_req(j).get("chat_id")) if job_req(j).get("source") == "guest" else "") if j else "💤 Idle.") +
            ("\nQueued: %d" % len(queue) if queue else "") + ("\n⏳ Waiting for requirements on a link." if pending else "") +
            ("\n👤 Waiting for your approval: %d" % len(waiting) if waiting else ""),
            **({"reply_markup": CANCEL_KB} if j else {}))
    elif low == "/cancel":
        if not cancel_current():
            say("Nothing is running.")
    elif low == "/guests":
        g = guests()
        if not g:
            say("No one else has messaged the bot.")
        for cid, x in g.items():
            kb = [[{"text": "✅ Allow", "callback_data": "allow:" + cid}]] if x["status"] != "allowed" else []
            kb += [[{"text": "🚫 Block", "callback_data": "block:" + cid}]] if x["status"] != "blocked" else []
            say("👤 %s: %s" % (x["name"], x["status"]), reply_markup=json.dumps({"inline_keyboard": kb}))
    elif low == "/retry":
        jobs = sorted([p for p in JOBS.glob("*") if p.is_dir() and not p.name.startswith("_")])
        if jobs:
            with lock:
                busy = jobs[-1] in queue or current["job"] == jobs[-1]
                if not busy:
                    queue.append(jobs[-1])
            if busy:
                say("Already queued or running: %s" % jobs[-1].name)
            else:
                set_status(jobs[-1], "queued", "retry")
                say("🔁 Re-queued %s" % jobs[-1].name)
    elif not pending_input(owner, text, say):
        threading.Thread(target=ask, args=(text,), daemon=True).start()


def handle_guest(msg, text):
    cid = msg["chat"]["id"]
    reply = lambda t, **kw: send(cid, t, **kw)
    g = guests().get(str(cid))
    if not g:
        f = msg.get("from", {})
        name = " ".join(x for x in [f.get("first_name"), f.get("last_name")] if x) or "Someone"
        if f.get("username"):
            name += " (@%s)" % f["username"]
        guests()[str(cid)] = {"name": name, "status": "asked", "since": datetime.now().isoformat(timespec="seconds")}
        save_cfg()
        ev("guest", "%s asked for access: %s" % (name, text[:200]))
        reply("👋 This is a private reel bot. I've asked the owner to let you in; you'll get a message here when they do.")
        say("👤 %s wants to use your reel bot.\nTheir message: %s" % (name, text[:300] or "(none)"),
            reply_markup=json.dumps({"inline_keyboard": [[{"text": "✅ Allow", "callback_data": "allow:%s" % cid},
                                                          {"text": "🚫 Block", "callback_data": "block:%s" % cid}]]}))
        return
    if g["status"] == "blocked":
        return
    if g["status"] != "allowed":
        reply("⏳ Still waiting for the owner to let you in.")
        return
    ev("guest", text or "(non-text message)", who=g["name"])
    low = text.lower()
    if low in ("/help", "/start"):
        reply(GUEST_HELP)
    elif low.startswith("/make"):
        idea = text[5:].strip()
        if not idea:
            reply("Usage: /make <idea + requirements>")
            return
        submit(cid, "", "idea", idea)
    elif low == "/go":
        start_pending(cid, "they said go") if cid in pending else reply("Share a reel link first.")
    elif low == "/status":
        mine = sorted((d for d in JOBS.glob("*") if d.is_dir() and job_req(d).get("chat_id") == cid), reverse=True)[:5]
        if not mine:
            reply("You have no requests yet.")
        else:
            reply("Your requests:\n" + "\n".join("• %s: %s" % (d.name, "running" if d == current["job"] else (job_state(d) or "?")) for d in mine))
    elif low == "/cancel":
        if not cancel_current(cid):
            reply("None of your builds is running.")
    elif not pending_input(cid, text, reply):
        reply("I only build reels here. Share an Instagram reel link, then tell me what you want. /help")


def handle(msg):
    cid = msg["chat"]["id"]
    text = (msg.get("text") or msg.get("caption") or "").strip()
    if not cfg.get("chat_id"):
        if text == "/start " + cfg.get("pair_code", "") or text == cfg.get("pair_code"):
            cfg["chat_id"] = cid
            save_cfg()
            say("✅ Paired. This bot now only listens to you.\n\n" + HELP)
        else:
            tg("sendMessage", {"chat_id": cid, "text": "Send the pairing code shown on the Mac."})
        return
    if msg.get("chat", {}).get("type") != "private":
        return                       # ignore groups
    if cid == cfg["chat_id"]:
        ev("telegram", text or "(non-text message)")
        handle_owner(text)
    else:
        handle_guest(msg, text)


def handle_callback(cq):
    cid = cq.get("message", {}).get("chat", {}).get("id")
    data = cq.get("data", "")
    owner = cid == cfg.get("chat_id")
    note = "Done"
    if data == "cancel":
        if owner or guests().get(str(cid), {}).get("status") == "allowed":
            note = "Cancelling…" if cancel_current(None if owner else cid) else "Nothing of yours is running."
    elif owner and ":" in data:
        kind, arg = data.split(":", 1)
        if kind in ("approve", "decline"):
            d = job_dir(arg)
            note = (approve(d) if kind == "approve" else decline(d)) if d else "Job not found."
        elif kind in ("allow", "block"):
            note = set_guest(arg, "allowed" if kind == "allow" else "blocked")
    try:
        tg("answerCallbackQuery", {"callback_query_id": cq["id"], "text": note[:190]})
    except Exception:
        pass


def main():
    JOBS.mkdir(exist_ok=True)
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=timer, daemon=True).start()
    offset = cfg.get("offset", 0)
    log("reel bot running")
    try:
        import dashboard
        dashboard.start(sys.modules[__name__])
    except Exception as e:
        log("dashboard failed:", e)
    while True:
        try:
            r = tg("getUpdates", {"offset": offset, "timeout": 50}, timeout=70)
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                cfg["offset"] = offset
                save_cfg()
                try:
                    if u.get("callback_query"):
                        handle_callback(u["callback_query"])
                    if "message" in u:
                        handle(u["message"])
                except Exception as e:
                    log("handle error", e)
        except Exception as e:
            log("poll error", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
