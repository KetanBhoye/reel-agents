#!/usr/bin/env python3
"""igctl: drive the Instagram app in an Android emulator (AVD).

Reads the screen through uiautomator (text, ids, bounds) instead of guessing coordinates.

  igctl.py boot                         start the emulator (cold boot; the old snapshot crashes it)
  igctl.py shot [name]                  screenshot -> scratch/<name>.png (405x900)
  igctl.py ui [filter]                  list on-screen elements: bounds, clickable, text | desc | id
  igctl.py tap "<text|desc|id>" [n]     tap the n-th element matching
  igctl.py clip "<text>"                put any text (emoji, Marathi) on the phone clipboard
  igctl.py open <instagram url>         open a reel or profile in the app
  igctl.py save-audio <reel url>        open a reel's audio page and tap "Save audio"
  igctl.py stats <reel url> [...]       read a reel's insights (views, skip rate, share rate, ...) as JSON
  igctl.py compose <spec.json>          build a scheduled reel up to the final button, then stop
  igctl.py confirm                      press the final Schedule/Share button (only after he says yes)
  igctl.py draft <file.mp4> ["caption"]  save a reel (no sound) to Drafts for him to finish
  igctl.py schedule <spec.json>         whole flow: Use audio from "ref" reel -> newest video -> post -> Schedule

spec (compose / schedule):
  {"file": "/abs/path.mp4", "ref": "https://www.instagram.com/reel/<code>/",
   "caption": "...", "location": "Rajgad Fort", "trial": true, "when": "2026-11-09 19:30"}
  Sound ALWAYS comes from the reference reel's audio page -> "Use audio" (never song search:
  it picks the wrong part of the song). Highest-quality upload is always switched on.

Nothing is ever posted without `confirm`. Never type passwords here.
"""
import base64, datetime as dt, json, os, re, subprocess, sys, time

ADB = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")
EMU = os.path.expanduser("~/Library/Android/sdk/emulator/emulator")
AVD = os.environ.get("IG_AVD", "Medium_Phone_API_36.1")  # your AVD name
SCRATCH = os.environ.get("IGCTL_SCRATCH", "/tmp/igctl")
PHONE_DIR = "/sdcard/Movies/Reels"
os.makedirs(SCRATCH, exist_ok=True)


# ---------- adb basics ----------
def adb(*a, text=True):
    return subprocess.run([ADB, *a], capture_output=True, text=text).stdout

def sh(cmd):
    return adb("shell", cmd)

def tap_xy(x, y):
    sh(f"input tap {x} {y}")

def key(code):
    sh(f"input keyevent {code}")

def back():
    key(4)

def swipe(x1, y1, x2, y2, ms=400):
    sh(f"input swipe {x1} {y1} {x2} {y2} {ms}")


# ---------- screen model ----------
def nodes():
    x = adb("exec-out", "uiautomator", "dump", "/dev/tty")
    out = []
    for m in re.finditer(r"<node [^>]*>", x):
        n = m.group(0)
        g = lambda k: (re.search(k + r'="([^"]*)"', n) or [None, ""])[1]
        b = list(map(int, re.findall(r"\d+", g("bounds"))))
        if len(b) < 4:
            continue
        out.append(dict(t=g("text"), d=g("content-desc"), r=g("resource-id").split("/")[-1],
                        c=g("clickable") == "true", k=g("checked") == "true", b=b))
    return out

def label(n):
    return " | ".join(v for v in (n["t"], n["d"], n["r"]) if v)

def find(q, ns=None, exact=False):
    ns = ns if ns is not None else nodes()
    q = q.lower()
    if exact:
        return [n for n in ns if q in (n["t"].lower(), n["d"].lower(), n["r"].lower())]
    return [n for n in ns if q in label(n).lower()]

def center(n):
    b = n["b"]
    return (b[0] + b[2]) // 2, (b[1] + b[3]) // 2

def tap(q, i=0, exact=False, ns=None):
    hits = find(q, ns, exact)
    if len(hits) <= i:
        raise SystemExit(f"NOT FOUND: {q}")
    tap_xy(*center(hits[i]))
    return hits[i]

def wait_for(q, timeout=20, exact=False):
    end = time.time() + timeout
    while time.time() < end:
        hits = find(q, exact=exact)
        if hits:
            return hits[0]
        time.sleep(1)
    raise SystemExit(f"TIMEOUT waiting for: {q}")

def shot(name="s"):
    p = f"{SCRATCH}/{name}_full.png"
    with open(p, "wb") as f:
        f.write(subprocess.run([ADB, "exec-out", "screencap", "-p"], capture_output=True).stdout)
    small = f"{SCRATCH}/{name}.png"
    subprocess.run(["sips", "-Z", "900", p, "--out", small], capture_output=True)
    return small

def clip(text):
    b64 = base64.b64encode(text.encode()).decode()
    sh(f"am start -n com.reelagents.clipper/.SetClip --es b64 {b64}")
    time.sleep(1.5)

def paste_into(field_q, text):
    tap(field_q)
    time.sleep(0.8)
    sh("input keycombination 113 29")  # select all
    key(67)                              # delete
    clip(text)
    tap(field_q)
    time.sleep(0.5)
    key(279)                             # paste
    time.sleep(0.8)


# ---------- app helpers ----------
def boot():
    if "emulator-" in adb("devices"):
        print("already running"); return
    subprocess.Popen([EMU, "-avd", AVD, "-no-snapshot", "-gpu", "host"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    adb("wait-for-device")
    while sh("getprop sys.boot_completed").strip() != "1":
        time.sleep(3)
    print("booted")

def open_url(url):
    sh(f"am start -a android.intent.action.VIEW -d '{url}' com.instagram.android")
    time.sleep(5)

def push_as_newest(path):
    """Copy a video so it's the newest item in the gallery (first tile after the camera)."""
    name = os.path.basename(path)
    sh(f"mkdir -p {PHONE_DIR}")
    adb("push", path, f"{PHONE_DIR}/{name}")
    sh(f"touch '{PHONE_DIR}/{name}'")
    sh(f"am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d 'file://{PHONE_DIR}/{name}'")
    time.sleep(2)


# ---------- audio ----------
def save_audio(url):
    open_url(url)
    ns = nodes()
    row = [n for n in ns if "·" in n["t"] and n["c"]] or find("Original audio", ns)
    if not row:
        raise SystemExit("no audio row on this reel")
    tap_xy(*center(row[0]))
    time.sleep(4)
    ns = nodes()
    if find("Save audio", ns) or find("Saved", ns):
        if find("Save audio", ns):
            tap("Save audio", ns=ns)
            time.sleep(1)
        print("saved:", row[0]["t"]); return
    raise SystemExit("audio page did not open; take a shot and check")


# ---------- stats ----------
STAT_KEYS = ["Views", "Viewers", "Average watch time", "Follows", "Skip rate", "Share rate",
             "Like rate", "Save rate", "Repost rate", "Comment rate"]

def read_insight_screen(acc):
    ns = nodes()
    texts = [n["t"] or n["d"] for n in ns if (n["t"] or n["d"])]
    for i, t in enumerate(texts[:-1]):
        if t in STAT_KEYS and t not in acc:
            acc[t] = texts[i + 1]
    return acc

def stats(url):
    open_url(url)
    # own reel: the "View insights" / "Trial insights" entry sits under the video
    for q in ("View insights", "Trial insights", "Insights"):
        if find(q):
            tap(q); break
    time.sleep(4)
    if find("View insights"):
        tap("View insights"); time.sleep(4)
    acc = {}
    for _ in range(4):
        read_insight_screen(acc)
        swipe(540, 1900, 540, 900)
        time.sleep(1.5)
    return acc


# ---------- compose + schedule ----------
def _pick_vals():
    return [n for n in nodes() if n["r"] == "numberpicker_input"]

def _step(col, direction, times):
    b = _pick_vals()[col]["b"]; h = b[3] - b[1]
    for _ in range(times):
        tap_xy((b[0] + b[2]) // 2, (b[1] + b[3]) // 2 + direction * h)
        time.sleep(0.7)

def set_picker(col, target):
    """col: 0 date, 1 hour, 2 minute, 3 am/pm. Computes the steps, taps, then verifies."""
    for _ in range(4):
        cur = _pick_vals()
        if len(cur) < 4: raise SystemExit("picker not visible")
        c = cur[col]["t"]
        if c == target: return
        if col == 0:
            y = dt.date.today().year
            d = (dt.datetime.strptime(f"{target} {y}", "%a, %b %d %Y") - dt.datetime.strptime(f"{c} {y}", "%a, %b %d %Y")).days
        elif col == 1:
            d = (int(target) - int(c)) % 12
        elif col == 2:
            d = ((int(target) - int(c)) // 5) % 12
        else:
            d = 1 if target == "PM" else -1
        if col in (1, 2) and d > 6: d -= 12   # shorter way round
        _step(col, 1 if d > 0 else -1, abs(d))
        time.sleep(0.5)
    if _pick_vals()[col]["t"] != target:
        raise SystemExit(f"could not set picker {col} to {target}")

def pixel(x, y):
    from PIL import Image
    p = f"{SCRATCH}/px.png"
    with open(p, "wb") as f:
        f.write(subprocess.run([ADB, "exec-out", "screencap", "-p"], capture_output=True).stdout)
    return Image.open(p).convert("RGB").getpixel((x, y))

def switch_on(row_text):
    """Toggles on More options don't report their state; read the track colour (dark = on)."""
    r = find(row_text)
    if not r: raise SystemExit(f"row not found: {row_text}")
    y = (r[0]["b"][1] + r[0]["b"][3]) // 2
    for _ in range(3):
        if sum(pixel(925, y)) < 150: return True
        tap_xy(970, y); time.sleep(1.5)
    return sum(pixel(925, y)) < 150

def set_schedule(when):
    t = dt.datetime.strptime(when, "%Y-%m-%d %H:%M")
    if t.minute % 5:
        raise SystemExit("minutes must be a multiple of 5")
    tap("More options"); time.sleep(2)
    sched = find("Schedule this reel")[0]
    tap_xy(970, (sched["b"][1] + sched["b"][3]) // 2)
    wait_for("numberpicker_input")
    set_picker(0, t.strftime("%a, %b %d"))
    set_picker(3, t.strftime("%p"))
    set_picker(1, str(int(t.strftime("%I"))))
    set_picker(2, t.strftime("%M"))
    tap("Done", exact=True); time.sleep(2)
    back(); time.sleep(2)  # back to the post screen

def set_trial(on=True):
    for _ in range(3):
        tr = find("Trial", exact=True)
        if tr: break
        swipe(540, 1800, 540, 900); time.sleep(1)
    toggles = [n for n in nodes() if n["r"] == "toggle"]
    trial_row = find("Trial", exact=True)[0]
    tg = min(toggles, key=lambda n: abs(n["b"][1] - trial_row["b"][1]))
    if tg["k"] != on:
        tap_xy(*center(tg)); time.sleep(1)

def set_location(name):
    tap("metadata_location_first_row"); time.sleep(3)
    clip(name); key(279); time.sleep(4)
    ns = nodes()
    hits = [n for n in ns if n["t"] and name.split()[0].lower() in n["t"].lower() and n["c"]]
    if not hits:
        hits = [n for n in ns if n["t"] and name.split()[0].lower() in n["t"].lower()]
    tap_xy(*center(hits[0])); time.sleep(2)

def wait_dump(timeout=15):
    """uiautomator can't dump while video plays; retry until it returns something."""
    end = time.time() + timeout
    while time.time() < end:
        ns = nodes()
        if ns: return ns
        time.sleep(1)
    return []

def use_audio(ref_url):
    """Reference reel -> its audio page -> Use audio (keeps the trend's exact song part)."""
    open_url(ref_url); time.sleep(2)
    # the audio row sits under the author name; its text scrolls, so tap by position
    ns = wait_dump()
    row = [n for n in ns if n["r"] == "clips_author_username"]
    y = row[0]["b"][3] + 27 if row else 2039
    tap_xy(250, y); time.sleep(6)
    tap_xy(285, 653); time.sleep(6)          # "Use audio" on the audio page (video page: no dump)
    tap_xy(88, 2256); time.sleep(4)          # gallery button in the reels camera

def pick_newest():
    if find("Start new video"):                 # leftover unsaved edit prompt
        tap("Start new video"); time.sleep(3)
    t = [n for n in wait_dump() if n["r"] == "gallery_grid_item_thumbnail"]
    if not t: raise SystemExit("gallery not open")
    t.sort(key=lambda n: dt.datetime.strptime(n["d"].split("created on ")[1], "%B %d, %Y %I:%M %p"), reverse=True)
    tap_xy(*center(t[0])); time.sleep(6)
    if find("Get App"): swipe(540, 1700, 540, 2350, 300); time.sleep(2)
    return t[0]["d"]

def finish_post(caption, location=None, when=None, trial=True):
    """From the editor: Next -> caption, then post_rest()."""
    ns = nodes()
    for q in ("clips_right_action_button", "drawer_next_button_layout", "Next"):
        if find(q, ns): tap(q, ns=ns); break
    else:
        tap_xy(959, 110)   # editor's top-right arrow (screen unreadable while the video plays)
    wait_for("caption_input_text_view", 25)
    paste_into("caption_input_text_view", caption); back(); time.sleep(1)
    post_rest(location, when, trial)

def pick_location(location):
        """Inside the location screen: search, pick the first venue, confirm the map sheet."""; time.sleep(3)
        tap("row_search_edit_text"); clip(location); tap("row_search_edit_text"); key(279); time.sleep(5)
        v = []
        for _ in range(20):
            v = [n for n in nodes() if n["r"] == "row_venue_title"]
            if v: break
            time.sleep(1.5)
        if not v: raise SystemExit("no location results")
        tap_xy(540, v[0]["b"][1] + 40); time.sleep(3)
        if find("Add", exact=True): tap("Add", exact=True); time.sleep(3)

def post_rest(location=None, when=None, trial=True):
    """On the post screen: location, trial, schedule time + highest quality."""
    if location:
        tap("metadata_location_first_row"); time.sleep(3)
        pick_location(location)
    set_trial(trial); time.sleep(2)
    if find("Close", exact=True): tap("Close", exact=True); time.sleep(2)
    for _ in range(3):
        if find("More options"): break
        swipe(540, 1800, 540, 900); time.sleep(1)
    if when:
        t = dt.datetime.strptime(when, "%Y-%m-%d %H:%M")
        tap("More options"); time.sleep(3)
        sched = find("Schedule this reel")[0]
        tap_xy(970, (sched["b"][1] + sched["b"][3]) // 2)
        wait_for("numberpicker_input")
        set_picker(0, t.strftime("%a, %b %d")); set_picker(3, t.strftime("%p"))
        set_picker(1, str(int(t.strftime("%I")))); set_picker(2, t.strftime("%M"))
        got = [n["t"] for n in nodes() if n["r"] == "numberpicker_input"]
        tap("Done", exact=True); time.sleep(3)
        print("schedule on:", switch_on("Schedule this reel"), "| highest quality on:", switch_on("Upload at highest quality"))
        back(); time.sleep(2)
        print("schedule set:", got)
    btn = find("share_button", exact=True)
    print("button:", btn[0]["t"] if btn else "?")

def schedule_reel(spec):
    """spec: file, ref (reference reel url for Use audio), caption, location, when."""
    push_as_newest(spec["file"])
    use_audio(spec["ref"])
    print("picked:", pick_newest())
    finish_post(spec["caption"], spec.get("location"), spec.get("when"), spec.get("trial", True))
    confirm()

def save_draft(file, caption=""):
    """Reel with no sound -> Drafts, for him to finish (sound, text) himself."""
    for _ in range(6):
        if find("feed_tab"): break
        back(); time.sleep(1.5)
    push_as_newest(file)
    tap("feed_tab"); time.sleep(2)
    tap("action_bar_left_button"); time.sleep(4)
    if find("cam_dest_clips"): tap("cam_dest_clips"); time.sleep(4)
    print("picked:", pick_newest())
    ns = nodes()
    if find("clips_right_action_button", ns): tap("clips_right_action_button", ns=ns)
    else: tap_xy(959, 110)
    wait_for("caption_input_text_view", 25)
    if caption:
        paste_into("caption_input_text_view", caption); back(); time.sleep(1)
    tap("save_draft_button"); time.sleep(5)
    print("draft saved")

def compose(spec):
    push_as_newest(spec["file"]); use_audio(spec["ref"]); pick_newest()
    finish_post(spec["caption"], spec.get("location"), spec.get("when"), spec.get("trial", True))
    print("READY. Run: igctl.py confirm")

def confirm():
    tap("share_button", exact=True); time.sleep(6)
    if find("Turn off and share"):          # Meta AI original-audio prompt: he chose "turn off"
        tap("Turn off and share"); time.sleep(8)
    toast = [label(n) for n in nodes() if "scheduled" in label(n).lower()]
    print("result:", toast[0] if toast else "no toast seen; check Scheduled content")


# ---------- cli ----------
if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: print(__doc__); sys.exit()
    c = a[0]
    if c == "boot": boot()
    elif c == "shot": print(shot(a[1] if len(a) > 1 else "s"))
    elif c == "ui":
        f = (a[1] if len(a) > 1 else "").lower()
        for n in nodes():
            s = label(n)
            if s and f in s.lower(): print(n["b"], "C" if n["c"] else " ", "✓" if n["k"] else " ", s[:130])
    elif c == "tap": print("tapped", label(tap(a[1], int(a[2]) if len(a) > 2 else 0)))
    elif c == "clip": clip(a[1]); print("clipboard set")
    elif c == "open": open_url(a[1])
    elif c == "save-audio": save_audio(a[1])
    elif c == "stats": print(json.dumps({u: stats(u) for u in a[1:]}, indent=1))
    elif c == "compose": compose(json.load(open(a[1])))
    elif c == "confirm": confirm()
    elif c == "schedule": schedule_reel(json.load(open(a[1])))
    elif c == "draft": save_draft(a[1], a[2] if len(a) > 2 else "")
    else: print(__doc__)
