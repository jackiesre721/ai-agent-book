# 实验 5-5：论文讲解视频的自动生成 ★★

在“论文 → PPT”的基础上，Agent 为每一页幻灯片生成**口语化讲解词**（引导性叙述，
而非逐条复述要点），调用 **TTS** 合成语音，再用 **ffmpeg** 把 PPT 截图与音频
**逐页同步合成**为一段带旁白的讲解视频。

## 流程

```
论文要点(内置示例)
   │  PIL 渲染
   ▼
每页 PNG 幻灯片 ──► gpt-4o-mini 生成口语化讲解词 ──► OpenAI tts-1 合成 mp3
   │                                                        │
   └──────────────── ffmpeg：每页 PNG + 该页音频 ───────────┘
                              │  (每页时长 = 该页音频时长)
                              ▼
                     ffmpeg concat 拼接
                              ▼
                     output/lecture.mp4
```

- 本项目**自包含**，不依赖实验 5-4：内置一份《Attention Is All You Need》的论文要点，
  用 PIL 直接渲染出 5 页幻灯片 PNG（也可替换为 5-4 的 Slidev 截图）。
- 讲解词由 `gpt-4o-mini` 生成；语音由 OpenAI `tts-1`（`voice=alloy`）合成。
- 视频由 `ffmpeg` 合成：每页做一段 mp4，段时长等于该页音频时长，最后 concat 拼接，
  因此**每页展示时间与语音时长精确匹配**。

## 运行

```bash
pip install -r requirements.txt      # 安装 Python 依赖
cp env.example .env                  # 填入 OPENAI_API_KEY
python demo.py                       # 生成讲解词 → TTS → 合成视频
```

产物：
- `output/slides/slide_*.png`   每页幻灯片
- `output/audio/audio_*.mp3`    每页讲解音频
- `output/segments/seg_*.mp4`   每页分段视频
- `output/narration.json`       每页讲解词与音频时长清单
- `output/lecture.mp4`          最终讲解视频

查看视频元信息：

```bash
ffprobe -v error -show_format -show_streams output/lecture.mp4
```

## 依赖

- **ffmpeg / ffprobe**：命令行工具（本项目用 8.x 验证）。macOS 可 `brew install ffmpeg`。
- **Python 包**：`openai`、`Pillow`、`python-dotenv`（见 `requirements.txt`）。
- **中文字体**：渲染幻灯片需系统中文字体，脚本已按 macOS 常见字体
  （PingFang / STHeiti / Hiragino / Arial Unicode）自动回退。
- **环境变量**：仅需 `OPENAI_API_KEY`（走官方 OpenAI）；可选项见 `env.example`。

## 注意事项

- 讲解词与 TTS 都会产生真实的 OpenAI API 调用（`gpt-4o-mini` 与 `tts-1`），会计费。
- 若要生成更长（5~15 分钟）的视频，增加 `SLIDES` 页数或加长每页讲解词即可。
- 更换论文：编辑 `demo.py` 中的 `SLIDES` 列表；或把幻灯片渲染换成 5-4 的 Slidev 截图，
  其余流程不变。
