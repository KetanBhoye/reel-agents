---
description: Build a reel from an Instagram link, a local reference file, or an idea, plus requirements
argument-hint: <instagram link | file path | idea> [requirements, e.g. "trek footage, 2 versions"]
---
Build a new reel for the creator: $ARGUMENTS

1. If it's an Instagram link, download it with `reel-dl` into `References/To Recreate/`. If
   it's an idea, check the knowledge base `idea-bank.md`.
2. Analyse the reference with `analyze-reel`. Use the footage-scout approach to shortlist
   shots, previewing them.
3. Build it the reel-editor way (load the `instagram-reel` skill):
   - **pick the editor:** Palmier by default; Edits for Instagram-native text, captions or
     effects; or both
   - 1080×1920
   - verify every frame range
   - `finalize` Two versions if asked: one faithful, one creative twist.
4. Write SHOTLIST.md, add a CONTENT_LOG.md row, then give the caption, hashtags, audio and
   posting notes (reel-strategist style).

Ask only if the requirements truly conflict; otherwise decide and say what you chose.
