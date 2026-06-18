# Troubleshooting & cost notes

## Common errors

| Symptom | Cause | Fix |
|---|---|---|
| `ARK_API_KEY is not set` | env var missing | `export ARK_API_KEY="..."` (don't commit it) |
| Permission / quota error from API | Seedream or Seedance not enabled, or no resource pack | Enable both models in the Ark console; bind an active quota; confirm the key's account matches |
| "must stop automatic inference limit first" | auto model inference limit is on | Turn off the automatic inference limit, then set the model quota manually |
| Video task stays `queued`/`running` for a long time | Seedance is async; queues during peak hours | Increase `--timeout` (e.g. 3600) and `--poll-interval`; the manifest keeps the task id so you can re-poll |
| Download fails / TLS cert error | local Python cert chain issue | The downloader falls back to `curl`; or update system certs |
| `ffmpeg`/`ffprobe` not found | not installed or off PATH | install ffmpeg; or set `FFMPEG` / `FFPROBE` env vars |
| Narration voice differs between shots | each clip generates its own audio | Pin one voice in `voice_style`; if needed, post-process to a single narration track |
| Visual style wanders | generative randomness | Pin a `style_prefix`, rely on first/last-frame constraints, and re-run individual shots that fail QA |

## Re-running cleanly

- The pipeline is **idempotent per shot**. Re-run a single bad shot with
  `--shots 03` instead of regenerating everything.
- `--skip-existing-images` reuses keyframe stills already on disk and only
  (re)creates the video task — useful when the images are good but the clip isn't.
- Every shot folder keeps `manifest_<id>.json` with the task id, prompts, and
  model ids, so failures are traceable and prompts are reproducible.

## Cost

Cost is **metered by Volcengine**, not by these scripts — the manifests record
model ids and task ids for reconciliation, but never hardcode prices.

To split image vs. video spend: export the bill from the Ark billing center,
group by model id, attribute `doubao-seedream-*` to image generation and
`doubao-seedance-*` to video generation, and cross-check against the task ids
saved in the manifests.

Rough order of magnitude from the original reference project: ~21 keyframe
images + ~11 video tasks for a ~9-shot, ~2-minute film came to ~¥120 total. Your
cost scales with shot count, durations, resolution, and how many re-runs QA
forces — treat any single figure as indicative, not a quote.

## Always dry-run first

`--dry-run` writes all manifests and resolves prompts **without any API calls or
cost**. Run it, read the manifests, confirm prompts and first/last-frame
assignments look right, and only then run for real.
