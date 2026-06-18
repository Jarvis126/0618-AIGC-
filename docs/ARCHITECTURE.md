# 脚本架构说明

## 模块划分

| 模块 | 文件 | 职责 |
|---|---|---|
| 分镜 01 生成 | `scripts/generate_shot01.py` | 生成 3 张开场关键帧，创建并轮询 Seedance 视频任务 |
| 分镜 02-09 生成 | `scripts/generate_storyboard_api.py` + `scripts/generate_shots_02_04.py` | 批量生成后续分镜图片和视频 |
| 成片拼接 | `scripts/stitch_storyboard.py` | 用 xfade/acrossfade 拼接视频和音频 |
| 统一旁白 | `scripts/replace_auto_video_audio.py` | 可选后处理：统一声线并重新混音 |
| 抽帧质检 | `scripts/qa_storyboard.py` | 抽首帧/中帧/尾帧，生成 QA 报告 |

## 数据流

```text
分镜配置
  -> Seedream 图片生成
  -> 本地关键帧图片
  -> Seedance 视频任务
  -> 轮询任务状态
  -> 下载分镜视频
  -> ffmpeg 拼接叠化
  -> 抽帧质检
  -> 最终成片
```

## Manifest 设计

每个分镜目录都会写入 `manifest_XX.json`，记录：

- 分镜编号和目录名
- 图片模型和视频模型
- 图片提示词、图片 URL、本地图片路径
- 视频提示词、分辨率、时长、水印开关
- Seedance task id、任务状态、返回结果
- 本地视频路径

manifest 的价值是：出错可追踪、成本可对账、提示词可复用、结果可复核。

## 为什么使用首尾帧

纯文本生视频容易出现风格跳变、主体漂移和镜头不可控。脚本先用 Seedream 生成首帧/尾帧，再把图片作为 Seedance 的约束输入，让每段视频至少满足：

- 起始画面可控
- 结束画面可控
- 风格更接近同一套视觉系统
- 分镜之间更容易拼接

## 为什么还需要 QA

全自动不等于免检查。视频模型可能出现：

- UI 字符不稳定
- 人声声线漂移
- 局部画面闪烁
- 运动方向偏离提示词
- 首尾帧与生成视频不完全一致

`qa_storyboard.py` 的作用是快速生成抽帧总览，帮助在正式交付前发现明显问题。
