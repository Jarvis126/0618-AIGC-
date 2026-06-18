#!/usr/bin/env python3
"""Stitch a storyboard's clips into one final video with gentle crossfades.

Reads the same storyboard JSON config used for generation, finds each shot's
rendered clip, then uses ffmpeg xfade (video) + acrossfade (audio) to join them
with a short dissolve between every pair. Writes final_stitch_manifest.json with
per-clip durations and the estimated vs. actual output length.

Usage:
  python scripts/stitch_storyboard.py config.json
  python scripts/stitch_storyboard.py config.json --transition 0.45
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ark_common as ark  # noqa: E402,F401  (kept for consistent imports)

FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = os.environ.get("FFPROBE") or shutil.which("ffprobe") or "ffprobe"


def duration(path: Path) -> float:
    out = subprocess.check_output(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        text=True,
    )
    return float(json.loads(out)["format"]["duration"])


def collect_clips(config: dict[str, Any], out_root: Path) -> list[Path]:
    """One clip per shot, in config order. A shot may declare extra `clips`."""
    clips: list[Path] = []
    for shot in config["shots"]:
        folder = out_root / shot["folder_name"]
        names = shot.get("clips") or [shot["video_name"]]
        for name in names:
            clips.append(folder / name)
    return clips


def build_filter(clips: list[Path], durations: list[float], transition: float) -> str:
    filters: list[str] = []
    for i in range(len(clips)):
        filters.append(
            f"[{i}:v]scale=1280:720:force_original_aspect_ratio=increase,"
            f"crop=1280:720,fps=30,format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[v{i}]"
        )
        filters.append(
            f"[{i}:a]aformat=sample_fmts=fltp:sample_rates=44100:"
            f"channel_layouts=stereo,asetpts=PTS-STARTPTS[a{i}]"
        )

    current_v, elapsed = "v0", durations[0]
    for i in range(1, len(clips)):
        offset = elapsed - transition
        filters.append(
            f"[{current_v}][v{i}]xfade=transition=fade:"
            f"duration={transition}:offset={offset:.3f}[xv{i}]"
        )
        current_v = f"xv{i}"
        elapsed += durations[i] - transition

    current_a = "a0"
    for i in range(1, len(clips)):
        filters.append(
            f"[{current_a}][a{i}]acrossfade=d={transition}:c1=tri:c2=tri[xa{i}]"
        )
        current_a = f"xa{i}"

    filters.append(f"[{current_v}]format=yuv420p[vout]")
    filters.append(f"[{current_a}]acopy[aout]")
    return ";".join(filters)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config")
    parser.add_argument("--transition", type=float, default=None,
                        help="Crossfade seconds (default: config or 0.45).")
    parser.add_argument("--output", default=None, help="Override output path.")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    out_root = Path(config.get("out_root", f"outputs/{config.get('project_name', 'storyboard')}")).resolve()
    transition = args.transition if args.transition is not None else config.get("transition_seconds", 0.45)

    clips = collect_clips(config, out_root)
    missing = [c for c in clips if not c.exists()]
    if missing:
        raise FileNotFoundError("Missing clips:\n" + "\n".join(str(c) for c in missing))

    durations = [duration(c) for c in clips]
    output = Path(args.output) if args.output else out_root / f"{config.get('project_name', 'storyboard')}_final.mp4"

    command = [FFMPEG, "-y"]
    for clip in clips:
        command += ["-i", str(clip)]
    command += [
        "-filter_complex", build_filter(clips, durations, transition),
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(output),
    ]
    subprocess.run(command, check=True)

    summary = {
        "output": str(output),
        "transition_seconds": transition,
        "clips": [{"path": str(c), "duration": d} for c, d in zip(clips, durations)],
        "source_duration_seconds": round(sum(durations), 3),
        "estimated_output_seconds": round(sum(durations) - transition * (len(clips) - 1), 3),
        "actual_output_seconds": round(duration(output), 3),
    }
    (out_root / "final_stitch_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
