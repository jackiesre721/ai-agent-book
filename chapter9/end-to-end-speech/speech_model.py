"""
可插拔的语音模型接口：端到端（end-to-end）与级联（cascaded）两种范式。

对应《深入理解 AI Agent》实验 9-3「使用 Step-Audio R1 实现端到端语音思考」。

- 端到端（EndToEndSpeechModel）：单一模型直接「听 → 想 → 说」，以 Step-Audio R1
  为代表。书中范式讨论指出：端到端在隐空间中直接传递副语言信息（情绪、语气、
  语速、环境声），延迟更低、韵律更自然，但需多卡 GPU 部署，无现成公开 endpoint。
  这里保留一个可插拔接口：仅当配置了 STEP_AUDIO_ENDPOINT 时才可调用，否则不可用。

- 级联（CascadedSpeechModel）：把 ASR → LLM → TTS 三个独立模型串成流水线，
  一棒接一棒。可用 OpenAI 的 whisper-1 / gpt-4o-mini / tts-1 真实跑通完整闭环。
  代价：模型间以离散文本接口相连，说话人的情绪、语气、语调等副语言信息在交接时
  几乎损失殆尽（见 chapter9.md 范式一 · 级联流水线）。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Optional

from openai import OpenAI


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class StageResult:
    """级联流水线中单个阶段的结果与延迟。"""

    name: str          # 阶段名（如 "ASR 语音识别"）
    model: str         # 使用的模型
    latency_s: float   # 该阶段耗时（秒）
    text: Optional[str] = None       # 文本产物（ASR 转写 / LLM 回答）
    audio_path: Optional[str] = None # 音频产物（TTS 合成）


@dataclass
class PipelineResult:
    """一次完整「语音输入 → 思考 → 语音输出」的结果。"""

    paradigm: str                 # "cascaded" 或 "end_to_end"
    input_audio: str              # 输入音频路径
    output_audio: Optional[str]   # 输出音频路径
    stages: list[StageResult] = field(default_factory=list)

    @property
    def total_latency_s(self) -> float:
        return sum(s.latency_s for s in self.stages)


# ---------------------------------------------------------------------------
# 端到端范式（占位，需部署 Step-Audio R1）
# ---------------------------------------------------------------------------
class EndToEndSpeechModel:
    """端到端语音思考模型接口（以 Step-Audio R1 为例）。

    真实部署：Step-Audio R1 由音频编码器 + 音频适配器 + Qwen2.5 32B 解码器组成，
    需多卡 GPU。它通过 MGRD（模态锚定思考蒸馏）真正基于声学特征思考，并通过
    MPS 双脑架构实现「边想边说」的低延迟表达。

    本类只是一个可插拔占位：若环境变量 STEP_AUDIO_ENDPOINT 已配置，则向该 endpoint
    发送音频并取回音频；否则 available == False，调用 run() 会抛出说明性异常。
    """

    def __init__(self) -> None:
        self.endpoint = os.getenv("STEP_AUDIO_ENDPOINT", "").strip()

    @property
    def available(self) -> bool:
        return bool(self.endpoint)

    def run(self, input_audio: str, output_audio: str) -> PipelineResult:
        if not self.available:
            raise RuntimeError(
                "端到端模型（Step-Audio R1）不可用：未配置 STEP_AUDIO_ENDPOINT。\n"
                "Step-Audio R1 无公开 endpoint，需自行多卡 GPU 部署后，将服务地址\n"
                "写入 STEP_AUDIO_ENDPOINT 环境变量。本 demo 以级联基线跑通完整闭环。"
            )

        # 说明：以下为真实部署时的调用骨架。不同部署方案（vLLM / 自定义 HTTP 服务）
        # 的请求体各异，此处给出最常见的「上传音频、取回音频」形态，供接入时改写。
        import requests  # 延迟导入：仅在真正配置 endpoint 时才需要该依赖

        t0 = time.perf_counter()
        with open(input_audio, "rb") as f:
            resp = requests.post(
                self.endpoint,
                files={"audio": f},
                timeout=120,
            )
        resp.raise_for_status()
        with open(output_audio, "wb") as out:
            out.write(resp.content)
        latency = time.perf_counter() - t0

        # 端到端只有「一段」：听→想→说融合在单次前向中，无法拆分中间文本
        stage = StageResult(
            name="端到端（听→想→说，单模型融合）",
            model="Step-Audio R1",
            latency_s=latency,
            audio_path=output_audio,
        )
        return PipelineResult(
            paradigm="end_to_end",
            input_audio=input_audio,
            output_audio=output_audio,
            stages=[stage],
        )


# ---------------------------------------------------------------------------
# 级联范式（可运行基线）
# ---------------------------------------------------------------------------
class CascadedSpeechModel:
    """级联语音流水线：ASR → LLM → TTS，三个独立模型串联。

    默认使用 OpenAI：
      - ASR：whisper-1        （语音 → 文本）
      - LLM：gpt-4o-mini      （文本思考 → 文本回答）
      - TTS：tts-1            （文本 → 语音）
    """

    def __init__(
        self,
        client: OpenAI,
        asr_model: str = "whisper-1",
        llm_model: str = "gpt-4o-mini",
        tts_model: str = "tts-1",
        tts_voice: str = "alloy",
    ) -> None:
        self.client = client
        self.asr_model = asr_model
        self.llm_model = llm_model
        self.tts_model = tts_model
        self.tts_voice = tts_voice

    # -- 阶段 1：ASR 语音识别 ------------------------------------------------
    def transcribe(self, audio_path: str) -> StageResult:
        t0 = time.perf_counter()
        with open(audio_path, "rb") as f:
            resp = self.client.audio.transcriptions.create(
                model=self.asr_model,
                file=f,
            )
        latency = time.perf_counter() - t0
        return StageResult(
            name="ASR 语音识别",
            model=self.asr_model,
            latency_s=latency,
            text=resp.text.strip(),
        )

    # -- 阶段 2：LLM 思考 ----------------------------------------------------
    def think(self, question_text: str) -> StageResult:
        t0 = time.perf_counter()
        resp = self.client.chat.completions.create(
            model=self.llm_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一个语音助手。请先进行必要的推理，再给出简洁、口语化、"
                        "适合朗读的中文回答。回答控制在三句话以内。"
                    ),
                },
                {"role": "user", "content": question_text},
            ],
            temperature=0.3,
        )
        latency = time.perf_counter() - t0
        return StageResult(
            name="LLM 思考",
            model=self.llm_model,
            latency_s=latency,
            text=resp.choices[0].message.content.strip(),
        )

    # -- 阶段 3：TTS 语音合成 ------------------------------------------------
    def synthesize(self, text: str, output_audio: str) -> StageResult:
        t0 = time.perf_counter()
        resp = self.client.audio.speech.create(
            model=self.tts_model,
            voice=self.tts_voice,
            input=text,
        )
        resp.stream_to_file(output_audio)
        latency = time.perf_counter() - t0
        return StageResult(
            name="TTS 语音合成",
            model=self.tts_model,
            latency_s=latency,
            audio_path=output_audio,
        )

    # -- 完整流水线 ----------------------------------------------------------
    def run(self, input_audio: str, output_audio: str) -> PipelineResult:
        asr = self.transcribe(input_audio)
        llm = self.think(asr.text)
        tts = self.synthesize(llm.text, output_audio)
        return PipelineResult(
            paradigm="cascaded",
            input_audio=input_audio,
            output_audio=output_audio,
            stages=[asr, llm, tts],
        )


def synthesize_question_audio(
    client: OpenAI,
    question_text: str,
    output_audio: str,
    tts_model: str = "tts-1",
    voice: str = "shimmer",
) -> None:
    """用 TTS 先合成一段「用户提问」的语音，作为级联管道的输入。"""
    resp = client.audio.speech.create(model=tts_model, voice=voice, input=question_text)
    resp.stream_to_file(output_audio)
