---
name: mmx-cli-cn
description: 通过 mmx 在 MiniMax AI 平台上生成文本、图片、视频、语音和音乐。当用户希望通过终端创建媒体内容、与 MiniMax 模型对话、执行网页搜索，或管理 MiniMax API 资源时使用。
---

# MiniMax CLI — Agent 使用指南（中文版）

通过 `mmx` 在 MiniMax AI 平台上生成文本、图片、视频、语音、音乐，以及执行网页搜索。

## 前置条件

```bash
# 安装
npm install -g mmx-cli

# 鉴权（OAuth 持久化到 ~/.mmx/credentials.json，API Key 持久化到 ~/.mmx/config.json）
mmx auth login --api-key sk-xxxxx

# 查看当前生效的鉴权来源
mmx auth status

# 也可以按调用临时传入
mmx text chat --api-key sk-xxxxx --message "你好"
```

区域（region）会自动检测，可通过 `--region global` 或 `--region cn` 手动覆盖。

---

## Agent 标志位

在非交互（Agent/CI）场景下，必须使用以下标志位：

| 标志位 | 作用 |
|---|---|
| `--non-interactive` | 缺少参数时立即失败，而不是弹出交互提示 |
| `--quiet` | 抑制旋转进度条等动态输出，让 stdout 只输出纯数据 |
| `--output json` | 输出机器可读的 JSON |
| `--async` | 立即返回任务 ID（用于视频生成） |
| `--dry-run` | 预览 API 请求但不真正执行 |
| `--yes` | 跳过确认提示 |

---

## 命令参考

### text chat

对话补全。默认模型：`MiniMax-M2.7`。

```bash
mmx text chat --message <text> [flags]
```

| 标志位 | 类型 | 说明 |
|---|---|---|
| `--message <text>` | 字符串，**必填**，可重复 | 消息文本。加 `role:` 前缀可指定角色（例如 `"system:你是一个助手"`、`"user:你好"`） |
| `--messages-file <path>` | 字符串 | 包含 messages 数组的 JSON 文件。用 `-` 表示从 stdin 读取 |
| `--system <text>` | 字符串 | 系统提示词 |
| `--model <model>` | 字符串 | 模型 ID（默认：`MiniMax-M2.7`） |
| `--max-tokens <n>` | 数字 | 最大 token 数（默认：4096） |
| `--temperature <n>` | 数字 | 采样温度 (0.0, 1.0] |
| `--top-p <n>` | 数字 | 核采样阈值 |
| `--stream` | 布尔 | 是否流式输出 token（默认：在 TTY 中开启） |
| `--tool <json-or-path>` | 字符串，可重复 | 工具定义 JSON 或文件路径 |

```bash
# 单条消息
mmx text chat --message "user:MiniMax 是什么？" --output json --quiet

# 多轮对话
mmx text chat \
  --system "你是一个编程助手。" \
  --message "user:用 Python 写一个 fizzbuzz" \
  --output json

# 从文件读取
cat conversation.json | mmx text chat --messages-file - --output json
```

**stdout**：文本模式下输出回复文本；JSON 模式下输出完整响应对象。

---

### image generate

图片生成。模型：`image-01`。

```bash
mmx image generate --prompt <text> [flags]
```

| 标志位 | 类型 | 说明 |
|---|---|---|
| `--prompt <text>` | 字符串，**必填** | 图片描述 |
| `--aspect-ratio <ratio>` | 字符串 | 例如 `16:9`、`1:1`。当同时设置了 `--width` 和 `--height` 时被忽略 |
| `--n <count>` | 数字 | 生成图片数量（默认：1） |
| `--seed <n>` | 数字 | 随机种子，用于可复现生成 |
| `--width <px>` | 数字 | 宽度像素（512–2048，必须是 8 的倍数）。需配合 `--height` |
| `--height <px>` | 数字 | 高度像素（512–2048，必须是 8 的倍数）。需配合 `--width` |
| `--prompt-optimizer` | 布尔 | 生成前先优化 prompt |
| `--aigc-watermark` | 布尔 | 嵌入 AIGC 水印 |
| `--subject-ref <params>` | 字符串 | 主体参考，例如 `type=character,image=path-or-url` |
| `--response-format <format>` | 字符串 | `url`（默认）或 `base64`。base64 模式跳过 CDN 下载 |
| `--out-dir <dir>` | 字符串 | 将图片下载到指定目录 |
| `--out-prefix <prefix>` | 字符串 | 文件名前缀（默认：`image`） |

```bash
mmx image generate --prompt "一只穿太空服的猫" --output json --quiet
# stdout: quiet 模式下每行一个图片 URL

mmx image generate --prompt "Logo" --n 3 --out-dir ./gen/ --quiet
# stdout: 每行一个保存的文件路径
```

---

### video generate

视频生成。默认模型：`MiniMax-Hailuo-2.3`。这是一个异步任务，默认会阻塞轮询直到完成。

```bash
mmx video generate --prompt <text> [flags]
```

| 标志位 | 类型 | 说明 |
|---|---|---|
| `--prompt <text>` | 字符串，**必填** | 视频描述 |
| `--model <model>` | 字符串 | `MiniMax-Hailuo-2.3`（默认）或 `MiniMax-Hailuo-2.3-Fast` |
| `--first-frame <path-or-url>` | 字符串 | 首帧图片 |
| `--callback-url <url>` | 字符串 | 完成时的回调 webhook |
| `--download <path>` | 字符串 | 将视频保存到指定文件 |
| `--async` | 布尔 | 立即返回任务 ID |
| `--no-wait` | 布尔 | 同 `--async` |
| `--poll-interval <seconds>` | 数字 | 轮询间隔秒数（默认：5） |

```bash
# 非阻塞：获取任务 ID
mmx video generate --prompt "一个机器人。" --async --quiet
# stdout: {"taskId":"..."}

# 阻塞：等待完成后返回文件路径
mmx video generate --prompt "海浪。" --download ocean.mp4 --quiet
# stdout: ocean.mp4
```

### video task get

查询视频生成任务的状态。

```bash
mmx video task get --task-id <id> [--output json]
```

### video download

根据任务 ID 下载已完成的视频。

```bash
mmx video download --file-id <id> [--out <path>]
```

---

### speech synthesize

语音合成。默认模型：`speech-2.8-hd`。单次最多 1 万字符。

```bash
mmx speech synthesize --text <text> [flags]
```

| 标志位 | 类型 | 说明 |
|---|---|---|
| `--text <text>` | 字符串 | 要合成的文本 |
| `--text-file <path>` | 字符串 | 从文件读取文本。用 `-` 表示从 stdin 读取 |
| `--model <model>` | 字符串 | `speech-2.8-hd`（默认）、`speech-2.6`、`speech-02` |
| `--voice <id>` | 字符串 | 发音人 ID（默认：`English_expressive_narrator`） |
| `--speed <n>` | 数字 | 语速倍数 |
| `--volume <n>` | 数字 | 音量大小 |
| `--pitch <n>` | 数字 | 音高调整 |
| `--format <fmt>` | 字符串 | 音频格式（默认：`mp3`） |
| `--sample-rate <hz>` | 数字 | 采样率（默认：32000） |
| `--bitrate <bps>` | 数字 | 比特率（默认：128000） |
| `--channels <n>` | 数字 | 声道数（默认：1） |
| `--language <code>` | 字符串 | 语言增强 |
| `--subtitles` | 布尔 | 同时下载并保存字幕为 `.srt` 文件（与 `--out` 指定的音频文件保存在同一目录）。所选模型的 API 必须支持字幕。 |
| `--pronunciation <from/to>` | 字符串，可重复 | 自定义发音 |
| `--sound-effect <effect>` | 字符串 | 添加音效 |
| `--out <path>` | 字符串 | 保存音频到文件 |
| `--stream` | 布尔 | 将原始音频流式输出到 stdout |

```bash
mmx speech synthesize --text "你好世界" --out hello.mp3 --quiet
# stdout: hello.mp3

mmx speech synthesize --text "你好" --subtitles --out hello.mp3
# 同时保存 hello.mp3 与 hello.srt（SRT 字幕文件）

echo "突发新闻。" | mmx speech synthesize --text-file - --out news.mp3
```

---

### music generate

音乐生成。对结构化、丰富的描述响应更好。

**模型：** `music-2.6-free` — 对 API Key 用户不限量，RPM = 3。

```bash
mmx music generate --prompt <text> [--lyrics <text>] [flags]
```

| 标志位 | 类型 | 说明 |
|---|---|---|
| `--prompt <text>` | 字符串 | 音乐风格描述（可以写得详细） |
| `--lyrics <text>` | 字符串 | 带结构标签的歌词。除非使用 `--instrumental` 或 `--lyrics-optimizer`，否则必填。 |
| `--lyrics-file <path>` | 字符串 | 从文件读取歌词。用 `-` 表示从 stdin 读取 |
| `--lyrics-optimizer` | 布尔 | 根据 prompt 自动生成歌词。不能与 `--lyrics` 或 `--instrumental` 同时使用 |
| `--instrumental` | 布尔 | 生成纯器乐（无人声）。不能与 `--lyrics` 同时使用 |
| `--vocals <text>` | 字符串 | 人声风格，例如 `"温暖的男中音"`、`"明亮的女高音"`、`"男女对唱带和声"` |
| `--genre <text>` | 字符串 | 音乐流派，例如 folk、pop、jazz |
| `--mood <text>` | 字符串 | 情绪或氛围，例如 warm、melancholic、uplifting |
| `--instruments <text>` | 字符串 | 主要乐器，例如 `"acoustic guitar, piano"` |
| `--tempo <text>` | 字符串 | 节奏描述，例如 fast、slow、moderate |
| `--bpm <number>` | 数字 | 精确 BPM 数值 |
| `--key <text>` | 字符串 | 调式，例如 C major、A minor、G sharp |
| `--avoid <text>` | 字符串 | 需要避免的元素 |
| `--use-case <text>` | 字符串 | 使用场景，例如 `"视频背景音乐"`、`"主题曲"` |
| `--structure <text>` | 字符串 | 歌曲结构，例如 `"verse-chorus-verse-bridge-chorus"` |
| `--references <text>` | 字符串 | 参考曲目或艺人，例如 `"类似 Ed Sheeran"` |
| `--extra <text>` | 字符串 | 其他细化要求 |
| `--aigc-watermark` | 布尔 | 嵌入 AIGC 水印 |
| `--format <fmt>` | 字符串 | 音频格式（默认：`mp3`） |
| `--sample-rate <hz>` | 数字 | 采样率（默认：44100） |
| `--bitrate <bps>` | 数字 | 比特率（默认：256000） |
| `--out <path>` | 字符串 | 保存音频到文件 |
| `--stream` | 布尔 | 将原始音频流式输出到 stdout |

至少需要在 `--prompt` 或 `--lyrics` 中传入一个。

```bash
# 带歌词
mmx music generate --prompt "轻快流行" --lyrics "啦啦啦..." --out song.mp3 --quiet

# 根据 prompt 自动生成歌词
mmx music generate --prompt "关于夏天的轻快流行曲" --lyrics-optimizer --out summer.mp3 --quiet

# 纯器乐
mmx music generate --prompt "电影配乐，弦乐铺底，层层递进" --instrumental --out bgm.mp3 --quiet

# 详细 prompt + 人声特征
mmx music generate --prompt "温暖的清晨民谣" \
  --vocals "男女对唱，副歌带和声" \
  --instruments "木吉他, 钢琴" \
  --bpm 95 \
  --lyrics-file song.txt \
  --out duet.mp3
```

---

### music cover

基于参考音频生成翻唱版本。

**模型：** `music-cover-free` — 对 API Key 用户不限量，RPM = 3。

```bash
mmx music cover --prompt <text> (--audio <url> | --audio-file <path>) [flags]
```

| 标志位 | 类型 | 说明 |
|---|---|---|
| `--prompt <text>` | 字符串，**必填** | 目标翻唱风格，例如 `"独立民谣，木吉他，温暖男声"` |
| `--audio <url>` | 字符串 | 参考音频 URL（mp3、wav、flac 等 — 6 秒到 6 分钟，最大 50MB） |
| `--audio-file <path>` | 字符串 | 本地参考音频文件（自动 base64 编码） |
| `--lyrics <text>` | 字符串 | 翻唱歌词。若省略，则通过 ASR 从参考音频中提取。 |
| `--lyrics-file <path>` | 字符串 | 从文件读取歌词。用 `-` 表示从 stdin 读取 |
| `--seed <number>` | 数字 | 0–1000000 的随机种子，用于可复现结果 |
| `--format <fmt>` | 字符串 | 音频格式：`mp3`、`wav`、`pcm`（默认：`mp3`） |
| `--sample-rate <hz>` | 数字 | 采样率（默认：44100） |
| `--bitrate <bps>` | 数字 | 比特率（默认：256000） |
| `--channel <n>` | 数字 | 声道数：`1`（单声道）或 `2`（立体声，默认） |
| `--out <path>` | 字符串 | 保存音频到文件 |
| `--stream` | 布尔 | 将原始音频流式输出到 stdout |

```bash
# 基于 URL 的翻唱
mmx music cover --prompt "独立民谣，木吉他，温暖男声" \
  --audio https://filecdn.minimax.chat/public/d20eda57-2e36-45bf-9e12-82d9f2e69a86.mp3 --out cover.mp3 --quiet

# 基于本地文件 + 自定义歌词
mmx music cover --prompt "爵士，钢琴，慢板" \
  --audio-file original.mp3 --lyrics-file lyrics.txt --out jazz_cover.mp3 --quiet

# 使用种子获得可复现结果
mmx music cover --prompt "流行，轻快" --audio https://filecdn.minimax.chat/public/d20eda57-2e36-45bf-9e12-82d9f2e69a86.mp3 --seed 42 --out cover.mp3
```

---

### vision describe

通过 VLM 进行图像理解。`--image` 和 `--file-id` 二选一，不可同时使用。

```bash
mmx vision describe (--image <path-or-url> | --file-id <id>) [flags]
```

| 标志位 | 类型 | 说明 |
|---|---|---|
| `--image <path-or-url>` | 字符串 | 本地路径或 URL（自动 base64 编码） |
| `--file-id <id>` | 字符串 | 预先上传的文件 ID（跳过 base64） |
| `--prompt <text>` | 字符串 | 关于图片的问题（默认：`"Describe the image."`） |

```bash
mmx vision describe --image photo.jpg --prompt "这是什么品种？" --output json
```

**stdout**：文本模式下输出描述文本；JSON 模式下输出完整响应。

---

### search query

通过 MiniMax 进行网页搜索。

```bash
mmx search query --q <query>
```

| 标志位 | 类型 | 说明 |
|---|---|---|
| `--q <query>` | 字符串，**必填** | 搜索关键词 |

```bash
mmx search query --q "MiniMax AI" --output json --quiet
```

---

### quota show

显示 Token Plan 的用量与剩余额度。

```bash
mmx quota show [--output json]
```

---

## 工具 Schema 导出

将所有命令导出为兼容 Anthropic/OpenAI 的 JSON 工具 Schema：

```bash
# 所有适合作为工具的命令（排除 auth/config/update）
mmx config export-schema

# 单个命令
mmx config export-schema --command "video generate"
```

可用于在 Agent 框架中动态把 mmx 命令注册为工具。

---

## 退出码

| 退出码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 通用错误 |
| 2 | 用法错误（参数错误、缺少参数） |
| 3 | 鉴权错误 |
| 4 | 配额超限 |
| 5 | 超时 |
| 10 | 触发内容审核 |

---

## 管道组合模式

```bash
# stdout 始终是干净数据，可安全地传入管道
mmx text chat --message "你好" --output json | jq '.content'

# stderr 是进度/旋转条等动态输出，需要时丢弃
mmx video generate --prompt "海浪" 2>/dev/null

# 链路：生成图片 → 描述图片
URL=$(mmx image generate --prompt "日落" --quiet)
mmx vision describe --image "$URL" --quiet

# 异步视频工作流
TASK=$(mmx video generate --prompt "一个机器人" --async --quiet | jq -r '.taskId')
mmx video task get --task-id "$TASK" --output json
mmx video download --task-id "$TASK" --out robot.mp4
```

---

## 配置优先级

CLI 标志位 → 环境变量 → `~/.mmx/config.json` → 默认值。

```bash
# 持久化配置
mmx config set --key region --value cn
mmx config show

# 环境变量
export MINIMAX_API_KEY=sk-xxxxx
export MINIMAX_REGION=cn
```

### 默认模型配置

为各模态设置默认模型，就不用每次都传 `--model`：

```bash
# 设置默认
mmx config set --key default-text-model --value MiniMax-M2.7-highspeed
mmx config set --key default-speech-model --value speech-2.8-hd
mmx config set --key default-video-model --value MiniMax-Hailuo-2.3
mmx config set --key default-music-model --value music-2.6

# 无需 --model 直接使用
mmx text chat --message "你好"
mmx speech synthesize --text "你好" --out hello.mp3
mmx video generate --prompt "海浪"
mmx music generate --prompt "轻快流行" --instrumental

# --model 仍可按调用覆盖
mmx text chat --model MiniMax-M2.7 --message "你好"
```

**解析优先级**：`--model` 标志位 > 配置默认值 > 内置兜底值。