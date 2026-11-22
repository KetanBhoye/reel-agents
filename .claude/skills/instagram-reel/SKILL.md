---
name: instagram-reel
description: Edit an Instagram Reel from raw phone clips using the palmier-pro MCP video editor - beat-synced cutting, color grading, on-screen text, music extraction from a reference reel, and export. Use when the user wants to make/edit a reel, short-form vertical video, TikTok, or YouTube Short from their footage, or references a reel whose look/song they want to copy, including recreating a reference reel shot-for-shot with their own footage (same typography, matched shots, AI fill shots).
---

# Instagram Reel Editing

Build a finished vertical reel from raw clips in the palmier-pro MCP editor. The
workflow below is ordered; skipping the assessment steps produces generic edits.

## Choose the editor first

Two editors are connected. Pick one per reel and say which, and why, in one line.

- **Palmier** (`mcp__palmier-pro__*`), the default:
  - beat-exact montage cuts, or matching a reference's cut points frame by frame
  - grading, layouts, keyframes
  - several versions as separate timelines
  - all Telegram bot jobs
- **Edits**, Instagram's own editor (`mcp__metapilot-native__*`):
  - text that must look exactly like Instagram's (Classic and Modern fonts)
  - auto captions in Instagram caption styles
  - Instagram filters, transitions and speed ramps that a reference uses
  - `autoReframe` for landscape to 9:16
  - voiceover and Voice Enhance
  - simple one-shot reels with text
- **Both:** cut in Palmier, `finalize` into the scratchpad, then add the Instagram text or
  captions in Edits and export.

The full Edits guide (tools, their text defaults, export, audio, traps) is in
`references/edits-app.md`. Read it before the first Edits call. The rest of this file is the
Palmier workflow. Its principles (look at every clip, cut on the beat, one idea per reel,
verify visually) apply in Edits too.

## Non-negotiables

- **Never cut before you have looked at every clip.** `inspect_media` with
  `overview:true` on each asset first. You cannot pick a hook or an ending from
  filenames.
- **Every cut lands on a beat.** Run `detect_beats` on the music and place clips
  on that grid. This single thing separates an edit that feels professional from
  one that feels like a slideshow. **Exception:** when the audio is a voiceover,
  poem or quote, cut on the spoken phrases instead (`inspect_media
  wordTimestamps:true`), as the reference does.
- **Copying a reference reel?** Read `references/recreating-reference-reels.md`
  first. It covers measuring cuts, text timing, font, colour and watermark, mapping
  shots by meaning, and the vertical-format decisions.
- **One idea per reel.** A shot that breaks the tone (different location, different
  camera, a joke in a landscape piece) hurts more than it adds. Cut it.
- **Verify visually.** `capture_frame` then `inspect_media` on the captured frame
  after grading and after adding text. Do not report a look as done unseen.

## Step 1 — Read the footage and the reference

```
manage_project action:list        # confirm which project is open
get_media                         # inventory + timelines
inspect_media mediaRef overview:true   # EVERY clip, in parallel batches
```

If the user supplies a reference reel (a file path or a link they downloaded),
import it and inspect it too. Extract from it:

- **Pacing** — how long is each shot? (tile timestamps tell you)
- **Text** — how many lines, what font class (serif = quiet/poetic, bold sans =
  hook-driven), where on screen, does it persist or change?
- **Grade** — warm/cool, saturated/crushed, faded blacks or deep?
- **Structure** — single continuous shot, or montage?

Then classify their own clips into **heroes** (best composition, internal motion,
the "where is this" answer) and **texture** (supporting, static, repetitive).
Note duplicates — identical files by name or duration usually are.

## Step 2 — Pick a strategy, state it

Match the reference's genre, then adapt to what the footage can actually support.
Say the strategy in one or two sentences before building. Three that cover most
travel/lifestyle footage:

| Format | Length | Structure |
|---|---|---|
| Hook-driven POV | 18-22s | text hook frame 1, cuts every 1-1.5s, location tag, CTA |
| Cinematic | 28-33s | 3s shots, minimal text, ambient audio under music, push-ins |
| Mood piece | 8-12s | 6-8 wet/dark shots, one persistent line, loops seamlessly |

## Step 3 — Music

Either (a) the user names a track, (b) rip it from their reference reel, or
(c) generate one.

Rip from a reference (works because palmier imports local paths in place):

```bash
ffmpeg -y -i /path/to/reference.mp4 -vn -c:a aac -b:a 192k song.m4a
```

then `import_media` with `source:{path:...}` and `detect_beats` on the result.
Detecting beats on the audio-only file is faster and more reliable than on the
source video.

Generate instead: `list_models type:audio` → `generate_audio` with
`model:'elevenlabs-music'`, `instrumental:true`, a duration, and a prompt naming
genre + instruments + BPM + mood. Costs real money; it is not undoable.

**Ripped audio is baked into the export and Instagram may flag or mute it.**
Say so once, and offer a music-free export so the user can add the same track
from IG's audio library at upload.

## Step 4 — Build the cut on the beat grid

`detect_beats` returns `beats` and `downbeats` in **source seconds**. Convert:
`frame = seconds × fps`. A bar is 4 beats; at 100 BPM that is ~2.4s ≈ 70 frames.

Structure the energy — do not use a uniform shot length:

- **0:00-0:02** two half-beat or single-beat cuts. Motion in frame 1. Never open
  on a static wide.
- **early hero** at ~0:02, a full bar. Answer "where am I" fast — do not save the
  best shot for 0:15, most viewers never get there.
- **middle** alternate full bars (breathe) with half bars (rhythm). Two half-bar
  cuts, then a hero, then two more.
- **end** the longest shot of the reel, fading out with the music. This is what
  earns the rewatch.

Place clips with `add_clips`, giving each a `source:[startSec, endSec]` window
whose length equals the frames you want ÷ fps. Choose in-points from the overview
tiles — never start at 0.0s, phone clips begin with a stabilization wobble.

**Rounding leaves 1-frame gaps.** After adding, fix every clip whose `frames`
end is one short of the next start with
`set_clip_properties durationFrames:<n>`. Check the whole timeline for this.

Mute the source audio when music carries the reel
(`set_clip_properties volumeDb:-60` on the nested `audio.id`, not the video clip
id). For a cinematic cut, keep it at −20 to −24 dB instead so rain and engine
sit under the music — but mute any clip with speech in it.

## Step 5 — Grade

`apply_color` merges by default, so nudge one knob at a time; `reset:true`
starts from neutral. See `references/grades.md` for three tested recipes
(punchy, warm-faded cinematic, moody dark) with exact values.

Apply the same grade to every clip in one call so the reel reads as one look.
`apply_effect` is separate from grading — grain, vignette, clarity/dehaze live
there. Negative `dehaze` *adds* atmosphere, which is what you want for fog.

## Step 6 — Motion on static shots

Static shots are the main cause of mid-reel drop-off. Add a slow push-in with
`set_keyframes property:'scale'`, clip-relative frames:

```
[[0, 1, 1, "linear"], [<lastFrame>, 1.06, 1.06, "linear"]]
```

Reverse it (1.06 → 1.0) on one shot for variety. 6-9% over 2-3s is enough; more
reads as a zoom. Skip shots that already have camera motion.

## Step 7 — Text

Ask what the user wants before adding a lot of it — many people want none.
Default for trend reels: small (~46px), plain sans, white lowercase, static, placed
where the reference reels put it. No animation unless asked. Two
modes:

**Hook mode** (bold sans, `Helvetica-Bold`, ~68pt on a 2160-wide canvas, top
third at `y:0.15`, `animation:'popIn'`): a curiosity gap in frame 1 that the
footage disproves, a location tag mid-reel, and a save-driving CTA at the end.

**Quiet mode** (serif, `Baskerville`, ~44-54pt, `y:0.24-0.34`): one block that
holds for the whole reel, fading in and out. Statement + colon works — the
footage is the answer.

Always a heavy drop shadow (blur 24-30, opacity 0.75-0.85) — white text over an
overcast sky vanishes without one. Add fades with `set_clip_properties` so text
never pops.

**Copy mode** (when recreating a reference): the reference's own font, colour and
position, measured rather than guessed. One line per shot, hard swaps, and a light
shadow (opacity 0.25, blur 6) only. Example: the quote reel used
HelveticaNeue-Italic 30pt #E8D01F at y 0.5. Replace the creator watermark with the
user's handle (e.g. `YOUR.HANDLE`, HelveticaNeue-Bold 18pt, same colour, y 0.8), or drop it if the user doesn't want a watermark.
Move a single line off a face rather than every line.

## Step 8 — Export

Use the repo's tools (in `tools/`, on your PATH): `analyze-reel <ref.mp4>` for Step 1 (sheet, cuts,
on-screen text, speech) and `finalize <master.mov> <out.mp4>` for the final transcode below.


Draft/review exports — fast, small:

```
export_project mode:'video' codec:'H.264' resolution:'1080p' outputPath:'<abs path>.mp4'
```

**Final upload — maximum quality that survives Instagram.** Two stages: render a
ProRes master from palmier, then transcode it yourself. See
`references/export-quality.md` for the reasoning and the exact ffmpeg command.
Short version:

```
export_project mode:'video' codec:'ProRes' resolution:'Match Timeline' outputPath:'<tmp>/master.mov'
```
```bash
ffmpeg -y -i master.mov \
 -vf "scale=1080:1920:flags=lanczos,format=yuv420p" \
 -c:v libx264 -profile:v high -level 4.2 -preset veryslow -crf 16 \
 -maxrate 25M -bufsize 50M \
 -x264-params "keyint=60:min-keyint=30:scenecut=0:bframes=2:ref=4" \
 -color_primaries bt709 -color_trc bt709 -colorspace bt709 \
 -c:a aac -b:a 320k -ar 48000 -movflags +faststart out.mp4
```

Put the ProRes master in scratch, not the user's folder — it is ~2GB per 30s.

`manage_exports action:'list'` to poll; **`progress:100` with
`status:'rendering'` is not done** — poll until `status:'completed'`, or check
the file on disk.

## Iterating

Use `create_timeline from:<id>` to version. A named timeline per idea
("Draft 1 — POV Hook") keeps every variant alive in one project instead of
overwriting the user's approved cut. Rebuilding a cut wholesale
(`remove_clips` everything, then `add_clips`) is usually cleaner than nudging
twenty clips — clip ids change, so re-read `get_timeline` after.

Name versions V1, V2, V3… and give each a no-text twin timeline. Export as
`V<n>_<reel>_with-text.mp4` and `V<n>_<reel>_no-text.mp4`.

**AI fill shots** (`generate_video`, paid): use them only for a line the footage
can't cover, and only with the user's go-ahead. Use the user's photos as Kling O3
references. Generate the shortest duration that covers the shot, poll `get_media`
right away for a credit failure, and colour-match with the "Match an AI clip" recipe
in `references/grades.md`. Tell the user Instagram may label it as AI.

`references/palmier-gotchas.md` has the API traps worth knowing before you hit
them. `references/recreating-reference-reels.md` is the copy-a-reel workflow. `references/media-sourcing.md` explains how to find footage in Apple Photos
(scene labels, face tags, iCloud export). `references/reel-research.md` has the retention data behind the structure
choices above.
