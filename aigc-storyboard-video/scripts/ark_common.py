#!/usr/bin/env python3
"""Shared helpers for the Volcengine Ark AIGC storyboard pipeline.

This module centralizes everything that the original repo duplicated across
scripts: building the Ark client, robust downloading, async task polling,
manifest writing, and image <-> data-url conversion. The generation, stitch,
and QA scripts all import from here so the per-shot logic stays small.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

# Default Ark endpoint and models. Override per-project via the storyboard
# config (image_model / video_model) or via CLI flags.
BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_IMAGE_MODEL = "doubao-seedream-4-0-250828"
DEFAULT_VIDEO_MODEL = "doubao-seedance-2-0-260128"


def ensure_key() -> str:
    """Return the Ark API key or raise a clear, actionable error."""
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ARK_API_KEY is not set. Export it first, e.g. "
            'export ARK_API_KEY="your-volcengine-ark-key"'
        )
    return api_key


def make_client(api_key: str | None = None, base_url: str = BASE_URL):
    """Build an Ark client. Imported lazily so --dry-run needs no SDK."""
    from volcenginesdkarkruntime import Ark  # noqa: PLC0415

    return Ark(base_url=base_url, api_key=api_key or ensure_key())


def to_plain(obj: Any) -> Any:
    """Recursively turn SDK model objects into JSON-serializable values."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [to_plain(item) for item in obj]
    if isinstance(obj, dict):
        return {key: to_plain(value) for key, value in obj.items()}
    return obj


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def download_url(url: str, path: Path) -> None:
    """Download a URL, falling back to curl on TLS certificate failures."""
    path.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=120) as response:
            path.write_bytes(response.read())
    except URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        subprocess.run(
            ["curl", "-fL", "--retry", "3", "--connect-timeout", "30",
             "--max-time", "600", "-A", "Mozilla/5.0", "-o", str(path), url],
            check=True,
        )


def image_response_to_url(image_response: Any) -> tuple[str, str | None]:
    """Extract a usable url (http or data:) and size from an images response."""
    data = getattr(image_response, "data", None)
    if not data:
        raise RuntimeError(f"Image response has no data: {to_plain(image_response)}")
    first = data[0]
    url = getattr(first, "url", None)
    b64_json = getattr(first, "b64_json", None)
    size = getattr(first, "size", None)
    if url:
        return url, size
    if b64_json:
        return "data:image/png;base64," + b64_json, size
    raise RuntimeError(
        f"Image response has neither url nor b64_json: {to_plain(image_response)}"
    )


def save_data_image(data_url: str, path: Path) -> None:
    header, encoded = data_url.split(",", 1)
    if "base64" not in header:
        raise ValueError("Only base64 data URLs are supported")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(encoded))


def local_image_as_data_url(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def generate_image(client, *, model: str, prompt: str, size: str) -> tuple[str, str | None]:
    """Call Seedream and return (url_or_data_url, size)."""
    response = client.images.generate(
        model=model,
        prompt=prompt,
        size=size,
        response_format="url",
        watermark=False,
        sequential_image_generation="disabled",
        timeout=600,
    )
    return image_response_to_url(response)


def create_video_task(
    client,
    *,
    model: str,
    prompt: str,
    first_frame_url: str,
    last_frame_url: str | None,
    resolution: str,
    ratio: str,
    duration: int,
    generate_audio: bool = True,
):
    """Create a Seedance async video task constrained by first/last frames."""
    content: list[dict[str, Any]] = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": first_frame_url}, "role": "first_frame"},
    ]
    if last_frame_url:
        content.append(
            {"type": "image_url", "image_url": {"url": last_frame_url}, "role": "last_frame"}
        )
    return client.content_generation.tasks.create(
        model=model,
        content=content,
        resolution=resolution,
        ratio=ratio,
        duration=duration,
        watermark=False,
        generate_audio=generate_audio,
        return_last_frame=True,
        timeout=120,
    )


def poll_video_task(client, task_id: str, *, poll_interval: int, timeout: int):
    """Poll an async task until it reaches a terminal state or times out."""
    deadline = time.time() + timeout
    while True:
        task = client.content_generation.tasks.get(task_id=task_id, timeout=120)
        status = getattr(task, "status", None)
        print(f"Task {task_id}: {status}", flush=True)
        if status in {"succeeded", "failed", "cancelled"}:
            return task
        if time.time() >= deadline:
            raise TimeoutError(f"Task {task_id} did not finish within {timeout}s")
        time.sleep(poll_interval)


def task_video_url(task) -> str | None:
    content = getattr(task, "content", None)
    return getattr(content, "video_url", None) if content else None
