# 0618-AIGC 全自动视频生成脚本包

本仓库整理的是《软件谷的隐藏接口》全自动 AIGC 视频生成方案：用火山方舟 Ark API 调用 Seedream 生成关键帧图片，再调用 Seedance 生成分镜视频，最后用 ffmpeg 自动拼接、叠化转场、抽帧质检。

## 1. 脚本能力概览

| 能力 | 脚本 | 说明 |
|---|---|---|
| 分镜 01 生成 | `scripts/generate_shot01.py` | 生成开场 3 张关键帧，并调用 Seedance 生成开场视频 |
| 分镜 02-09 生成 | `scripts/generate_storyboard_api.py` | 批量生成清晨、早高峰、路径规划、负载均衡、推荐系统、傍晚、冷备、结尾等分镜 |
| 图片生成 | Seedream API | 每个分镜先生成首帧/尾帧/过程帧，保证视觉风格可控 |
| 视频生成 | Seedance API | 使用首尾帧约束视频运动，并开启音画同出 |
| 任务轮询 | 脚本内置 | 创建异步任务后自动轮询，成功后下载视频 |
| 拼接成片 | `scripts/stitch_storyboard.py` | 按固定顺序拼接 11 段视频，并加入 0.45 秒叠化转场 |
| 统一旁白替换 | `scripts/replace_auto_video_audio.py` | 可选：用 macOS `say` 生成统一旁白，再替换原片音轨 |
| 抽帧质检 | `scripts/qa_storyboard.py` | 抽取每段首帧/中帧/尾帧，生成 QA 报告和总览图 |

## 2. 实现原理

流程是一个 API 驱动的视频流水线：

1. 文案和分镜被结构化写入脚本。
2. 每个分镜先调用 Seedream 生成关键帧图片。
3. 视频生成时把首帧、尾帧和分镜提示词一起传给 Seedance。
4. Seedance 返回异步任务 ID，脚本定时轮询任务状态。
5. 任务成功后下载视频，并把任务 ID、模型、提示词、图片 URL、本地路径写入 manifest。
6. 所有分镜完成后，用 ffmpeg 执行视频拼接、画面叠化和音频 acrossfade。
7. 质检脚本抽帧并生成 `qa_report.json`，方便人工快速复核画风、首尾帧一致性和最终成片状态。

这个方案的核心价值不是“手动复制提示词”，而是把选题、分镜、图片、视频、拼接、转场和质检都串成脚本化流程。

## 3. 运行前准备

需要开通并可调用以下模型：

| 类型 | 推荐模型 |
|---|---|
| 图片生成 | `doubao-seedream-4-0-250828` |
| 视频生成 | `doubao-seedance-2-0-260128` |

安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

配置密钥：

```bash
cp .env.example .env
export ARK_API_KEY="你的火山方舟 API Key"
```

不要把真实 API Key 写入仓库。

ffmpeg 用于拼接和质检：

```bash
brew install ffmpeg
```

如果 ffmpeg 不在 PATH，可以手动指定：

```bash
export FFMPEG=/opt/homebrew/bin/ffmpeg
export FFPROBE=/opt/homebrew/bin/ffprobe
```

## 4. 推荐运行顺序

先做 dry run，检查 manifest 和提示词，不产生 API 成本：

```bash
python scripts/generate_shot01.py --dry-run
python scripts/generate_storyboard_api.py --dry-run
```

生成分镜 01：

```bash
python scripts/generate_shot01.py
```

生成分镜 02-09：

```bash
python scripts/generate_storyboard_api.py --shots 02 03 04 05 06 07A 07B 08A 08B 09
```

拼接最终成片：

```bash
python scripts/stitch_storyboard.py
```

可选：替换为统一旁白版：

```bash
python scripts/replace_auto_video_audio.py
```

抽帧质检：

```bash
python scripts/qa_storyboard.py
```

## 5. 输出目录

默认输出到：

```text
outputs/软件谷的隐藏接口_分镜视频/
```

最终文件命名方式：

```text
分镜 01 - 开场/
分镜 02 - 清晨/
分镜 03 - 早高峰/
分镜 04 - 路径规划/
分镜 05 - 负载均衡/
分镜 06 - 推荐系统/
分镜 07 - 傍晚/
分镜 08 - 冷备/
分镜 09 - 结尾/
软件谷的隐藏接口_全自动API成片_叠化版.mp4
质检抽帧/qa_report.json
质检抽帧/全片分镜中帧总览.jpg
```

## 6. 成本分析

本项目最终按火山引擎后台确认的总成本为：

| 指标 | 结果 |
|---|---:|
| 关键帧图片 | 21 张 |
| 视频任务 | 11 段 |
| 最终分镜目录 | 9 个 |
| 视频 tokens | 2,601,900 |
| API 总成本 | ¥119.63 |
| 按 9 个最终分镜平均 | ¥13.29 / 分镜 |
| 按 11 段视频任务平均 | ¥10.88 / 段 |
| 报销上限 | ¥200 |
| 成本结论 | 低成本达标 |

图片生成和视频生成的精确拆分应以火山引擎费用中心账单为准：导出账单后按模型 ID 分组，Seedream 归入图片生成成本，Seedance 归入视频生成成本。脚本的 manifest 会记录模型 ID、任务 ID 和生成时间，方便与后台账单对账。

## 7. 已遇到的问题与解决方法

| 问题 | 原因 | 解决方法 |
|---|---|---|
| `ARK_API_KEY is not set` | 没有配置环境变量 | 执行 `export ARK_API_KEY=...`，或写入本机 shell 配置文件 |
| 模型不可调用 | 火山方舟模型未开通或未绑定资源包 | 在控制台开通 Seedream / Seedance，并确认账号有可用额度 |
| 关闭/设置推理限额失败 | 自动模型推理限制未先关闭 | 先关闭自动设置模型推理限制，再手动设置模型额度 |
| 视频任务长时间 pending | Seedance 是异步任务，高峰期耗时较长 | 增大 `--timeout`，保留 task id 后继续轮询 |
| 下载图片失败或证书错误 | Python urllib 证书链异常 | 脚本内置 `curl` 兜底下载；也可更新系统证书 |
| ffmpeg 找不到 | 本机未安装或路径不同 | 安装 ffmpeg，或设置 `FFMPEG` / `FFPROBE` 环境变量 |
| 人声不完全统一 | 每段视频音画同出会各自生成声音 | 使用 `replace_auto_video_audio.py` 后处理统一旁白 |
| 画面风格仍有波动 | 图像/视频模型存在随机性 | 固定风格前缀、使用首尾帧约束、必要时单分镜重跑 |

## 8. 方案优势与缺陷

优势：

- 从文案、分镜、图片、视频到拼接质检形成自动化链路。
- 每段都保留 manifest，便于追踪任务、复现提示词和对账。
- 通过首尾帧约束，比分镜纯文本生成更稳定。
- 成本低于 200 元报销上限。

缺陷：

- 视频模型的声线一致性仍不稳定，需要后处理统一旁白。
- 每个分镜的画面质量仍受模型随机性影响，正式交付前需要抽帧质检。
- 当前脚本是针对《软件谷的隐藏接口》定制的模板，换题材需要替换分镜配置和提示词。
- 精确成本拆分依赖火山后台账单，脚本只记录模型和任务信息，不直接读取账单。

## 9. 安全说明

- 本仓库不包含 API Key。
- `.env`、输出视频、图片、音频和缓存默认被 `.gitignore` 忽略。
- 不建议提交 `outputs/`，因为会包含大体积媒体文件和可能过期的生成 URL。
