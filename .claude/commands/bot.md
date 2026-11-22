---
description: Telegram reel bot status, recent jobs and fixes
---
Check the Telegram reel bot (`tools/reel-bot/`, README there):

- `launchctl print gui/$(id -u)/com.reelagents.reelbot` (state and pid)
- the last 30 lines of `~/.config/reel-bot/bot.log`
- the newest folders in `Bot Jobs/`: `result.json`, and the tail of `claude.log`

Report whether it's running, what the last jobs produced, and any errors with a proposed fix.
Never print the token from `~/.config/reel-bot/config.json`.
