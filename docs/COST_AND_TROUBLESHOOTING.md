# 成本与问题复盘

## 成本口径

本次项目成本以火山引擎后台实际记录为准，最终总成本为 `¥119.63`。

| 项目 | 数值 |
|---|---:|
| 关键帧图片 | 21 张 |
| 视频任务 | 11 段 |
| 最终分镜 | 9 个 |
| 视频 tokens | 2,601,900 |
| 总成本 | ¥119.63 |
| 平均到 9 个最终分镜 | ¥13.29 / 分镜 |
| 平均到 11 段视频任务 | ¥10.88 / 段 |

## 图片/视频拆分方法

脚本不直接读取火山账单，因此不在代码里硬编码图片成本和视频成本。准确拆分应按以下方式做：

1. 到火山引擎费用中心导出账单。
2. 按模型 ID 或产品名称分组。
3. `doubao-seedream-*` 归入图片生成成本。
4. `doubao-seedance-*` 归入视频生成成本。
5. 用脚本生成的 manifest 中的 task id、生成时间、模型 ID 做交叉核对。

## 遇到的问题

### 1. API Key 配置

现象：

```text
ARK_API_KEY is not set
```

解决：

```bash
export ARK_API_KEY="你的火山方舟 API Key"
```

不要把真实 key 写入代码、README 或 GitHub。

### 2. 模型未开通或未绑定额度

现象：

- API 返回权限或额度错误
- 控制台显示模型未开通

解决：

- 在火山方舟控制台开通 Seedream 图片模型和 Seedance 视频模型。
- 购买或绑定可用资源包。
- 确认 API Key 所属账号与开通模型的账号一致。

### 3. 模型推理限额无法设置

现象：

```text
操作被拒绝，因为需要先停止自动设置模型推理限制
```

解决：

先关闭自动模型推理限制，再手动设置模型额度或关闭额度限制。

### 4. 异步视频任务耗时长

原因：

Seedance 视频生成是异步任务，高峰期可能长时间排队。

解决：

```bash
python scripts/generate_storyboard_api.py --timeout 3600 --poll-interval 20
```

manifest 会保留 task id，便于重新查询。

### 5. 声音统一问题

原因：

每段视频音画同出时，模型可能为不同分镜生成略有差异的男声。

解决：

使用：

```bash
python scripts/replace_auto_video_audio.py
```

该脚本会删除原音轨，用 macOS `say` 生成统一旁白，并重新合成低音量环境声。

### 6. 画面质量波动

原因：

生成式模型存在随机性，可能出现构图不稳、UI 字符异常或运动偏差。

解决：

- 先用 Seedream 固定关键帧，再用 Seedance 生成视频。
- 对不合格分镜单独重跑。
- 使用 `qa_storyboard.py` 抽帧检查。

### 7. ffmpeg 路径问题

解决：

```bash
brew install ffmpeg
export FFMPEG=/opt/homebrew/bin/ffmpeg
export FFPROBE=/opt/homebrew/bin/ffprobe
```
