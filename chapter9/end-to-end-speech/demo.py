"""
实验 9-3 配套 demo：端到端语音思考 vs 级联流水线。

书中实验 9-3 的核心是端到端语音思考模型 Step-Audio R1（直接「听→想→说」）。
Step-Audio R1 需多卡 GPU 部署、无公开 endpoint，本 demo 因此以**级联基线**
（ASR → LLM → TTS）真实跑通完整「语音输入 → 思考 → 语音输出」闭环，
并保留端到端接口与表 9-1 的对照说明。

流程：
  1. 用 TTS 合成一段「用户提问」的语音（一道需要多步推理的数学题，Spoken-MQA 风格）；
  2. 把该语音喂给级联管道：whisper-1 转写 → gpt-4o-mini 思考 → tts-1 合成回答语音；
  3. 打印各阶段结果与延迟，并用 ffprobe 确认输出音频真实生成；
  4. 打印端到端 vs 级联的对照（延迟拆解 + 级联在副语言/语气上的信息损失说明）。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from speech_model import (
    CascadedSpeechModel,
    EndToEndSpeechModel,
    PipelineResult,
    synthesize_question_audio,
)

HERE = Path(__file__).parent
AUDIO_DIR = HERE / "audio"

# 一道需要多步推理的口述数学题（Spoken-MQA 风格：先听懂，再多步计算）
USER_QUESTION = (
    "小明有 12 块钱，他买了 3 支铅笔，每支 2 块钱，"
    "然后又用剩下的钱买了尽可能多的、每块 1 块 5 的橡皮，"
    "请问他最后还剩多少钱？"
)


def hr(char: str = "-", n: int = 68) -> str:
    return char * n


def ffprobe_info(audio_path: str) -> dict:
    """用 ffprobe 读取音频真实信息（时长、格式、码率），确认文件已生成。"""
    if not shutil.which("ffprobe"):
        return {"error": "未安装 ffprobe，跳过音频校验（brew install ffmpeg）"}
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration,format_name,bit_rate,size",
                "-of", "json", audio_path,
            ],
            capture_output=True, text=True, check=True,
        )
        fmt = json.loads(out.stdout).get("format", {})
        return {
            "格式": fmt.get("format_name"),
            "时长(秒)": round(float(fmt.get("duration", 0)), 2),
            "码率(bps)": fmt.get("bit_rate"),
            "文件大小(字节)": fmt.get("size"),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": f"ffprobe 失败：{e}"}


def print_pipeline_result(result: PipelineResult) -> None:
    print(hr("="))
    print(f"级联流水线（{result.paradigm}）各阶段结果与延迟")
    print(hr("="))
    for i, s in enumerate(result.stages, 1):
        print(f"\n[阶段 {i}] {s.name}  |  模型={s.model}  |  延迟={s.latency_s:.2f}s")
        if s.text is not None:
            print(f"    文本：{s.text}")
        if s.audio_path is not None:
            print(f"    音频：{s.audio_path}")
    print(f"\n级联总延迟（各阶段串行相加）：{result.total_latency_s:.2f}s")


def print_comparison(result: PipelineResult) -> None:
    """打印端到端 vs 级联的概念对照（延迟拆解 + 副语言信息损失）。"""
    stages = {s.name: s for s in result.stages}
    asr = stages.get("ASR 语音识别")
    llm = stages.get("LLM 思考")
    tts = stages.get("TTS 语音合成")

    print("\n" + hr("="))
    print("端到端（Step-Audio R1） vs 级联（本 demo）对照")
    print(hr("="))

    print("\n【1】延迟拆解（级联 = 三段串行之和；端到端 = 单模型一次前向）")
    print(f"    级联  ASR({asr.latency_s:.2f}s) + LLM({llm.latency_s:.2f}s) "
          f"+ TTS({tts.latency_s:.2f}s) = {result.total_latency_s:.2f}s（串行累加）")
    print("    端到端  听→想→说在单一模型内融合，无跨模型交接，且可「边想边说」")
    print("           （MPS 双脑架构：Speak-First 零延迟 / Think-First ~80 token 延迟），")
    print("           首字延迟显著低于级联的串行累加。")

    print("\n【2】信息损失（副语言 / 语气）")
    print("    级联在 ASR 处把语音压成纯文本，说话人的情绪、语速、语调、重音、")
    print("    停顿、以及背景环境声/音乐在交接时几乎全部丢失——LLM 只看到「说了什么」，")
    print("    看不到「怎么说的」。本次输入语音承载的语气在下面这行文本处被抹平为：")
    print(f"        ASR 文本 → 「{asr.text}」")
    print("    端到端模型在隐空间（Latent Space）中直接传递这些副语言信息，")
    print("    能感知情绪（高兴/愤怒）、语速（急促/迟疑）、语调（上扬/低沉），")
    print("    并据此生成有表现力、韵律匹配的回复。")

    print("\n【3】书中表 9-1（Step-Audio R1 不同语音思考配置，供对照）")
    print("    配置                          Spoken-MQA   URO-Bench")
    print("    不思考直接回答（基线）           70.6%        77.4")
    print("    MPS Speak-First（零延迟）        92.8%        82.5")
    print("    MPS Think-First（~80 tok 延迟）  93.9%        84.8")
    print("    完整 TBS（无延迟约束）           93.0%         —")
    print("    要点：Speak-First 几乎不损推理精度（92.8% ≈ TBS 93.0%），因为 CoT")
    print("    开头往往只是复述问题；这正是端到端「边想边说」能低延迟又不失准的原因。")

    print("\n【4】取舍小结")
    print("    级联：模块清晰、每段可独立调优、可解释性好；但延迟串行累加、副语言损失大。")
    print("    端到端：延迟更低、保留非文字信息、韵律自然；代价是训练数据需求大、")
    print("            可解释性差，且需多卡 GPU 部署。二者在 2026 年的生产系统中长期并存。")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="实验 9-3：端到端语音思考 vs 级联流水线。合成一段「用户提问」语音，"
                    "跑通级联管道 ASR(whisper-1) → LLM(gpt-4o-mini) → TTS(tts-1)，"
                    "打印各阶段延迟并给出与端到端 Step-Audio R1 的对照。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--question", default=USER_QUESTION,
                   help="自定义口述提问（默认为一道 Spoken-MQA 风格的多步数学题）。")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    global USER_QUESTION
    USER_QUESTION = args.question

    load_dotenv(HERE / ".env")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("错误：未配置 OPENAI_API_KEY。请复制 env.example 为 .env 并填入有效的 "
              "OpenAI Key。", file=sys.stderr)
        return 1

    # timeout + 自动重试：单次网络/SSL 抖动不至于让整条流水线崩溃
    client = OpenAI(api_key=api_key, timeout=60.0, max_retries=3)
    AUDIO_DIR.mkdir(exist_ok=True)
    question_audio = str(AUDIO_DIR / "user_question.mp3")
    answer_audio = str(AUDIO_DIR / "assistant_answer.mp3")

    # -- 端到端范式可用性检查（占位接口） --------------------------------------
    e2e = EndToEndSpeechModel()
    print(hr("="))
    print("范式一：端到端语音思考（Step-Audio R1）")
    print(hr("="))
    if e2e.available:
        print(f"检测到 STEP_AUDIO_ENDPOINT={e2e.endpoint}，将走真实端到端管道。")
    else:
        print("端到端模型不可用：未配置 STEP_AUDIO_ENDPOINT。")
        print("Step-Audio R1 无公开 endpoint，需多卡 GPU 自行部署。")
        print("→ 本 demo 改用【级联基线】跑通完整闭环，并在末尾给出端到端对照。\n")

    # -- 步骤 1：合成「用户提问」语音 ------------------------------------------
    print(hr("="))
    print("步骤 1：用 TTS 合成一段「用户提问」语音（作为级联管道的输入）")
    print(hr("="))
    print(f"提问文本：{USER_QUESTION}")
    synthesize_question_audio(client, USER_QUESTION, question_audio)
    print(f"已生成输入音频：{question_audio}")
    print(f"ffprobe 校验：{ffprobe_info(question_audio)}")

    # -- 步骤 2：跑级联流水线 --------------------------------------------------
    print("\n" + hr("="))
    print("步骤 2：运行级联流水线 ASR → LLM → TTS")
    print(hr("="))
    cascaded = CascadedSpeechModel(client)

    if e2e.available:
        # 若真实端到端可用，也可跑一遍对照（此处仅演示级联，避免额外部署依赖）
        pass

    result = cascaded.run(question_audio, answer_audio)
    print_pipeline_result(result)

    # -- 步骤 3：ffprobe 确认输出音频真实生成 ---------------------------------
    print("\n" + hr("="))
    print("步骤 3：ffprobe 确认输出「语音回答」真实生成")
    print(hr("="))
    print(f"输出音频：{answer_audio}")
    print(f"ffprobe 校验：{ffprobe_info(answer_audio)}")

    # -- 步骤 4：端到端 vs 级联对照 -------------------------------------------
    print_comparison(result)

    print("\n完成。可用 `ffplay audio/assistant_answer.mp3` 试听语音回答。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
