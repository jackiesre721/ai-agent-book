# 实验 9-3 配套：端到端语音思考 vs 级联流水线

对应《深入理解 AI Agent》第 9 章 **实验 9-3 ★★★：使用 Step-Audio R1 实现端到端语音思考**。

## 目的

书中实验 9-3 的核心是**端到端语音思考模型 Step-Audio R1**：单一模型直接「听 → 想 → 说」，把 ASR、LLM、TTS 三段合而为一，在隐空间中直接传递副语言信息（情绪、语气、语速、环境声），延迟更低、韵律更自然。

本 demo 帮助你**动手跑通一条完整的「语音输入 → 思考 → 语音输出」闭环**，并直观对比端到端与级联两种范式在**延迟**与**信息损失（语气、副语言）**上的差异。

## 两种范式

| 范式 | 结构 | 优点 | 代价 |
|------|------|------|------|
| **级联（Cascaded）** | ASR → LLM → TTS 三个独立模型串联 | 模块清晰、每段可独立调优、可解释性好 | 延迟串行累加；模型间以纯文本接口相连，说话人情绪/语速/语调/环境声在交接时几乎全部丢失 |
| **端到端（End-to-End）** | 单一模型「听→想→说」（Step-Audio R1） | 延迟更低、可「边想边说」、保留副语言信息、韵律自然 | 训练数据需求大、可解释性差、需多卡 GPU 部署 |

书中 **表 9-1**（Step-Audio R1 不同配置）显示：MPS Speak-First（零延迟）在 Spoken-MQA 上达 92.8%，已逼近完整 TBS 的 93.0%——因为思维链（CoT）开头往往只是复述问题，让模型「一开口就同时启动思考」几乎不损精度。这正是端到端「边想边说」能低延迟又不失准的原因。

## 模型可用性适配（重要）

**Step-Audio R1 无现成可用的公开 endpoint/key**（由音频编码器 + 音频适配器 + Qwen2.5 32B 解码器组成，需多卡 GPU 部署）。因此本 demo：

- 提供一个**可插拔的端到端接口** `EndToEndSpeechModel`：仅当配置了环境变量 `STEP_AUDIO_ENDPOINT` 时才会调用真实端到端服务；否则标记为「不可用」，并给出部署说明。
- 以**可运行的级联基线**跑通完整闭环，全部使用 OpenAI 模型：
  - **ASR**：`whisper-1`（语音 → 文本）
  - **LLM**：`gpt-4o-mini`（文本思考 → 文本回答）
  - **TTS**：`tts-1`（文本 → 语音）

真实的端到端体验需要自行部署 Step-Audio R1，再把服务地址写入 `STEP_AUDIO_ENDPOINT`。

## 运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 Key
cp env.example .env
# 编辑 .env，填入有效的 OPENAI_API_KEY

# 3. 运行
python demo.py

# 4.（可选）试听生成的语音回答
ffplay audio/assistant_answer.mp3
```

依赖 `ffprobe`/`ffplay`（用于校验、试听音频）：`brew install ffmpeg`（macOS）。

## demo 做了什么

1. 用 TTS 合成一段**用户提问**语音（一道需多步推理的口述数学题，Spoken-MQA 风格）；
2. 把该语音喂给**级联管道**：`whisper-1` 转写 → `gpt-4o-mini` 思考 → `tts-1` 合成回答语音；
3. 打印**各阶段结果与延迟**，并用 `ffprobe` 确认输入/输出音频真实生成；
4. 打印**端到端 vs 级联对照**：延迟拆解（级联三段串行 vs 端到端单模型融合 + 边想边说）、副语言/语气的信息损失说明、以及书中表 9-1。

## 文件

- `demo.py`：可运行主程序（`python demo.py`）。
- `speech_model.py`：`SpeechModel` 抽象——`EndToEndSpeechModel`（占位/可插拔）与 `CascadedSpeechModel`（可运行）。
- `requirements.txt` / `env.example`：依赖与环境变量样例。
- `audio/`：运行时生成的输入/输出音频。

## 注意

- 本 demo 用「文本 TTS → 输入语音」来构造带语气的输入，仅用于演示闭环；真实场景中输入来自用户的真实麦克风音频，副语言信息更丰富，级联的损失也更明显。
- 级联的延迟是三段**串行相加**；端到端可「边想边说」并行，首字延迟通常显著更低。demo 打印的延迟数字会随网络与 OpenAI 负载波动。
