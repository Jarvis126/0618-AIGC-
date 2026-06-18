#!/usr/bin/env python3
"""Frame-extraction QA for generated storyboard clips.

For each shot's clip, extracts start / middle / end frames, optionally compares
the generated keyframe stills against the video's boundary frames via grayscale
SSIM, and builds a contact sheet of every shot's middle frame so a human can
eyeball style drift, first/last-frame fidelity, and obvious glitches before
delivery. Writes qa_report.json.

Usage:
  python scripts/qa_storyboard.py config.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ark_common as ark  # noqa: E402,F401

FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = os.environ.get("FFPROBE") or shutil.which("ffprobe") or "ffprobe"


def probe(path: Path) -> dict[str, Any]:
    out = subprocess.check_output(
        [FFPROBE, "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height,pix_fmt,sample_rate,channels",
         "-of", "json", str(path)],
        text=True,
    )
    return json.loads(out)


def duration(path: Path) -> float:
    return float(probe(path)["format"]["duration"])


def extract_frame(video: Path, timestamp: float, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [FFMPEG, "-y", "-ss", f"{timestamp:.3f}", "-i", str(video),
         "-frames:v", "1", "-q:v", "2", str(output)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def compare_ssim(reference: Path | None, candidate: Path) -> float | None:
    if not reference or not reference.exists() or not candidate.exists():
        return None
    result = subprocess.run(
        [FFMPEG, "-i", str(reference), "-i", str(candidate), "-lavfi",
         "[0:v]scale=320:180,format=gray[ref];[1:v]scale=320:180,format=gray[cmp];[ref][cmp]ssim",
         "-f", "null", "-"],
        check=True, text=True, capture_output=True,
    )
    match = re.search(r"All:([0-9.]+)", result.stderr)
    return float(match.group(1)) if match else None


def make_contact_sheet(frames: list[Path], output: Path, qa_root: Path) -> None:
    if not frames:
        return
    list_file = qa_root / "contact_sheet_inputs.txt"
    list_file.write_text("".join(f"file '{p}'\n" for p in frames), encoding="utf-8")
    cols = 3
    rows = (len(frames) + cols - 1) // cols
    subprocess.run(
        [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
         "-vf", f"scale=320:180,tile={cols}x{rows}:margin=8:padding=6:color=white",
         "-frames:v", "1", str(output)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def find_image(folder: Path, name: str | None) -> Path | None:
    if not name:
        return None
    for suffix in (".jpg", ".jpeg", ".png", ""):
        path = folder / f"{name}{suffix}"
        if path.exists():
            return path
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    out_root = Path(config.get("out_root", f"outputs/{config.get('project_name', 'storyboard')}")).resolve()
    qa_root = out_root / "qa_frames"
    qa_root.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "qa_method": "ffmpeg extracts start/middle/end frames; keyframe stills vs "
                     "video boundary frames compared with grayscale SSIM; contact "
                     "sheet built for fast human review.",
        "shots": [],
    }
    middle_frames: list[Path] = []

    for shot in config["shots"]:
        folder = out_root / shot["folder_name"]
        names = shot.get("clips") or [shot["video_name"]]
        for name in names:
            video = folder / name
            if not video.exists():
                report["shots"].append({"clip": str(video), "error": "missing"})
                continue
            stem = Path(name).stem
            dur = duration(video)
            start_f = qa_root / f"{stem}_start.jpg"
            mid_f = qa_root / f"{stem}_middle.jpg"
            end_f = qa_root / f"{stem}_end.jpg"
            extract_frame(video, 0.15, start_f)
            extract_frame(video, dur / 2, mid_f)
            extract_frame(video, max(dur - 0.2, 0.0), end_f)
            middle_frames.append(mid_f)

            first, last = None, None
            for im in shot.get("images", []):
                if im.get("role") == "first_frame":
                    first = im["name"]
                if im.get("role") == "last_frame":
                    last = im["name"]
            if first is None and shot.get("images"):
                first = shot["images"][0]["name"]
            if last is None and len(shot.get("images", [])) > 1:
                last = shot["images"][-1]["name"]

            report["shots"].append({
                "shot_id": shot["id"],
                "clip": str(video),
                "duration_seconds": round(dur, 3),
                "frames": {"start": str(start_f), "middle": str(mid_f), "end": str(end_f)},
                "boundary_ssim": {
                    "first_image_vs_start": compare_ssim(find_image(folder, first), start_f),
                    "last_image_vs_end": compare_ssim(find_image(folder, last), end_f),
                },
            })

    contact_sheet = qa_root / "middle_frames_overview.jpg"
    make_contact_sheet(middle_frames, contact_sheet, qa_root)
    report["contact_sheet"] = str(contact_sheet)

    final = out_root / f"{config.get('project_name', 'storyboard')}_final.mp4"
    if final.exists():
        report["final_video"] = {"path": str(final), "probe": probe(final)}

    report_path = qa_root / "qa_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"report": str(report_path), "contact_sheet": str(contact_sheet)},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
