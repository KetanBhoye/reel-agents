#!/bin/zsh
# setup.sh <telegram-bot-token>: save the token, generate a pairing code, start the bot at login
set -e
DIR="${0:A:h}"   # this folder (tools/reel-bot)
TOKEN=$1; [[ -n $TOKEN ]] || { echo "usage: setup.sh <bot token from @BotFather>"; exit 1; }
CFG=~/.config/reel-bot; mkdir -p $CFG; chmod 700 $CFG
CODE=$(jot -r 1 100000 999999)
pkill -f "reel-bot/bot.py" 2>/dev/null || true   # stop any test copy still running
# Keep an existing pairing, so changing the token doesn't need /start again
/usr/bin/python3 -c "
import json,sys,os
p=sys.argv[3]; old=json.load(open(p)) if os.path.exists(p) else {}
json.dump({'token':sys.argv[1],'chat_id':old.get('chat_id'),'pair_code':sys.argv[2]}, open(p,'w'), indent=2)" "$TOKEN" "$CODE" $CFG/config.json
chmod 600 $CFG/config.json
ME=$(curl -s "https://api.telegram.org/bot$TOKEN/getMe" | /usr/bin/python3 -c "import json,sys; d=json.load(sys.stdin); print(d['result']['username'] if d.get('ok') else 'BAD_TOKEN')")
[[ $ME == BAD_TOKEN ]] && { echo "Telegram rejected that token."; exit 1; }
PL=~/Library/LaunchAgents/com.reelagents.reelbot.plist
cat > $PL <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.reelagents.reelbot</string>
  <key>ProgramArguments</key><array><string>/usr/bin/python3</string><string>$DIR/bot.py</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$CFG/bot.log</string>
  <key>StandardErrorPath</key><string>$CFG/bot.log</string>
</dict></plist>
PLIST
launchctl bootout gui/$(id -u)/com.reelagents.reelbot 2>/dev/null || true
launchctl bootstrap gui/$(id -u) $PL
echo "Bot @$ME is running."
if /usr/bin/python3 -c "import json;exit(0 if json.load(open('$CFG/config.json')).get('chat_id') else 1)"; then
  echo "Already paired with your Telegram. Send /status to t.me/$ME to check."
else
  echo "On your phone: open t.me/$ME and send:  /start $CODE"
fi
