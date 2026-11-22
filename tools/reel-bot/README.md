# Reel bot (Telegram → Mac → Telegram)

Share an Instagram reel to the bot and type what you want. The Mac then:
1. downloads the reel (`reel-dl`)
2. runs Claude Code unattended with `job_prompt.md`, which:
   - analyses the reel
   - searches the raw footage folders and Apple Photos
   - builds 1–2 versions in PalmierPro (2 unless you say "1 version")
   - exports them
3. sends back the videos (as files, so there's no Telegram compression), caption, hashtags,
   audio and posting notes

You post them yourself.

## Setup (once)

1. In Telegram, message **@BotFather** and send `/newbot`. Give it a name and a username, and
   copy the token.
2. On the Mac, in Terminal (not in a chat, so the token stays private), run:
   `tools/reel-bot/setup.sh <token>` (from the repo folder)
3. Open the bot link it prints and send `/start <code>`. The bot then only answers you.

## Use

- Instagram → reel → **Share → Telegram → your bot**. Then type your requirements, for example
  "rajgad footage, aesthetic, 1 version". Send `/go`, or it starts by itself after 3 minutes.
- **Ask anything** (ideas, captions, what to shoot). Any message that isn't a link gets a reply
  from Claude, which is read-only and uses the knowledge base. It remembers context for 30 min.
- `/make <idea>`: builds from an idea with no reference reel, e.g. `/make i said i love hiking,
  beach version`.
- Other commands: `/status`, `/cancel` (or the 🛑 button on the "started" message), `/retry`,
  `/help`.
- Jobs go in `Bot Jobs/<date>_<code>/`, holding `reference/`, `output/`, `result.json`,
  `SHOTLIST.md` and `claude.log`.

## Needs

- **The Mac on and awake**, logged in. It uses `caffeinate` during a build.
- **PalmierPro.** The bot opens it automatically.
- **Telegram's 50 MB bot limit.** Larger finals get a lighter copy for Telegram, and the full
  file stays on the Mac.
- **Usage limits.** Each build uses your Claude usage like a normal session; a build is
  roughly 20–60 min.
- **Photos access.** If a job reports that it can't read the Photos library, give `python3`
  Full Disk Access (System Settings → Privacy & Security), or limit it to the footage folders.

## Manage

- Log: `~/.config/reel-bot/bot.log`
- Stop: `launchctl bootout gui/$(id -u)/com.reelagents.reelbot`
- Start again: rerun `setup.sh`. You'll need to pair again.

## Dashboard: http://localhost:8765

Runs inside the bot (`dashboard.py` + `dashboard.html`), on this Mac only (127.0.0.1).
- **Requests:** every job, where it came from (📱 Telegram / 🖥️ dashboard), status, requirements.
- **Progress:** Queued → Download → Analyse → Find footage → Edit → Export → Caption, plus every
  step Claude took, read live from `claude.log`.
- **Results:** play the videos, copy the caption + keywords + hashtags block.
- **Actions:** cancel, retry / rebuild, remove from queue, open folder, start a waiting link,
  queue a new build from a link or an idea.
- **Activity:** your Telegram messages, the bot's chat answers and job status changes
  (`Bot Jobs/_events.jsonl`). Each job also has a `status.json`.

## Friends (guest access with approval)

- Someone new messages the bot → you get **Allow / Block** buttons (also on the dashboard
  under Friends, or `/guests`). Until you allow them they only get "waiting for the owner".
- An allowed friend shares a reel + requirements (or `/make <idea>`) → you get
  **Approve / Decline**. Nothing runs until you approve.
- Their videos and caption go to **their** chat; you get key updates prefixed `[name]`.
- Friends can't use the chat answers (those read your workspace folder), `/retry`, or cancel your
  builds; only their own `/status` and `/cancel`. Builds use your footage and Claude usage.
- Guests are stored in `config.json` under `"guests"`.
