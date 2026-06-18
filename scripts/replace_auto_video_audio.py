#!/usr/bin/env python3
"""Replace the auto-stitched video's original audio with unified narration and a new ambient bed."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT = REPO_ROOT / "outputs" / "软件谷的隐藏接口_分镜视频"
FINAL_VIDEO = ROOT / "软件谷的隐藏接口_全自动API成片_叠化版.mp4"
OUT_DIR = ROOT / "统一旁白音频替换"
FFMPEG = os.environ.get("FFMPEG") or shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = os.environ.get("FFPROBE") or shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
SAY = "/usr/bin/say"
VOICE = "Reed (中文（中国大陆）)"
TRANSITION_SECONDS = 0.45


@dataclass(frozen=True)
class Segment:
    sid: str
    duration: float
    text: str


SEGMENTS = [
    Segment("01", 13.072834, "你有没有想过——你住的这座城，其实也是一台计算机？它会自检，会调度，在你看不见的地方运转一整天。这，就是南京雨花台软件谷。"),
    Segment("02", 13.096009, "天没亮透，城市先醒了。街角的传感器一盏盏睁开眼，这是物联网。它们互相确认：每个节点都健康在线，城市，正式开机。"),
    Segment("03", 14.093991, "成千上万人同时出门，地铁、马路、电梯，同一刻涌入海量请求——这叫并发。系统提前预测，排好队列，再大的洪峰也稳稳接住。"),
    Segment("04", 13.096009, "街角的无人配送车不慌不忙。它脑子里跑着路径规划算法，在千万条路里，实时算出此刻最快的那一条。"),
    Segment("05", 13.096009, "正午最忙，订单、外卖、机械臂一起开动。城市从不把活全压给一台机器，谁闲就派给谁——这叫负载均衡。"),
    Segment("06", 13.072834, "你刷到的每条内容，背后都是大数据推荐。它把你的喜好和海量信息比对，在你开口前，就把你想要的，推到眼前。"),
    Segment("07A", 8.057007, "夕阳西下，一天的数据开始回传、汇聚。无人机升空，把数字翻译成光。"),
    Segment("07B", 9.101995, "一根根柱状图腾空，散作整片星河——这就是数据可视化。"),
    Segment("08A", 6.082993, "城市安静了，计算机却不真正休眠。数据中心进入冷备，压低呼吸。"),
    Segment("08B", 7.058866, "悄悄备份。万一出错，总有一份副本，在黑暗里替你守着。"),
    Segment("09", 11.051995, "从清晨到深夜，这些接口你天天在用，却从没看见。读懂它们，你才发现：这座城，一直在为你安静地思考。"),
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


def synthesize_say(text: str, output: Path, rate: int) -> None:
    subprocess.run([SAY, "-v", VOICE, "-r", str(rate), "-o", str(output), text], check=True)


def convert_to_wav(input_path: Path, output_path: Path, target_duration: float) -> None:
    subprocess.run(
        [
            FFMPEG,
            "-y",
            "-i",
            str(input_path),
            "-af",
            f"apad=pad_dur=0.2,atrim=0:{target_duration:.3f},afade=t=in:st=0:d=0.08,afade=t=out:st={max(target_duration - 0.18, 0):.3f}:d=0.18,volume=1.25",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(output_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def make_narration(segment: Segment, target_duration: float) -> dict[str, object]:
    aiff = OUT_DIR / "narration_raw" / f"{segment.sid}.aiff"
    wav = OUT_DIR / "narration_wav" / f"{segment.sid}.wav"
    aiff.parent.mkdir(parents=True, exist_ok=True)
    wav.parent.mkdir(parents=True, exist_ok=True)

    selected_rate = 170
    selected_duration = 0.0
    for rate in range(150, 281, 10):
        synthesize_say(segment.text, aiff, rate)
        selected_duration = duration(aiff)
        selected_rate = rate
        if selected_duration <= target_duration:
            break

    convert_to_wav(aiff, wav, target_duration=max(selected_duration, min(target_duration, selected_duration + 0.25)))
    return {
        "sid": segment.sid,
        "voice": VOICE,
        "rate": selected_rate,
        "raw_duration": round(selected_duration, 3),
        "target_duration": round(target_duration, 3),
        "wav": str(wav),
        "text": segment.text,
    }


def create_ambient_bed(duration_seconds: float, output: Path) -> None:
    # Quiet synthetic bed: low pads + soft pink noise, intentionally below narration.
    filter_graph = (
        f"sine=frequency=196:duration={duration_seconds:.3f}:sample_rate=44100[a0];"
        f"sine=frequency=294:duration={duration_seconds:.3f}:sample_rate=44100[a1];"
        f"sine=frequency=392:duration={duration_seconds:.3f}:sample_rate=44100[a2];"
        f"anoisesrc=color=pink:duration={duration_seconds:.3f}:amplitude=0.018:sample_rate=44100[n];"
        "[a0]volume=0.035,afade=t=in:st=0:d=3,afade=t=out:st="
        f"{max(duration_seconds - 4, 0):.3f}:d=4[p0];"
        "[a1]volume=0.022,afade=t=in:st=0:d=4,afade=t=out:st="
        f"{max(duration_seconds - 4, 0):.3f}:d=4[p1];"
        "[a2]volume=0.012,afade=t=in:st=0:d=5,afade=t=out:st="
        f"{max(duration_seconds - 4, 0):.3f}:d=4[p2];"
        "[n]volume=0.10,lowpass=f=1800,highpass=f=80,afade=t=in:st=0:d=2,afade=t=out:st="
        f"{max(duration_seconds - 3, 0):.3f}:d=3[p3];"
        "[p0][p1][p2][p3]amix=inputs=4:normalize=0,volume=0.65[aout]"
    )
    subprocess.run(
        [
            FFMPEG,
            "-y",
            "-filter_complex",
            filter_graph,
            "-map",
            "[aout]",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(output),
        ],
        check=True,
    )


def create_mix(narration_files: list[dict[str, object]], offsets: list[float], ambient: Path, output: Path) -> None:
    command = [FFMPEG, "-y", "-i", str(ambient)]
    for item in narration_files:
        command.extend(["-i", str(item["wav"])])

    filters: list[str] = ["[0:a]volume=0.55[bed]"]
    inputs = ["[bed]"]
    for index, (item, offset) in enumerate(zip(narration_files, offsets, strict=True), start=1):
        delay_ms = int(round(offset * 1000))
        label = f"n{index}"
        filters.append(f"[{index}:a]adelay={delay_ms}|{delay_ms},volume=1.0[{label}]")
        inputs.append(f"[{label}]")
    filters.append("".join(inputs) + f"amix=inputs={len(inputs)}:normalize=0,alimiter=limit=0.92[aout]")

    command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[aout]",
            "-ar",
            "44100",
            "-ac",
            "2",
            str(output),
        ]
    )
    subprocess.run(command, check=True)


def mux_video(video: Path, audio: Path, output: Path) -> None:
    subprocess.run(
        [
            FFMPEG,
            "-y",
            "-i",
            str(video),
            "-i",
            str(audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output),
        ],
        check=True,
    )


def main() -> int:
    if not shutil.which(SAY):
        raise RuntimeError("macOS say is not available.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    final_duration = duration(FINAL_VIDEO)
    offsets: list[float] = []
    current = 0.0
    for segment in SEGMENTS:
        offsets.append(current)
        current += segment.duration - TRANSITION_SECONDS

    narration_files = []
    for segment in SEGMENTS:
        # Leave a short natural pause before each transition.
        target = max(segment.duration - 0.9, 3.0)
        narration_files.append(make_narration(segment, target))

    ambient = OUT_DIR / "new_ambient_bed.wav"
    narration_mix = OUT_DIR / "unified_narration_mix.wav"
    final_output = ROOT / "软件谷的隐藏接口_全自动API成片_统一旁白版.mp4"
    create_ambient_bed(final_duration, ambient)
    create_mix(narration_files, offsets, ambient, narration_mix)
    mux_video(FINAL_VIDEO, narration_mix, final_output)

    manifest = {
        "source_video": str(FINAL_VIDEO),
        "output_video": str(final_output),
        "method": "删除原音轨；使用 macOS say 统一中文男声 Reed 生成旁白；使用 ffmpeg 合成新低音量环境/配乐床；按原分镜时间轴对齐混音。",
        "voice": VOICE,
        "final_duration": round(duration(final_output), 3),
        "segments": narration_files,
        "offsets": [round(value, 3) for value in offsets],
        "ambient_bed": str(ambient),
        "audio_mix": str(narration_mix),
    }
    manifest_path = OUT_DIR / "audio_replace_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
