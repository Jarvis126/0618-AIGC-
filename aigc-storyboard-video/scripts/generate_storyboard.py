#!/usr/bin/env python3
"""Generate every shot in a storyboard via Volcengine Ark (Seedream + Seedance).

Reads a single JSON storyboard config (see assets/storyboard.example.json) and,
for each shot:
  1. Generates the shot's keyframe images with Seedream.
  2. Creates a Seedance async video task constrained by the first/last frame.
  3. Polls until the task finishes and downloads the clip.
  4. Writes a per-shot manifest_<id>.json recording models, prompts, task ids,
     image URLs and local paths so runs are reproducible and auditable.

Usage:
  python scripts/generate_storyboard.py config.json --dry-run   # no API cost
  python scripts/generate_storyboard.py config.json             # all shots
  python scripts/generate_storyboard.py config.json --shots 01 02
  python scripts/generate_storyboard.py config.json --skip-existing-images
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ark_common as ark  # noqa: E402


def load_config(path: Path) -> dict[str, Any]:
    import json

    config = json.loads(path.read_text(encoding="utf-8"))
    config.setdefault("image_model", ark.DEFAULT_IMAGE_MODEL)
    config.setdefault("video_model", ark.DEFAULT_VIDEO_MODEL)
    config.setdefault("image_size", "1280x720")
    config.setdefault("resolution", "720p")
    config.setdefault("ratio", "16:9")
    config.setdefault("generate_audio", True)
    config.setdefault("style_prefix", "")
    config.setdefault("base_url", ark.BASE_URL)
    if "out_root" not in config:
        config["out_root"] = f"outputs/{config.get('project_name', 'storyboard')}"
    return config


def image_prompt(config: dict[str, Any], image: dict[str, Any]) -> str:
    """Prepend the shared style prefix unless the image opts out or repeats it."""
    prefix = config.get("style_prefix", "")
    base = image["prompt"]
    if prefix and image.get("apply_style_prefix", True) and prefix not in base:
        return f"{prefix} {base}"
    return base


def resolve_frames(images: list[dict[str, Any]]) -> tuple[dict | None, dict | None]:
    """Pick first/last frame images. Explicit roles win; else first & last."""
    first = next((im for im in images if im.get("role") == "first_frame"), None)
    last = next((im for im in images if im.get("role") == "last_frame"), None)
    if first is None and images:
        first = images[0]
    if last is None and len(images) > 1:
        last = images[-1]
    return first, last


def public_images(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strip bulky inline data URLs before writing the manifest."""
    out = []
    for image in images:
        item = dict(image)
        if (item.get("url") or "").startswith("data:image"):
            item["url"] = "[local data URL omitted]"
        item.pop("prompt_full", None)
        out.append(item)
    return out


def image_path_for(folder: Path, name: str) -> Path | None:
    for suffix in (".jpg", ".jpeg", ".png"):
        path = folder / f"{name}{suffix}"
        if path.exists():
            return path
    return None


def generate_shot_images(client, config, shot, folder: Path, skip_existing: bool) -> None:
    for image in shot["images"]:
        existing = image_path_for(folder, image["name"])
        if skip_existing and existing:
            image["local_path"] = str(existing)
            image["url"] = ark.local_image_as_data_url(existing)
            continue
        print(f"[{shot['id']}] image: {image['name']}", flush=True)
        url, size = ark.generate_image(
            client,
            model=config["image_model"],
            prompt=image_prompt(config, image),
            size=config["image_size"],
        )
        image["url"], image["size"] = url, size
        suffix = ".png" if url.startswith("data:image") else ".jpg"
        local_path = folder / f"{image['name']}{suffix}"
        if url.startswith("data:image"):
            ark.save_data_image(url, local_path)
        else:
            ark.download_url(url, local_path)
        image["local_path"] = str(local_path)


def generate_shot(client, config, shot, out_root: Path, args) -> int:
    folder = out_root / shot["folder_name"]
    folder.mkdir(parents=True, exist_ok=True)
    manifest_path = folder / f"manifest_{shot['id']}.json"
    manifest: dict[str, Any] = {
        "shot": shot["id"],
        "folder_name": shot["folder_name"],
        "image_model": config["image_model"],
        "video_model": config["video_model"],
        "image_size": config["image_size"],
        "video": {
            "prompt": shot["video_prompt"],
            "resolution": config["resolution"],
            "ratio": config["ratio"],
            "duration": shot["duration"],
            "generate_audio": config["generate_audio"],
            "watermark": False,
        },
        "status": "dry_run" if args.dry_run else "started",
        "created_at": int(time.time()),
    }

    if args.dry_run:
        manifest["images"] = public_images(shot["images"])
        ark.write_json(manifest_path, manifest)
        print(f"[{shot['id']}] dry-run manifest -> {manifest_path}")
        return 0

    try:
        generate_shot_images(client, config, shot, folder, args.skip_existing_images)
        manifest["images"] = public_images(shot["images"])
        ark.write_json(manifest_path, manifest)

        first, last = resolve_frames(shot["images"])
        if not first or not first.get("url"):
            raise RuntimeError(f"Shot {shot['id']} has no usable first frame.")
        create = ark.create_video_task(
            client,
            model=config["video_model"],
            prompt=shot["video_prompt"],
            first_frame_url=first["url"],
            last_frame_url=last["url"] if last else None,
            resolution=config["resolution"],
            ratio=config["ratio"],
            duration=shot["duration"],
            generate_audio=config["generate_audio"],
        )
        task_id = getattr(create, "id", None)
        if not task_id:
            raise RuntimeError(f"Create task response has no id: {ark.to_plain(create)}")
        manifest["video"]["task_id"] = task_id
        manifest["video"]["create_response"] = ark.to_plain(create)
        manifest["status"] = "video_task_created"
        ark.write_json(manifest_path, manifest)

        task = ark.poll_video_task(
            client, task_id, poll_interval=args.poll_interval, timeout=args.timeout
        )
        manifest["video"]["task"] = ark.to_plain(task)
        manifest["status"] = getattr(task, "status", "unknown")

        video_url = ark.task_video_url(task)
        if manifest["status"] == "succeeded" and video_url:
            video_path = folder / shot["video_name"]
            ark.download_url(video_url, video_path)
            manifest["video"]["url"] = video_url
            manifest["video"]["local_path"] = str(video_path)
        elif manifest["status"] == "succeeded":
            raise RuntimeError("Task succeeded but returned no video_url.")

        ark.write_json(manifest_path, manifest)
        return 0 if manifest["status"] == "succeeded" else 2
    except Exception as exc:  # noqa: BLE001 - record then re-raise
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        manifest.setdefault("images", public_images(shot["images"]))
        ark.write_json(manifest_path, manifest)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="Path to the storyboard JSON config.")
    parser.add_argument("--shots", nargs="+", help="Subset of shot ids to run.")
    parser.add_argument("--skip-existing-images", action="store_true",
                        help="Reuse keyframe images already present on disk.")
    parser.add_argument("--poll-interval", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--dry-run", action="store_true",
                        help="Write manifests only, make no API calls.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(Path(args.config).resolve())
    out_root = Path(config["out_root"]).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    by_id = {shot["id"]: shot for shot in config["shots"]}
    shot_ids = args.shots or [shot["id"] for shot in config["shots"]]
    unknown = [s for s in shot_ids if s not in by_id]
    if unknown:
        raise SystemExit(f"Unknown shot ids: {unknown}. Available: {list(by_id)}")

    client = None if args.dry_run else ark.make_client(base_url=config["base_url"])

    exit_code = 0
    for shot_id in shot_ids:
        result = generate_shot(client, config, by_id[shot_id], out_root, args)
        if result != 0:
            exit_code = result
            break
    print(f"Output root: {out_root}", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
