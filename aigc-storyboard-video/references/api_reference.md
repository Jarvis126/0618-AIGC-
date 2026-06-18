# Volcengine Ark API reference (for this skill)

This skill talks to Volcengine Ark (火山方舟) through the official
`volcengine-python-sdk[ark]` package. Two model families are used:

| Stage | Model family | Default model | Endpoint |
|---|---|---|---|
| Keyframe images | Seedream | `doubao-seedream-4-0-250828` | `images.generate` |
| Shot videos | Seedance | `doubao-seedance-2-0-260128` | `content_generation.tasks.*` |

Base URL: `https://ark.cn-beijing.volces.com/api/v3`

## Authentication

The SDK reads the key from the `ARK_API_KEY` environment variable. Never commit
a real key. The account behind the key must have **both** the Seedream image
model and the Seedance video model enabled, with an active resource pack / quota.

```bash
export ARK_API_KEY="your-volcengine-ark-key"
```

## Image generation (Seedream)

```python
client.images.generate(
    model="doubao-seedream-4-0-250828",
    prompt="...",
    size="1280x720",
    response_format="url",          # returns a hosted URL (download promptly)
    watermark=False,
    sequential_image_generation="disabled",
    timeout=600,
)
```

The response exposes `data[0].url` (an http URL) or `data[0].b64_json`. The
helper `image_response_to_url` handles both and normalizes b64 into a
`data:image/png;base64,...` data URL.

## Video generation (Seedance) — async task model

Seedance is **asynchronous**: you create a task, then poll until it reaches a
terminal status. Frames are passed inside the `content` array with a `role`:

```python
task = client.content_generation.tasks.create(
    model="doubao-seedance-2-0-260128",
    content=[
        {"type": "text", "text": video_prompt},
        {"type": "image_url", "image_url": {"url": first_frame_url}, "role": "first_frame"},
        {"type": "image_url", "image_url": {"url": last_frame_url}, "role": "last_frame"},
    ],
    resolution="720p",
    ratio="16:9",
    duration=13,                    # seconds
    watermark=False,
    generate_audio=True,            # audio generated together with the video
    return_last_frame=True,
    timeout=120,
)
task_id = task.id
```

Poll:

```python
task = client.content_generation.tasks.get(task_id=task_id, timeout=120)
status = task.status   # queued / running / succeeded / failed / cancelled
video_url = task.content.video_url   # present when status == "succeeded"
```

Terminal statuses: `succeeded`, `failed`, `cancelled`. The helper
`poll_video_task` loops on a `poll_interval` until terminal or `timeout`.

## Why first/last frame constraints

Pure text-to-video drifts in style, subject, and camera. Generating the
first (and usually last) frame with Seedream first, then passing them as
`first_frame` / `last_frame`, makes the start and end of every clip controllable
and keeps shots inside one visual system — which also makes them stitch cleanly.

## Output sizing note

The stitch step normalizes every clip to 1280x720 @ 30fps before crossfading,
so mixed resolutions across shots still join cleanly. If you change `ratio` or
`resolution` for a project, update the scale/crop in `stitch_storyboard.py`
accordingly.
