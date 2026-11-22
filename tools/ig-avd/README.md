# ig-avd: schedule reels in the Instagram Android app (experimental)

Drives the Instagram app inside an Android emulator over `adb`, using UI-tree lookups plus a few
screen positions. Instagram updates often move things around, so expect to adjust coordinates.
Automating the app may go against Instagram's terms; use at your own risk.

## Setup
1. Android Studio → Device Manager → create a phone AVD **with Play Store**. Set `IG_AVD` to its
   name (default `Medium_Phone_API_36.1`).
2. Start it with `emulator -avd "$IG_AVD" -no-snapshot`, install Instagram from the Play Store, and
   **log in yourself**. The scripts never touch passwords.
3. Captions with emoji are pasted through a tiny clipboard helper app (`com.reelagents.clipper`,
   not included). Without it, use plain-text captions or paste the caption by hand.

## Use
A spec file per reel:
```json
{"file": "/path/to/reel.mp4", "when": "2026-12-01 19:30",
 "caption": "your caption…", "own": true}
```
`python3 sched2.py spec.json` stops on the final screen so you can check it; add `--go` to tap
Schedule. `own: true` keeps the video's own audio; otherwise set `"audio_page"` or `"ref"` to use
a trend sound via "Use audio".
