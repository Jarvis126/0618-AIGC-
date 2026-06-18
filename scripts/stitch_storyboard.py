#!/usr/bin/env python3
"""Stitch generated storyboard clips into one final video with gentle crossfades."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT = REPO_ROOT / "outputs" / "软件谷的隐藏接口_分镜视频"
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = os.environ.get("FFPROBE") or shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
TRANSITION_SECONDS = 0.45

CLIPS = [
    ROOT / "分镜 01 - 开场" / "分镜01_开场.mp4",
    ROOT / "分镜 02 - 清晨" / "分镜02_清晨.mp4",
    ROOT / "分镜 03 - 早高峰" / "分镜03_早高峰.mp4",
    ROOT / "分镜 04 - 路径规划" / "分镜04_路径规划.mp4",
    ROOT / "分镜 05 - 负载均衡" / "分镜05_负载均衡.mp4",
    ROOT / "分镜 06 - 推荐系统" / "分镜06_推荐系统.mp4",
    ROOT / "分镜 07 - 傍晚" / "分镜07A_傍晚上半.mp4",
    ROOT / "分镜 07 - 傍晚" / "分镜07B_傍晚下半.mp4",
    ROOT / "分镜 08 - 冷备" / "分镜08A_深夜城市俯冲.mp4",
    ROOT / "分镜 08 - 冷备" / "分镜08B_深夜走廊穿行.mp4",
    ROOT / "分镜 09 - 结尾" / "分镜09_结尾.mp4",
]


def duration(path: Path) -> float:
    output = subprocess.check_output(
        [
            FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    return float(json.loads(output)["format"]["duration"])


def build_filter(durations: list[float]) -> str:
    filters: list[str] = []
    for index in range(len(CLIPS)):
        filters.append(
            f"[{index}:v]scale=1280:720:force_original_aspect_ratio=increase,"
            f"crop=1280:720,fps=30,format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[v{index}]"
        )
        filters.append(
            f"[{index}:a]aformat=sample_fmts=fltp:sample_rates=44100:"
            f"channel_layouts=stereo,asetpts=PTS-STARTPTS[a{index}]"
        )

    current_v = "v0"
    elapsed = durations[0]
    for index in range(1, len(CLIPS)):
        out_v = f"xv{index}"
        offset = elapsed - TRANSITION_SECONDS
        filters.append(
            f"[{current_v}][v{index}]xfade=transition=fade:"
            f"duration={TRANSITION_SECONDS}:offset={offset:.3f}[{out_v}]"
        )
        current_v = out_v
        elapsed += durations[index] - TRANSITION_SECONDS

    current_a = "a0"
    for index in range(1, len(CLIPS)):
        out_a = f"xa{index}"
        filters.append(
            f"[{current_a}][a{index}]acrossfade=d={TRANSITION_SECONDS}:c1=tri:c2=tri[{out_a}]"
        )
        current_a = out_a

    filters.append(f"[{current_v}]format=yuv420p[vout]")
    filters.append(f"[{current_a}]acopy[aout]")
    return ";".join(filters)


def main() -> int:
    missing = [path for path in CLIPS if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing clips:\n" + "\n".join(str(path) for path in missing))

    durations = [duration(path) for path in CLIPS]
    output = ROOT / "软件谷的隐藏接口_全自动API成片_叠化版.mp4"
    summary = {
        "output": str(output),
        "transition_seconds": TRANSITION_SECONDS,
        "clips": [{"path": str(path), "duration": dur} for path, dur in zip(CLIPS, durations, strict=True)],
        "source_duration_seconds": round(sum(durations), 3),
        "estimated_output_seconds": round(sum(durations) - TRANSITION_SECONDS * (len(CLIPS) - 1), 3),
    }

    command = [FFMPEG, "-y"]
    for path in CLIPS:
        command.extend(["-i", str(path)])
    command.extend(
        [
            "-filter_complex",
            build_filter(durations),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )

    subprocess.run(command, check=True)
    summary["actual_output_seconds"] = round(duration(output), 3)
    (ROOT / "final_stitch_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
