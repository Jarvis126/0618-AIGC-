#!/usr/bin/env python3
"""Generate rebuilt storyboard shot 01 with Volcengine Ark.

Pipeline:
1. Generate three Seedream images for rebuilt shot 01.
2. Use image 01-1 as first_frame and image 01-3 as last_frame.
3. Create a Seedance video generation task.
4. Poll until completion and download the resulting video.
5. Write a manifest with prompts, task ids, URLs, and local paths.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = REPO_ROOT / "work" / "vendor"
if VENDOR_DIR.exists():
    sys.path.insert(0, str(VENDOR_DIR))

from volcenginesdkarkruntime import Ark  # noqa: E402


BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_IMAGE_MODEL = "doubao-seedream-4-0-250828"
DEFAULT_VIDEO_MODEL = "doubao-seedance-2-0-260128"


@dataclass
class GeneratedImage:
    name: str
    prompt: str
    url: str | None = None
    local_path: str | None = None
    size: str | None = None


SHOT01_IMAGES: list[GeneratedImage] = [
    GeneratedImage(
        name="image_01_1",
        prompt=(
            "中国新水墨风格，宣纸质感，水墨晕染与大留白，飞白笔触，电影感，16:9。"
            "极高空俯瞰江苏南京一带的山水与城市，长江如一条墨带自画面蜿蜒而过，"
            "江畔城市群以极淡墨线勾勒、隐于晨雾，山峦在远处淡墨起伏；"
            "大俯角、视野开阔，构图为后续俯冲推近留出纵深；冷青色调，宁静辽阔，"
            "无文字、无人脸。"
        ),
    ),
    GeneratedImage(
        name="image_01_2",
        prompt=(
            "中国新水墨风格，宣纸质感，水墨晕染，飞白笔触，电影感，16:9。"
            "镜头俯冲下压途中的斜俯视角，南京雨花台软件谷的现代高楼群迅速逼近、"
            "由远及近，楼宇以淡墨勾勒、带轻微运动模糊与速度感，晨光渐亮，"
            "水墨晕染随俯冲流动；强烈的纵深与下冲感，无文字、无人脸。"
        ),
    ),
    GeneratedImage(
        name="image_01_3",
        prompt=(
            "中国新水墨风格，宣纸质感，水墨晕染，电影感，16:9。"
            "俯冲落定后的软件谷城市天际线斜俯视角，城市上方与楼宇之间极淡的蓝色"
            "水墨网格线与发光墨点如墨入水般晕开、连成“数字接口”网络，"
            "可有一处极小英文 API；网格柔和不抢主体，承接下一镜，无大段文字、无人脸。"
        ),
    ),
]


SHOT01_VIDEO_PROMPT = (
    "开场镜头，13秒，中国新水墨风，16:9。以【图01-1】为首帧——极高空俯瞰南京一带的"
    "水墨山水与城市，长江如墨带蜿蜒。摄影机像纪录片航拍一样，从高空快速俯冲下压并"
    "持续向前推近（俯冲+推），强烈的下冲与纵深推进感，长江与城市迅速逼近，过渡到"
    "【图01-2】的斜俯视角；俯冲落定在软件谷城市天际线，城市上方浮现蓝色水墨接口网格，"
    "定格于【图01-3】。运动连贯有速度感、像水墨在镜头里流动，无剧烈抖动。\n\n"
    "UI生成要求：仅在落定阶段让淡蓝接口网格与发光墨点在城市上方自然晕开生长，"
    "仅极小英文 API，不要大段中文、不要密集数字，不依赖后期。\n\n"
    "同步音频（音画同出）：旁白用青年男声、标准普通话，清晰沉稳、有悬念、中速——"
    "「你有没有想过——你住的这座城，其实也是一台计算机？它会自检、会调度，在你看不见的"
    "地方运转一整天。这，就是南京雨花台软件谷。」API 读作 A-P-I。环境音：高空风声、"
    "城市远景环境声渐入。配乐：空灵古琴/弦乐，随俯冲推进而上扬，音量低于旁白。"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate rebuilt shot 01 via Volcengine Ark.")
    parser.add_argument("--out-dir", default="outputs/shot01", help="Directory for generated files.")
    parser.add_argument("--image-model", default=DEFAULT_IMAGE_MODEL)
    parser.add_argument("--video-model", default=DEFAULT_VIDEO_MODEL)
    parser.add_argument("--image-size", default="1280x720", help="Seedream output image size.")
    parser.add_argument("--resolution", default="720p", help="Seedance video resolution.")
    parser.add_argument("--ratio", default="16:9", help="Seedance video aspect ratio.")
    parser.add_argument("--duration", type=int, default=13, help="Seedance video duration in seconds.")
    parser.add_argument("--poll-interval", type=int, default=15)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument(
        "--video-only",
        action="store_true",
        help="Reuse existing local images in out-dir and only create/poll the video task.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Write manifest without API calls.")
    return parser.parse_args()


def ensure_key() -> str:
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        raise RuntimeError("ARK_API_KEY is not set. Run: source ~/.zshenv")
    return api_key


def to_plain(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, list):
        return [to_plain(item) for item in obj]
    if isinstance(obj, dict):
        return {key: to_plain(value) for key, value in obj.items()}
    return obj


def download_url(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=120) as response:
            path.write_bytes(response.read())
    except URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        subprocess.run(
            [
                "curl",
                "-fL",
                "--retry",
                "3",
                "--connect-timeout",
                "30",
                "--max-time",
                "600",
                "-A",
                "Mozilla/5.0",
                "-o",
                str(path),
                url,
            ],
            check=True,
        )


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


def get_image_url_or_b64_data(image_response: Any) -> tuple[str, str | None]:
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
    raise RuntimeError(f"Image response has neither url nor b64_json: {to_plain(image_response)}")


def save_data_image(data_url: str, path: Path) -> None:
    header, encoded = data_url.split(",", 1)
    if "base64" not in header:
        raise ValueError("Only base64 data URLs are supported")
    path.write_bytes(base64.b64decode(encoded))


def local_image_as_data_url(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def image_manifest_items() -> list[dict[str, Any]]:
    items = []
    for item in SHOT01_IMAGES:
        data = asdict(item)
        if (data.get("url") or "").startswith("data:image"):
            data["url"] = "[local data URL omitted]"
        items.append(data)
    return items


def load_existing_images(out_dir: Path, manifest: dict[str, Any]) -> None:
    for image in SHOT01_IMAGES:
        local_path = next(
            (out_dir / f"{image.name}{suffix}" for suffix in (".jpg", ".jpeg", ".png") if (out_dir / f"{image.name}{suffix}").exists()),
            None,
        )
        if local_path is None:
            raise FileNotFoundError(f"Missing local image for {image.name} in {out_dir}")
        image.local_path = str(local_path)
        image.url = local_image_as_data_url(local_path)
    manifest["images"] = image_manifest_items()
    write_manifest(out_dir / "manifest.json", manifest)


def generate_images(client: Ark, args: argparse.Namespace, out_dir: Path, manifest: dict[str, Any]) -> None:
    for image in SHOT01_IMAGES:
        print(f"Generating image: {image.name}", flush=True)
        response = client.images.generate(
            model=args.image_model,
            prompt=image.prompt,
            size=args.image_size,
            response_format="url",
            watermark=False,
            sequential_image_generation="disabled",
            timeout=600,
        )
        image.url, image.size = get_image_url_or_b64_data(response)
        suffix = ".png" if image.url.startswith("data:image") else ".jpg"
        local_path = out_dir / f"{image.name}{suffix}"
        if image.url.startswith("data:image"):
            save_data_image(image.url, local_path)
        else:
            download_url(image.url, local_path)
        image.local_path = str(local_path)
        manifest["images"] = image_manifest_items()
        write_manifest(out_dir / "manifest.json", manifest)


def create_video_task(client: Ark, args: argparse.Namespace) -> Any:
    first_frame = SHOT01_IMAGES[0].url
    last_frame = SHOT01_IMAGES[2].url
    if not first_frame or not last_frame:
        raise RuntimeError("Missing first or last frame URL.")
    content = [
        {"type": "text", "text": SHOT01_VIDEO_PROMPT},
        {"type": "image_url", "image_url": {"url": first_frame}, "role": "first_frame"},
        {"type": "image_url", "image_url": {"url": last_frame}, "role": "last_frame"},
    ]
    print("Creating video task", flush=True)
    return client.content_generation.tasks.create(
        model=args.video_model,
        content=content,
        resolution=args.resolution,
        ratio=args.ratio,
        duration=args.duration,
        watermark=False,
        generate_audio=True,
        return_last_frame=True,
        timeout=120,
    )


def poll_video_task(client: Ark, task_id: str, args: argparse.Namespace) -> Any:
    deadline = time.time() + args.timeout
    while True:
        task = client.content_generation.tasks.get(task_id=task_id, timeout=120)
        status = getattr(task, "status", None)
        print(f"Task {task_id}: {status}", flush=True)
        if status in {"succeeded", "failed", "cancelled"}:
            return task
        if time.time() >= deadline:
            raise TimeoutError(f"Task {task_id} did not finish within {args.timeout}s")
        time.sleep(args.poll_interval)


def main() -> int:
    args = parse_args()
    out_dir = (REPO_ROOT / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "shot": "01",
        "pipeline": "seedream-images-to-seedance-video",
        "base_url": BASE_URL,
        "image_model": args.image_model,
        "video_model": args.video_model,
        "image_size": args.image_size,
        "video": {
            "prompt": SHOT01_VIDEO_PROMPT,
            "resolution": args.resolution,
            "ratio": args.ratio,
            "duration": args.duration,
            "generate_audio": True,
            "watermark": False,
        },
        "images": image_manifest_items(),
        "status": "dry_run" if args.dry_run else "started",
        "created_at": int(time.time()),
    }
    write_manifest(out_dir / "manifest.json", manifest)

    if args.dry_run:
        print(f"Dry run manifest written to {out_dir / 'manifest.json'}")
        return 0

    api_key = ensure_key()
    client = Ark(base_url=BASE_URL, api_key=api_key)

    try:
        if args.video_only:
            print("Loading existing local images", flush=True)
            load_existing_images(out_dir, manifest)
        else:
            generate_images(client, args, out_dir, manifest)
        create_result = create_video_task(client, args)
        task_id = getattr(create_result, "id", None)
        if not task_id:
            raise RuntimeError(f"Create task response has no id: {to_plain(create_result)}")
        manifest["video"]["task_id"] = task_id
        manifest["status"] = "video_task_created"
        manifest["video"]["create_response"] = to_plain(create_result)
        write_manifest(out_dir / "manifest.json", manifest)

        task = poll_video_task(client, task_id, args)
        task_data = to_plain(task)
        manifest["video"]["task"] = task_data
        manifest["status"] = getattr(task, "status", "unknown")

        content = getattr(task, "content", None)
        video_url = getattr(content, "video_url", None) if content else None
        if manifest["status"] == "succeeded" and video_url:
            video_path = out_dir / "shot01.mp4"
            download_url(video_url, video_path)
            manifest["video"]["url"] = video_url
            manifest["video"]["local_path"] = str(video_path)
        elif manifest["status"] == "succeeded":
            raise RuntimeError(f"Task succeeded but no video_url was returned: {task_data}")

        write_manifest(out_dir / "manifest.json", manifest)
        print(f"Done. Manifest: {out_dir / 'manifest.json'}")
        return 0 if manifest["status"] == "succeeded" else 2
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        write_manifest(out_dir / "manifest.json", manifest)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
