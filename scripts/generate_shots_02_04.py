#!/usr/bin/env python3
"""Generate storyboard shots with Volcengine Ark Seedream + Seedance."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import shutil
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


STYLE_PREFIX = (
    "中国新水墨风格，宣纸质感，水墨晕染与留白，飞白笔触，淡青与淡赭点染，"
    "电影感构图，16:9 横画幅；现代城市以淡墨线勾勒；无可辨认真实人脸，"
    "无大段中文文字。整体色调、笔触、UI 融合方式与分镜01保持一致。"
)

VOICE_STYLE = (
    "旁白沿用分镜01同一类青年男声、标准普通话，清晰沉稳、中速，"
    "不要女声、不要童声、不要老年声；配乐延续新中式古琴/箫与轻弦乐，"
    "音量明显低于旁白，环境声短促点缀。"
)


@dataclass
class ImagePrompt:
    name: str
    title: str
    prompt: str
    url: str | None = None
    local_path: str | None = None
    size: str | None = None


@dataclass
class ShotSpec:
    shot_id: str
    folder_name: str
    video_name: str
    duration: int
    images: list[ImagePrompt]
    video_prompt: str


SHOTS: dict[str, ShotSpec] = {
    "02": ShotSpec(
        shot_id="02",
        folder_name="分镜 02 - 清晨",
        video_name="分镜02_清晨.mp4",
        duration=13,
        images=[
            ImagePrompt(
                name="图02-1",
                title="传感器未亮 · 首帧",
                prompt=(
                    f"{STYLE_PREFIX} 清晨街角，薄雾未散，一排路灯与城市传感器立杆沿街排列、"
                    "以淡墨勾勒；地面与远景大面积留白，冷青色调，安静；传感器尚未点亮，"
                    "本张不出现 UI 元素。"
                ),
            ),
            ImagePrompt(
                name="图02-2",
                title="点亮连网 · 尾帧",
                prompt=(
                    f"{STYLE_PREFIX} 同一清晨街角，传感器节点逐个点亮为淡蓝色发光墨点，"
                    "墨点之间以淡蓝墨线相连、织成一张物联网络；节点旁悬浮极简的淡墨状态卡片，"
                    "仅允许极小英文 ON 或 OK；薄雾微亮，科技感自然融入水墨。"
                ),
            ),
        ],
        video_prompt=(
            "画面与运镜：清晨镜头，中国新水墨风，16:9，承接开场网格意象，画风、色调、"
            "水墨 UI 融合方式与分镜01保持一致。以【图02-1】为首帧——薄雾中的清晨街角，"
            "路灯与传感器立杆静立。摄影机沿街缓慢横移，移动中传感器节点由近及远逐个点亮为"
            "淡蓝墨点，墨线在节点间一段段连接、织成物联网络，过渡到【图02-2】。运动平稳，"
            "点亮带轻微呼吸感，雾气随横移轻轻流动。\n\n"
            "UI生成要求：传感器节点点亮为淡蓝发光墨点、墨线沿街灯立杆自然连成网络，节点旁"
            "悬浮极简淡墨状态卡片；仅允许极小英文 ON 或 OK；不要大段中文、不要密集数字；"
            "不依赖后期。\n\n"
            f"同步音频（音画同出）：{VOICE_STYLE} 旁白——「天没亮透，城市先醒了。街角的"
            "传感器一盏盏睁开眼，这是物联网。它们互相确认：每个节点都健康在线，城市，"
            "正式开机。」IoT 读作“物联网”。环境音：清脆“叮”提示音数声、鸟鸣。"
        ),
    ),
    "03": ShotSpec(
        shot_id="03",
        folder_name="分镜 03 - 早高峰",
        video_name="分镜03_早高峰.mp4",
        duration=14,
        images=[
            ImagePrompt(
                name="图03-1",
                title="人潮汇聚 · 首帧",
                prompt=(
                    f"{STYLE_PREFIX} 早高峰的地铁口与十字路口，人潮与车流向画面中心汇聚，"
                    "以淡墨水墨笔触表现密集人影车影，不出现可辨真实人脸；晨光斜照，构图向中心汇聚，"
                    "繁忙而有序；本张不出现 UI 元素。"
                ),
            ),
            ImagePrompt(
                name="图03-2",
                title="并发光点+队列 · 尾帧",
                prompt=(
                    f"{STYLE_PREFIX} 同一路口拉远后的中远景，密集人流车流化作流动的墨色河流，"
                    "无数淡蓝色发光“请求”光点从四面同时涌入中心；画面侧边浮现淡墨半透明的"
                    "排队队列条，仅允许极小英文 QUEUE；秩序感，科技融入水墨。"
                ),
            ),
        ],
        video_prompt=(
            "画面与运镜：早高峰镜头，中国新水墨风，16:9，节奏比清晨加快，画风、色调、"
            "水墨 UI 融合方式与分镜01保持一致。以【图03-1】为首帧——人潮车流向路口中心汇聚。"
            "摄影机缓慢拉远，视野打开，密集人影车影渐渐化作流动的墨色河流，无数淡蓝“请求”"
            "光点从四面八方同时涌入中心，侧边浮现淡墨排队队列条此起彼伏，过渡到【图03-2】。"
            "运动平稳，人流如墨水流动，光点涌入带轻微节拍感。\n\n"
            "UI生成要求：蓝色“请求”光点涌入中心、侧边淡墨半透明队列条起伏，贴合路口与街道"
            "自然生长；仅允许极小英文 QUEUE；不要大段中文、不要密集数字；不依赖后期。\n\n"
            f"同步音频（音画同出）：{VOICE_STYLE} 旁白节奏略加快——「成千上万人同时出门，"
            "地铁、马路、电梯，同一刻涌入海量请求——这叫并发。系统提前预测、排好队列，"
            "再大的洪峰也稳稳接住。」“并发”读清楚、稍放慢。环境音：人潮、地铁进站气流声；"
            "配乐加入轻鼓点，音量低于旁白。"
        ),
    ),
    "04": ShotSpec(
        shot_id="04",
        folder_name="分镜 04 - 路径规划",
        video_name="分镜04_路径规划.mp4",
        duration=13,
        images=[
            ImagePrompt(
                name="图04-1",
                title="无人车行驶 · 首帧",
                prompt=(
                    f"{STYLE_PREFIX} 正午街道，一辆造型简洁的无人配送小车行驶在路上、以淡墨勾勒，"
                    "主体偏画面右侧，左侧是淡墨城市路网与街景；正午光线明亮、阴影短；"
                    "车前方暂无任何路径线，本张不出现 UI 元素。"
                ),
            ),
            ImagePrompt(
                name="图04-2",
                title="最优路径点亮 · 尾帧",
                prompt=(
                    f"{STYLE_PREFIX} 同一辆无人配送车，车前方道路上浮现多条淡蓝色墨线“候选路径”，"
                    "呈扇形铺开延伸向不同方向，其中一条被点亮为更亮的蓝色“最优路径”沿街蜿蜒；"
                    "路径如水墨笔锋流畅，仅允许极小英文 ROUTE。"
                ),
            ),
        ],
        video_prompt=(
            "画面与运镜：午间前镜头，中国新水墨风，16:9，从城市群像收回到从容个体，画风、"
            "色调、水墨 UI 融合方式与分镜01保持一致。以【图04-1】为首帧——无人配送车在正午街道"
            "平稳行驶。摄影机跟拍车辆，行进中车前方道路上缓缓浮现多条淡蓝墨线候选路径、呈扇形铺开，"
            "随后其中一条点亮为更亮的最优路径，过渡到【图04-2】。运动平稳跟随，路径线如毛笔顺锋"
            "逐段生长。\n\n"
            "UI生成要求：车前方候选路径线扇形铺开、最优路径点亮，贴合道路自然生长，像水墨笔锋；"
            "仅允许极小英文 ROUTE；不要大段中文、不要密集数字；不依赖后期。\n\n"
            f"同步音频（音画同出）：{VOICE_STYLE} 旁白从容——「街角的无人配送车不慌不忙。"
            "它脑子里跑着路径规划算法，在千万条路里，实时算出此刻最快的那一条。」“路径规划”"
            "读清楚、稍放慢。环境音：电机轻响、轻微“滴答”运算声；配乐轻快点状音色，音量低于旁白。"
        ),
    ),
    "05": ShotSpec(
        shot_id="05",
        folder_name="分镜 05 - 负载均衡",
        video_name="分镜05_负载均衡.mp4",
        duration=13,
        images=[
            ImagePrompt(
                name="图05-1",
                title="忙闲不均 · 首帧",
                prompt=(
                    f"{STYLE_PREFIX} 午间的智慧产业园，画面里横向并列几台机械臂与配送分拣节点、"
                    "以淡墨勾勒，三分式构图；其中一部分节点亮着暖光显得繁忙、另一部分偏暗显得空闲，"
                    "繁忙节点上方有较高的淡墨负载色块，仅允许极小英文 LOAD。"
                ),
            ),
            ImagePrompt(
                name="图05-2",
                title="任务均衡 · 尾帧",
                prompt=(
                    f"{STYLE_PREFIX} 同一排机械臂与节点，淡蓝色“任务”发光墨点从繁忙的节点"
                    "缓缓流向空闲的节点，各节点上方的淡墨负载色块随之此消彼长、趋于一致高度，"
                    "画面达到平衡；科技感融入水墨，仅允许极小英文 LOAD。"
                ),
            ),
        ],
        video_prompt=(
            "画面与运镜：午间镜头，中国新水墨风，16:9，全片最“忙”的一段，画风、色调、"
            "水墨 UI 融合方式与分镜01保持一致。以【图05-1】为首帧——一排机械臂与配送节点，"
            "忙闲不均、负载色块高低参差。摄影机沿节点缓慢平移，移动中淡蓝“任务”光点从繁忙节点"
            "流向空闲节点，各节点上方负载色块此消彼长、逐渐趋平，过渡到【图05-2】。运动平稳，"
            "光点流动如墨丝牵引，机械臂保持轻微规律运转。\n\n"
            "UI生成要求：任务发光墨点在节点间流动、节点上方负载色块此消彼长，贴合机械臂与设备"
            "自然生长；仅允许极小英文 LOAD；不要大段中文、不要密集数字；不依赖后期。\n\n"
            f"同步音频（音画同出）：{VOICE_STYLE} 旁白解释感更强——「正午最忙，订单、外卖、"
            "机械臂一起开动。城市从不把活全压给一台机器，谁闲就派给谁——这叫负载均衡。」"
            "“负载均衡”读清楚、稍放慢。环境音：机械臂运转、流水线规律节拍；配乐节奏最满、"
            "最密的一段，音量低于旁白。"
        ),
    ),
    "06": ShotSpec(
        shot_id="06",
        folder_name="分镜 06 - 推荐系统",
        video_name="分镜06_推荐系统.mp4",
        duration=13,
        images=[
            ImagePrompt(
                name="图06-1",
                title="内容流 · 首帧",
                prompt=(
                    f"{STYLE_PREFIX} 浅景深，特写一只手轻持手机，手以淡墨简笔表现，不出现真实人脸；"
                    "手机屏幕里是以淡墨墨点表示的海量内容流；主体居中、背景虚化留白，午间柔光；"
                    "本张暂无推荐高亮。"
                ),
            ),
            ImagePrompt(
                name="图06-2",
                title="推荐卡浮现 · 尾帧",
                prompt=(
                    f"{STYLE_PREFIX} 推近后的手机屏幕，海量淡墨内容墨点向中心的“用户偏好”"
                    "缓缓聚拢、对齐，匹配出两三张悬浮的淡墨推荐卡片轻轻浮现到前景，"
                    "淡蓝高光点缀，仅允许极小英文 FOR YOU。"
                ),
            ),
        ],
        video_prompt=(
            "画面与运镜：午间镜头，中国新水墨风，16:9，浅景深，从产业园的“大”收到掌心的“小”，"
            "画风、色调、水墨 UI 融合方式与分镜01保持一致。以【图06-1】为首帧——手持手机，"
            "屏内是漫天淡墨内容墨点。摄影机缓缓推近，推进中海量内容墨点向中心的“偏好”聚拢、"
            "对齐，匹配出两三张淡墨推荐卡片轻轻浮现到前景，过渡到【图06-2】。运动平稳，"
            "墨点聚拢如墨汁回流，卡片浮现柔和。\n\n"
            "UI生成要求：内容墨点向偏好聚拢、推荐卡片浮现，在手机屏内自然生长；仅允许极小英文 "
            "FOR YOU；不要大段中文、不要密集数字；不依赖后期。\n\n"
            f"同步音频（音画同出）：{VOICE_STYLE} 旁白解释感——「你刷到的每条内容，背后都是"
            "大数据推荐。它把你的喜好和海量信息比对，在你开口前，就把你想要的，推到眼前。」"
            "环境音：轻“咔哒”翻动、气泡声；配乐俏皮短音、稍收，音量低于旁白。"
        ),
    ),
    "07A": ShotSpec(
        shot_id="07A",
        folder_name="分镜 07 - 傍晚",
        video_name="分镜07A_傍晚上半.mp4",
        duration=8,
        images=[
            ImagePrompt(
                name="图07-1",
                title="黄昏待升空 · 首帧",
                prompt=(
                    f"{STYLE_PREFIX} 黄昏转夜的软件谷城市天际线，暖金色夕照正过渡到暮蓝，"
                    "一群无人机以淡墨小点列队悬停在城市上空待升；地平线压得很低，天空占画面上方"
                    "大部分，大面积留白；地面暂无柱状图。"
                ),
            ),
            ImagePrompt(
                name="图07-2",
                title="柱状图腾空 · 中间帧",
                prompt=(
                    f"{STYLE_PREFIX} 同一城市天际线，地面的数据化作一根根淡蓝色发光的水墨"
                    "“柱状图”自地面腾空升起，高低错落，如雨后春笋向夜空生长，柱体带水墨晕染边缘；"
                    "暮色加深，科技感融入水墨。"
                ),
            ),
        ],
        video_prompt=(
            "画面与运镜：傍晚上半，中国新水墨风，16:9，画风、色调、水墨 UI 融合方式与分镜01保持一致。"
            "以【图07-1】为首帧——黄昏城市天际线，无人机列队待升，天空大留白。摄影机缓慢向上摇，"
            "无人机升空，地面数据化作一根根淡蓝水墨柱状图自地面腾空升起、高低错落，过渡到【图07-2】。"
            "运动连贯优雅，柱体生长如水墨晕染般自然。\n\n"
            "UI生成要求：柱状图自地面腾空升起、水墨晕染边缘，自然生长，不像普通图表贴片；"
            "不要文字、不要密集数字；不依赖后期。\n\n"
            f"同步音频（音画同出）：{VOICE_STYLE} 旁白情绪上扬——「夕阳西下，一天的数据开始"
            "回传、汇聚。无人机升空，把数字翻译成光。」环境音：无人机群嗡鸣渐起、晚风；"
            "配乐弦乐铺开，音量低于旁白。"
        ),
    ),
    "07B": ShotSpec(
        shot_id="07B",
        folder_name="分镜 07 - 傍晚",
        video_name="分镜07B_傍晚下半.mp4",
        duration=9,
        images=[
            ImagePrompt(
                name="图07-2",
                title="柱状图腾空 · 首帧",
                prompt=(
                    f"{STYLE_PREFIX} 同一城市天际线，地面的数据化作一根根淡蓝色发光的水墨"
                    "“柱状图”自地面腾空升起，高低错落，如雨后春笋向夜空生长，柱体带水墨晕染边缘；"
                    "暮色加深，科技感融入水墨。"
                ),
            ),
            ImagePrompt(
                name="图07-3",
                title="散作星河 · 尾帧",
                prompt=(
                    f"{STYLE_PREFIX} 上摇至夜空后，升空的蓝色柱状图在高处散开、化作漫天细碎的"
                    "发光墨点，铺成一整片夜空里的“数据星河”，墨点疏密如银河；城市只剩底部一线"
                    "淡墨剪影，画面辽阔唯美。"
                ),
            ),
        ],
        video_prompt=(
            "画面与运镜：傍晚下半，中国新水墨风，16:9，全片视觉高潮，画风、色调、水墨 UI 融合方式"
            "与分镜01保持一致。以【图07-2】为首帧——柱状图升至半空。摄影机继续向上摇至夜空，"
            "柱状图在高处散开、化作漫天发光墨点，铺成整片“数据星河”，定格于【图07-3】。"
            "散开如水墨晕染般自然，画面辽阔唯美。\n\n"
            "UI生成要求：柱状图升空后散为漫天星河墨点，纯水墨光效、疏密如银河；不要文字、"
            "不要密集数字；不依赖后期。\n\n"
            f"同步音频（音画同出）：{VOICE_STYLE} 旁白情绪上扬——「一根根柱状图腾空，"
            "散作整片星河——这就是数据可视化。」“数据可视化”读清楚、稍放慢。环境音：晚风、"
            "低频氛围；配乐弦乐最辽阔的一段，音量低于旁白。"
        ),
    ),
    "08A": ShotSpec(
        shot_id="08A",
        folder_name="分镜 08 - 冷备",
        video_name="分镜08A_深夜城市俯冲.mp4",
        duration=6,
        images=[
            ImagePrompt(
                name="图08-1",
                title="沉睡城市 · 首帧",
                prompt=(
                    f"{STYLE_PREFIX} 深夜高空俯瞰沉睡的软件谷，绝大部分城市暗下、只剩零星如呼吸般的"
                    "幽蓝微光散落；画面中有一栋数据中心建筑透出幽蓝冷光，是唯一“醒着”的存在；"
                    "冷青墨色、克制压暗、大量暗部留白，大俯角，为俯冲推近留出纵深。"
                ),
            ),
        ],
        video_prompt=(
            "画面与运镜：深夜镜头上半，中国新水墨风，16:9，画风、色调、水墨 UI 融合方式与分镜01保持一致。"
            "以【图08-1】为首帧——深夜高空俯瞰沉睡的软件谷，城市大片暗下、零星幽蓝微光，一栋数据中心"
            "透着冷光。摄影机从高空缓慢俯冲下压并持续推近，对准那栋唯一亮着的数据中心，沉睡的城市由远"
            "及近、暗部细节渐显；运动平稳但持续、有明确的下压与推进感，不要原地不动。尾帧停在接近数据"
            "中心建筑的中近景。\n\n"
            f"同步音频（音画同出）：{VOICE_STYLE} 旁白放轻沉下、中速偏慢——「城市安静了，"
            "计算机却不真正休眠。数据中心进入冷备，压低呼吸。」“冷备”读清楚、稍放慢。"
            "环境音：极低频夜风、近乎寂静；配乐仅余古琴单音，音量低于旁白。"
        ),
    ),
    "08B": ShotSpec(
        shot_id="08B",
        folder_name="分镜 08 - 冷备",
        video_name="分镜08B_深夜走廊穿行.mp4",
        duration=7,
        images=[
            ImagePrompt(
                name="图08-2",
                title="昏暗机房走廊 · 首帧",
                prompt=(
                    f"{STYLE_PREFIX} 深夜数据中心机房走廊，一点透视、强烈纵深，绝大多数机柜已熄灭"
                    "陷入暗影、仅少数蓝色指示灯如呼吸般明灭，走廊深处透出一束柔和冷光；"
                    "昏暗、安静、克制，不要明亮满屏的灯，让纵深通道引导镜头向前。"
                ),
            ),
            ImagePrompt(
                name="图08-3",
                title="冷备副本 · 尾帧",
                prompt=(
                    f"{STYLE_PREFIX} 机房走廊深处的暗影中，一簇蓝色墨点静静地复制出一份并排的副本，"
                    "左侧本体、右侧副本，之间一条极淡的流动墨线，周围大量暗部留白，黑暗中安宁守护感，"
                    "仅允许极小英文 BACKUP。"
                ),
            ),
        ],
        video_prompt=(
            "画面与运镜：深夜镜头下半，中国新水墨风，16:9，画风、色调、水墨 UI 融合方式与分镜01保持一致。"
            "以【图08-2】为首帧——昏暗的机房走廊，少数蓝灯呼吸般明灭，深处一束柔光。摄影机匀速向前"
            "穿行、持续推进纵深，沿一点透视通道缓缓深入走廊，两侧熄灭的机柜从镜头旁掠过；行进接近深处时，"
            "画面一角一簇蓝色墨点静静复制出一份并排副本，过渡到【图08-3】。运动连贯、克制而持续。\n\n"
            "UI生成要求：仅少量呼吸般明灭的蓝光点、一簇墨点静静复制出并排副本，贴合机柜与走廊自然生长，"
            "仅极小英文 BACKUP；不要大段中文、不要密集数字；不依赖后期。\n\n"
            f"同步音频（音画同出）：{VOICE_STYLE} 旁白放轻、中速偏慢——「悄悄备份。万一出错，"
            "总有一份副本，在黑暗里替你守着。」环境音：低频机房嗡鸣、近乎寂静；配乐古琴单音、"
            "大量留白，音量低于旁白。"
        ),
    ),
    "09": ShotSpec(
        shot_id="09",
        folder_name="分镜 09 - 结尾",
        video_name="分镜09_结尾.mp4",
        duration=11,
        images=[
            ImagePrompt(
                name="图09-1",
                title="黎明将至 · 首帧",
                prompt=(
                    f"{STYLE_PREFIX} 黎明将至的软件谷城市俯瞰，构图与开场相呼应，天色由墨蓝转微明，"
                    "城市居中、四周大面积留白，宁静温暖；楼宇上暂无接口面板亮起。"
                ),
            ),
            ImagePrompt(
                name="图09-2",
                title="接口亮起收束 · 尾帧",
                prompt=(
                    f"{STYLE_PREFIX} 同一黎明城市俯瞰，一个个淡蓝色 UI“接口面板”沿楼宇与街道依次"
                    "轻轻亮起、连成接口网络，随后整体柔和收束、淡淡隐入水墨；画面右下或中部留出干净的"
                    "标题/落版位，温暖收尾，仅允许极小英文 API。"
                ),
            ),
        ],
        video_prompt=(
            "画面与运镜：结尾镜头，中国新水墨风，16:9，与开场首尾呼应，画风、色调、水墨 UI 融合方式"
            "与分镜01保持一致。以【图09-1】为首帧——黎明将至的城市俯瞰，构图回到开场。摄影机缓缓推近，"
            "推进中一个个淡蓝接口面板沿楼宇依次亮起、连成全片出现过的接口网络，随后整体柔和收束、淡淡"
            "隐入水墨并定格，留出干净的落版标题位，过渡到【图09-2】。运动平稳，亮起与收束如墨色呼吸。\n\n"
            "UI生成要求：接口面板沿楼宇依次亮起、连成网络后整体收束隐入水墨，自然生长、温暖收尾，"
            "画面留落版位；仅允许极小英文 API；不要大段中文、不要密集数字；不依赖后期。\n\n"
            f"同步音频（音画同出）：{VOICE_STYLE} 旁白温暖收束——「从清晨到深夜，这些接口你"
            "天天在用，却从没看见。读懂它们，你才发现：这座城，一直在为你安静地思考。」"
            "环境音：渐入晨声、一声轻钟收尾；配乐主题回到古琴、温暖收束，音量低于旁白。"
        ),
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate storyboard shots via Volcengine Ark.")
    parser.add_argument("--shots", nargs="+", default=sorted(SHOTS), choices=sorted(SHOTS))
    parser.add_argument("--out-root", default="outputs/软件谷的隐藏接口_分镜视频")
    parser.add_argument("--image-model", default=DEFAULT_IMAGE_MODEL)
    parser.add_argument("--video-model", default=DEFAULT_VIDEO_MODEL)
    parser.add_argument("--image-size", default="1280x720")
    parser.add_argument("--resolution", default="720p")
    parser.add_argument("--ratio", default="16:9")
    parser.add_argument("--poll-interval", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--skip-existing-images", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
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


def public_image_manifest(images: list[ImagePrompt]) -> list[dict[str, Any]]:
    items = []
    for image in images:
        data = asdict(image)
        if (data.get("url") or "").startswith("data:image"):
            data["url"] = "[local data URL omitted]"
        items.append(data)
    return items


def seed_shot01_folder(out_root: Path) -> None:
    source = REPO_ROOT / "outputs" / "shot01"
    target = out_root / "分镜 01 - 开场"
    target.mkdir(parents=True, exist_ok=True)
    for name in ["image_01_1.jpg", "image_01_2.jpg", "image_01_3.jpg", "shot01.mp4", "manifest.json"]:
        src = source / name
        if src.exists():
            if name == "shot01.mp4":
                dst = target / "分镜01_开场.mp4"
            elif name == "manifest.json":
                dst = target / "manifest_01.json"
            else:
                dst = target / name
            if not dst.exists():
                shutil.copy2(src, dst)


def image_path_for(folder: Path, image: ImagePrompt) -> Path | None:
    for suffix in (".jpg", ".jpeg", ".png"):
        path = folder / f"{image.name}{suffix}"
        if path.exists():
            return path
    return None


def generate_images(client: Ark, spec: ShotSpec, args: argparse.Namespace, folder: Path, manifest: dict[str, Any]) -> None:
    for image in spec.images:
        existing = image_path_for(folder, image)
        if args.skip_existing_images and existing:
            image.local_path = str(existing)
            image.url = local_image_as_data_url(existing)
            continue

        print(f"Generating {spec.shot_id} image: {image.name}", flush=True)
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
        local_path = folder / f"{image.name}{suffix}"
        if image.url.startswith("data:image"):
            save_data_image(image.url, local_path)
        else:
            download_url(image.url, local_path)
        image.local_path = str(local_path)
        manifest["images"] = public_image_manifest(spec.images)
        write_manifest(folder / f"manifest_{spec.shot_id}.json", manifest)


def create_video_task(client: Ark, spec: ShotSpec, args: argparse.Namespace) -> Any:
    first_frame = spec.images[0].url
    if not first_frame:
        raise RuntimeError(f"Missing first frame URL for shot {spec.shot_id}.")
    content = [
        {"type": "text", "text": spec.video_prompt},
        {"type": "image_url", "image_url": {"url": first_frame}, "role": "first_frame"},
    ]
    if len(spec.images) > 1:
        last_frame = spec.images[-1].url
        if not last_frame:
            raise RuntimeError(f"Missing last frame URL for shot {spec.shot_id}.")
        content.append({"type": "image_url", "image_url": {"url": last_frame}, "role": "last_frame"})
    print(f"Creating video task for shot {spec.shot_id}", flush=True)
    return client.content_generation.tasks.create(
        model=args.video_model,
        content=content,
        resolution=args.resolution,
        ratio=args.ratio,
        duration=spec.duration,
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


def generate_shot(client: Ark, spec: ShotSpec, args: argparse.Namespace, out_root: Path) -> int:
    folder = out_root / spec.folder_name
    folder.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "shot": spec.shot_id,
        "folder_name": spec.folder_name,
        "image_model": args.image_model,
        "video_model": args.video_model,
        "image_size": args.image_size,
        "video": {
            "prompt": spec.video_prompt,
            "resolution": args.resolution,
            "ratio": args.ratio,
            "duration": spec.duration,
            "generate_audio": True,
            "watermark": False,
        },
        "images": public_image_manifest(spec.images),
        "status": "dry_run" if args.dry_run else "started",
        "created_at": int(time.time()),
    }
    write_manifest(folder / f"manifest_{spec.shot_id}.json", manifest)
    if args.dry_run:
        print(f"Dry run manifest written: {folder / f'manifest_{spec.shot_id}.json'}")
        return 0

    try:
        generate_images(client, spec, args, folder, manifest)
        manifest["images"] = public_image_manifest(spec.images)
        create_result = create_video_task(client, spec, args)
        task_id = getattr(create_result, "id", None)
        if not task_id:
            raise RuntimeError(f"Create task response has no id: {to_plain(create_result)}")
        manifest["video"]["task_id"] = task_id
        manifest["video"]["create_response"] = to_plain(create_result)
        manifest["status"] = "video_task_created"
        write_manifest(folder / f"manifest_{spec.shot_id}.json", manifest)

        task = poll_video_task(client, task_id, args)
        task_data = to_plain(task)
        manifest["video"]["task"] = task_data
        manifest["status"] = getattr(task, "status", "unknown")

        content = getattr(task, "content", None)
        video_url = getattr(content, "video_url", None) if content else None
        if manifest["status"] == "succeeded" and video_url:
            video_path = folder / spec.video_name
            download_url(video_url, video_path)
            manifest["video"]["url"] = video_url
            manifest["video"]["local_path"] = str(video_path)
        elif manifest["status"] == "succeeded":
            raise RuntimeError(f"Task succeeded but no video_url was returned: {task_data}")

        write_manifest(folder / f"manifest_{spec.shot_id}.json", manifest)
        return 0 if manifest["status"] == "succeeded" else 2
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        write_manifest(folder / f"manifest_{spec.shot_id}.json", manifest)
        raise


def main() -> int:
    args = parse_args()
    out_root = (REPO_ROOT / args.out_root).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    seed_shot01_folder(out_root)

    if args.dry_run:
        client = None
    else:
        client = Ark(base_url=BASE_URL, api_key=ensure_key())

    exit_code = 0
    for shot_id in args.shots:
        spec = SHOTS[shot_id]
        result = generate_shot(client, spec, args, out_root) if client else generate_shot(None, spec, args, out_root)
        if result != 0:
            exit_code = result
            break
    print(f"Output root: {out_root}", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
