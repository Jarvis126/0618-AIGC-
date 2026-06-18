#!/usr/bin/env python3
"""Extract QA frames and compare generated stills with video boundary frames."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT = REPO_ROOT / "outputs" / "软件谷的隐藏接口_分镜视频"
QA_ROOT = ROOT / "质检抽帧"
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = os.environ.get("FFPROBE") or shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"


@dataclass(frozen=True)
class ShotQa:
    shot_id: str
    video: Path
    first_image: Path | None
    last_image: Path | None


SHOTS = [
    ShotQa("01", ROOT / "分镜 01 - 开场" / "分镜01_开场.mp4", ROOT / "分镜 01 - 开场" / "image_01_1.jpg", ROOT / "分镜 01 - 开场" / "image_01_3.jpg"),
    ShotQa("02", ROOT / "分镜 02 - 清晨" / "分镜02_清晨.mp4", ROOT / "分镜 02 - 清晨" / "图02-1.jpg", ROOT / "分镜 02 - 清晨" / "图02-2.jpg"),
    ShotQa("03", ROOT / "分镜 03 - 早高峰" / "分镜03_早高峰.mp4", ROOT / "分镜 03 - 早高峰" / "图03-1.jpg", ROOT / "分镜 03 - 早高峰" / "图03-2.jpg"),
    ShotQa("04", ROOT / "分镜 04 - 路径规划" / "分镜04_路径规划.mp4", ROOT / "分镜 04 - 路径规划" / "图04-1.jpg", ROOT / "分镜 04 - 路径规划" / "图04-2.jpg"),
    ShotQa("05", ROOT / "分镜 05 - 负载均衡" / "分镜05_负载均衡.mp4", ROOT / "分镜 05 - 负载均衡" / "图05-1.jpg", ROOT / "分镜 05 - 负载均衡" / "图05-2.jpg"),
    ShotQa("06", ROOT / "分镜 06 - 推荐系统" / "分镜06_推荐系统.mp4", ROOT / "分镜 06 - 推荐系统" / "图06-1.jpg", ROOT / "分镜 06 - 推荐系统" / "图06-2.jpg"),
    ShotQa("07A", ROOT / "分镜 07 - 傍晚" / "分镜07A_傍晚上半.mp4", ROOT / "分镜 07 - 傍晚" / "图07-1.jpg", ROOT / "分镜 07 - 傍晚" / "图07-2.jpg"),
    ShotQa("07B", ROOT / "分镜 07 - 傍晚" / "分镜07B_傍晚下半.mp4", ROOT / "分镜 07 - 傍晚" / "图07-2.jpg", ROOT / "分镜 07 - 傍晚" / "图07-3.jpg"),
    ShotQa("08A", ROOT / "分镜 08 - 冷备" / "分镜08A_深夜城市俯冲.mp4", ROOT / "分镜 08 - 冷备" / "图08-1.jpg", None),
    ShotQa("08B", ROOT / "分镜 08 - 冷备" / "分镜08B_深夜走廊穿行.mp4", ROOT / "分镜 08 - 冷备" / "图08-2.jpg", ROOT / "分镜 08 - 冷备" / "图08-3.jpg"),
    ShotQa("09", ROOT / "分镜 09 - 结尾" / "分镜09_结尾.mp4", ROOT / "分镜 09 - 结尾" / "图09-1.jpg", ROOT / "分镜 09 - 结尾" / "图09-2.jpg"),
]


def probe(path: Path) -> dict[str, object]:
    output = subprocess.check_output(
        [
            FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height,pix_fmt,sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    return json.loads(output)


def duration(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def extract_frame(video: Path, timestamp: float, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            FFMPEG,
            "-y",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def compare_ssim(reference: Path, candidate: Path) -> float | None:
    if not reference or not reference.exists() or not candidate.exists():
        return None
    command = [
        FFMPEG,
        "-i",
        str(reference),
        "-i",
        str(candidate),
        "-lavfi",
        "[0:v]scale=320:180,format=gray[ref];[1:v]scale=320:180,format=gray[cmp];[ref][cmp]ssim",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(command, check=True, text=True, capture_output=True)
    match = re.search(r"All:([0-9.]+)", result.stderr)
    return float(match.group(1)) if match else None


def make_contact_sheet(frame_paths: list[Path], output: Path) -> None:
    list_file = QA_ROOT / "contact_sheet_inputs.txt"
    list_file.write_text("".join(f"file '{path}'\n" for path in frame_paths), encoding="utf-8")
    subprocess.run(
        [
            FFMPEG,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-vf",
            "scale=320:180,tile=3x11:margin=8:padding=6:color=white",
            "-frames:v",
            "1",
            str(output),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    QA_ROOT.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "qa_method": "ffmpeg 抽首帧/中帧/尾帧；关键帧图片与视频边界抽帧做灰度 SSIM 对比；生成 contact sheet 供人工快速复核。",
        "shots": [],
    }
    middle_frames: list[Path] = []

    for shot in SHOTS:
        dur = duration(shot.video)
        start_frame = QA_ROOT / f"{shot.shot_id}_start.jpg"
        mid_frame = QA_ROOT / f"{shot.shot_id}_middle.jpg"
        end_frame = QA_ROOT / f"{shot.shot_id}_end.jpg"
        extract_frame(shot.video, 0.15, start_frame)
        extract_frame(shot.video, dur / 2, mid_frame)
        extract_frame(shot.video, max(dur - 0.2, 0.0), end_frame)
        middle_frames.append(mid_frame)
        report["shots"].append(
            {
                "shot_id": shot.shot_id,
                "video": str(shot.video),
                "duration_seconds": round(dur, 3),
                "frames": {
                    "start": str(start_frame),
                    "middle": str(mid_frame),
                    "end": str(end_frame),
                },
                "boundary_ssim": {
                    "first_image_vs_start_frame": compare_ssim(shot.first_image, start_frame),
                    "last_image_vs_end_frame": compare_ssim(shot.last_image, end_frame) if shot.last_image else None,
                },
            }
        )

    contact_sheet = QA_ROOT / "全片分镜中帧总览.jpg"
    make_contact_sheet(middle_frames, contact_sheet)
    final_video = ROOT / "软件谷的隐藏接口_全自动API成片_叠化版.mp4"
    report["final_video"] = {
        "path": str(final_video),
        "probe": probe(final_video),
    }
    report["contact_sheet"] = str(contact_sheet)
    report_path = QA_ROOT / "qa_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"report": str(report_path), "contact_sheet": str(contact_sheet)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
