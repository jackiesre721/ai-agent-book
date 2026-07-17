"""
实验 9-5 演示：控制标记驱动的可控 TTS
======================================

演示两件事：
  1) 三种配置对比（书中要求）：同一段带控制标记的文本，分别用
     A. 无控制标记（流畅但机械）
     B. 单一参考语音（自然但情感单调）
     C. 多参考语音库（按控制标记切换情感/语速/停顿，接近真人客服）
  2) 同一句文本、不同控制标记 -> 合成出多个不同风格的音频。

运行：python demo.py
输出：output/*.mp3
"""

import argparse
import os
import re
import subprocess

from dotenv import load_dotenv

from markup import parse
from tts import synthesize_segments, PREFERRED_MODEL

load_dotenv()

OUT_DIR = os.path.join(os.path.dirname(__file__), "output")
TMP_DIR = os.path.join(OUT_DIR, ".tmp")

# 书中给出的 LLM 输出示例（带控制标记）
DEMO_TEXT = ("[EMO:happy][SPEED:fast]太好了！您的订单已确认。"
             "[THINKING]嗯，让我查一下发货时间..."
             "[EMO:neutral][SPEED:normal]预计明天下午送达。")

# 同一句文本 + 不同控制标记 -> 不同风格
STYLE_VARIANTS = {
    "variant_happy_fast":  "[情感=高兴][语速=快]您的订单已确认，预计明天下午送达。",
    "variant_frustrated":  "[情感=沮丧][语速=慢]您的订单已确认，预计明天下午送达。",
    "variant_thinking":    "[THINKING]您的订单已确认，[PAUSE]预计明天下午送达。",
    "variant_casual_laugh": "[情感=兴奋][风格=轻松]您的订单已确认<laugh>，预计明天下午送达。",
    "variant_emphasis":    "您的订单<emphasis>已确认</emphasis>，预计<emphasis>明天下午</emphasis>送达。",
}


def strip_markers(text: str) -> str:
    """去掉所有控制标记，得到纯文本（用于「无控制标记」基线）。"""
    return re.sub(r"\[[^\]]*\]|<[^>]+>", "", text).strip()


def ffprobe(path: str) -> str:
    """打印 mp3 的时长/格式/码率，证明音频真实生成。"""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration,format_name,bit_rate", "-of",
         "default=noprint_wrappers=1:nokey=0", path],
        capture_output=True, text=True,
    ).stdout.strip().replace("\n", "  ")
    size = os.path.getsize(path)
    return f"{out}  size={size}B"


def render(name: str, segments, print_info=True):
    """合成一个音频文件并打印其合成信息 + ffprobe。"""
    out_path = os.path.join(OUT_DIR, f"{name}.mp3")
    info = synthesize_segments(segments, out_path, os.path.join(TMP_DIR, name))
    if print_info:
        for seg in info:
            if seg["type"] == "silence":
                print(f"    · [静音 {seg['ms']}ms]")
            else:
                emph = " +强调" if "强调" in seg.get("instructions", "") else ""
                print(f"    · [{seg['profile']:26s}{emph}] {seg['model']:16s} "
                      f"voice={seg['voice']} text='{seg['text']}'")
    print(f"  => {os.path.relpath(out_path)}  |  {ffprobe(out_path)}")
    return out_path


def parse_args():
    p = argparse.ArgumentParser(
        description="实验 9-5：控制标记驱动的可控 TTS。同一段带控制标记的文本，"
                    "对比「无标记 / 单一参考语音 / 多参考语音库」三种配置，"
                    "并合成多个不同风格的变体音频。输出到 output/*.mp3。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--quick", action="store_true",
        help="仅跑三种配置对比（A/B/C），跳过 5 个风格变体，减少 TTS 调用与耗时。",
    )
    return p.parse_args()


def main():
    args = parse_args()
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("请先设置 OPENAI_API_KEY（见 env.example）")
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"首选模型: {PREFERRED_MODEL}（不可用时自动兜底 tts-1）"
          f"{'  [--quick 模式：跳过风格变体]' if args.quick else ''}\n")

    # ================= 三种配置对比 =================
    print("=" * 72)
    print("对比实验：同一段带控制标记的文本，三种配置")
    print("原始文本:", DEMO_TEXT)
    print("=" * 72)

    # ---- 配置 A：无控制标记（基线，流畅但机械）----
    print("\n[A] 无控制标记（strip 掉所有标记，单次默认合成）")
    plain = strip_markers(DEMO_TEXT)
    print("    纯文本:", plain)
    seg_a = parse(plain)  # 无标记 -> 单个中性片段
    render("A_no_markers", seg_a)

    # ---- 配置 B：单一参考语音（自然但情感单调）----
    print("\n[B] 单一参考语音（去标记，全程用同一条中性/正常/正式参考语音）")
    seg_b = [dict(type="speech", text=plain, emotion="neutral",
                  speed="normal", style="formal", emphasis=False)]
    render("B_single_voice", seg_b)

    # ---- 配置 C：多参考语音库（按控制标记切换）----
    print("\n[C] 多参考语音库（解析控制标记 -> 逐段切换参考语音 + 停顿）")
    trace = []
    seg_c = parse(DEMO_TEXT, trace=trace)
    print("    -- 控制标记解析过程 --")
    for line in trace:
        print(line)
    print("    -- 合成片段 --")
    render("C_voice_library", seg_c)

    # ================= 同文本 / 不同控制标记 =================
    if not args.quick:
        print("\n" + "=" * 72)
        print("同一句文本 + 不同控制标记 -> 不同风格音频")
        print("=" * 72)
        for name, text in STYLE_VARIANTS.items():
            print(f"\n[{name}] {text}")
            trace = []
            segs = parse(text, trace=trace)
            for line in trace:
                print(line)
            render(name, segs)

    # ================= 汇总 =================
    print("\n" + "=" * 72)
    print("全部输出文件（ffprobe 时长对比）")
    print("=" * 72)
    for f in sorted(os.listdir(OUT_DIR)):
        if f.endswith(".mp3"):
            p = os.path.join(OUT_DIR, f)
            print(f"  {f:26s} {ffprobe(p)}")


if __name__ == "__main__":
    main()
