---
name: aigc-storyboard-video
description: >-
  AIGC storyboard-to-video on Volcengine Ark (火山方舟): Seedream keyframes,
  Seedance first/last-frame clips, ffmpeg crossfade stitch, frame QA. For
  Ark/Seedream/Seedance/分镜 batch video pipelines.
---

# AIGC storyboard video pipeline (Volcengine Ark)

This skill turns a storyboard into a finished video through an API-driven
pipeline: structured shots → Seedream keyframe images → Seedance shot videos
(constrained by first/last frame) → ffmpeg stitch with crossfades → QA frames.
Everything is driven by **one JSON config**, so the same scripts work for any
topic — not just the demo film they were factored out of.

## When to reach for this

Use it for any "make an AI video from a script/分镜" job on Ark: a multi-shot
explainer, a short film, a product story, etc. If the user only wants a single
still image, this is overkill — call the image API directly. This skill earns
its place when there are **multiple shots that must stay visually consistent and
be joined into one film**.

## The pipeline in one picture

```text
storyboard config (JSON)
  → Seedream image generation        (keyframes per shot)
  → Seedance async video task        (first_frame + last_frame + prompt)
  → poll task → download clip
  → per-shot manifest_<id>.json      (models, prompts, task ids, paths)
  → ffmpeg xfade/acrossfade stitch   (one final film)
  → ffmpeg QA frame extraction       (start/middle/end + contact sheet)
```

The core idea worth preserving: **don't hand-copy prompts**. Selection, shots,
images, video, stitching, transitions, and QA are all one scripted, auditable
flow, and **first/last-frame constraints** keep each clip inside one visual
system so the shots cut together cleanly.

## Setup (once)

```bash
pip install -r requirements.txt        # volcengine-python-sdk[ark]
export ARK_API_KEY="your-volcengine-ark-key"   # never commit this
# ffmpeg is needed for stitching + QA:
#   macOS: brew install ffmpeg   |   Debian/Ubuntu: apt-get install ffmpeg
# If ffmpeg isn't on PATH: export FFMPEG=/path/ffmpeg FFPROBE=/path/ffprobe
```

The account behind the key must have **both** the Seedream image model and the
Seedance video model enabled with an active quota. See
`references/troubleshooting.md` for enabling models and fixing quota errors.

## Step 1 — Author the storyboard config

Copy `assets/storyboard.example.json` and edit it. This is where all the
creative work lives. Shape:

- Top level: `project_name`, `out_root`, `image_model`, `video_model`,
  `image_size`, `resolution`, `ratio`, `transition_seconds`, and an optional
  `style_prefix` that is auto-prepended to every image prompt to lock the look.
- `shots`: an ordered list. Each shot has `id`, `folder_name`, `video_name`,
  `duration` (seconds), a `video_prompt`, and an `images` list.
- Each image has a `name`, a `prompt`, and an optional `role`:
  `first_frame`, `last_frame`, or `process` (generated for consistency but not
  fed to the video). If no roles are set, the first image is the first frame and
  the last image is the last frame.

Authoring guidance that makes results stable:
- Put the shared visual identity in `style_prefix`; describe only what changes
  per image in each prompt.
- Generate a controllable first frame, and usually a last frame, for every shot.
- In the `video_prompt`, reference the frames (e.g. "以【图01-1】为首帧 … 定格于
  【图01-3】") and keep on-screen UI/text minimal — generative text is unreliable.
- For audio consistency, describe one consistent narration voice in every shot.

## Step 2 — Dry run first (no cost)

Always validate before spending anything:

```bash
python scripts/generate_storyboard.py path/to/config.json --dry-run
```

This writes every `manifest_<id>.json` and resolves prompts/frame assignments
**without any API calls**. Read the manifests; confirm the first/last frames and
prompts are what you intended.

## Step 3 — Generate shots

```bash
# all shots:
python scripts/generate_storyboard.py path/to/config.json
# a subset / re-run one bad shot:
python scripts/generate_storyboard.py path/to/config.json --shots 03
# reuse good keyframes, only redo the video:
python scripts/generate_storyboard.py path/to/config.json --skip-existing-images
# slower/longer queues:
python scripts/generate_storyboard.py path/to/config.json --timeout 3600 --poll-interval 20
```

Each shot: generates its images, creates a Seedance task, polls to completion,
downloads the clip into its folder, and keeps a manifest. The run is idempotent
per shot — regenerate just the shots that fail QA rather than the whole film.

## Step 4 — Stitch into the final film

```bash
python scripts/stitch_storyboard.py path/to/config.json
# optional: python scripts/stitch_storyboard.py path/to/config.json --transition 0.45
```

Normalizes every clip to 1280x720@30fps, then joins them with a short video
`xfade` and audio `acrossfade`. Writes `<project_name>_final.mp4` and a
`final_stitch_manifest.json` with per-clip durations and estimated vs. actual
length. (A shot may list several `clips` if it was split into parts.)

## Step 5 — QA

```bash
python scripts/qa_storyboard.py path/to/config.json
```

Extracts start/middle/end frames per clip, compares keyframe stills against the
clip's boundary frames via grayscale SSIM, and builds a contact sheet of every
middle frame into `qa_frames/`. Full-auto is not full-trust: review the contact
sheet for style drift, first/last-frame fidelity, flicker, and wrong motion
before delivery, and re-run any weak shot.

## Full sequence

```bash
python scripts/generate_storyboard.py config.json --dry-run   # inspect, no cost
python scripts/generate_storyboard.py config.json             # generate all shots
python scripts/stitch_storyboard.py   config.json             # final film
python scripts/qa_storyboard.py       config.json             # QA frames + report
```

## Known limits (set expectations)

- Narration timbre can vary across shots; pin one voice, post-process if needed.
- Per-shot quality is subject to model randomness — QA before delivery.
- Exact cost comes only from the Ark billing center; manifests hold the task ids
  and model ids for reconciliation but never hardcode prices.

## Reference files

- `references/api_reference.md` — exact Ark image/video call signatures, the
  async task model, polling, and why first/last frames are used. Read this when
  changing API parameters or debugging responses.
- `references/troubleshooting.md` — auth/quota errors, slow async tasks, ffmpeg
  setup, re-running cleanly, and how cost is metered. Read this on any failure.
- `scripts/ark_common.py` — shared client/download/poll/manifest helpers the
  three top-level scripts import.
