#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
实验 5-5：论文讲解视频的自动生成（★★）

流水线（端到端自包含，无需依赖 5-4）：
  1) 幻灯片：用 PIL 生成若干页带标题/要点的 PNG（模拟“论文 -> PPT”的产物）。
  2) 讲解词：对每一页调用 gpt-4o-mini 生成【口语化、引导性】的讲解文字
            （是叙述而非复述要点，负责承上启下）。
  3) TTS：用 OpenAI tts-1（voice=alloy）把讲解词合成为每页的语音 mp3。
  4) 合成：用 ffmpeg 把「每页 PNG + 该页音频」合成为分段视频（每页时长=该页音频时长），
          再用 concat 拼接为一个 output/lecture.mp4。
  5) 校验：用 ffprobe 打印最终 mp4 的时长/分辨率/音视频流信息。

依赖：ffmpeg / ffprobe（命令行）、Python 包见 requirements.txt。
环境变量：OPENAI_API_KEY（必填），可选 OPENAI_BASE_URL / TEXT_MODEL / TTS_MODEL / TTS_VOICE。
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from openai import OpenAI

# ---------------------------------------------------------------------------
# 路径与配置
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
SLIDES_DIR = OUTPUT_DIR / "slides"
AUDIO_DIR = OUTPUT_DIR / "audio"
SEG_DIR = OUTPUT_DIR / "segments"
FINAL_MP4 = OUTPUT_DIR / "lecture.mp4"

TEXT_MODEL = os.getenv("TEXT_MODEL", "gpt-4o-mini")
TTS_MODEL = os.getenv("TTS_MODEL", "tts-1")
TTS_VOICE = os.getenv("TTS_VOICE", "alloy")

# 视频参数
WIDTH, HEIGHT = 1280, 720
FPS = 30

# macOS 上可用的中文字体（按优先级回退）
FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]

# ---------------------------------------------------------------------------
# 模拟“论文 -> PPT”的产物：每页的标题与要点。
# 这里用《Attention Is All You Need》（Transformer）作为示例论文。
# 在真实的 5-4 流程中，这些数据由 Proposer/Reviewer Agent 从论文 PDF 生成。
# ---------------------------------------------------------------------------
SLIDES = [
    {
        "title": "Attention Is All You Need",
        "subtitle": "Transformer：一种全新的序列建模架构",
        "bullets": [
            "Vaswani 等人，2017 年发表于 NeurIPS",
            "完全基于注意力机制，抛弃循环与卷积",
            "在机器翻译任务上取得当时最优效果",
        ],
    },
    {
        "title": "研究背景与动机",
        "subtitle": "为什么要抛弃 RNN？",
        "bullets": [
            "RNN 按时间步串行计算，难以并行",
            "长距离依赖在梯度传播中容易衰减",
            "训练大模型时的计算效率成为瓶颈",
        ],
    },
    {
        "title": "核心方法：自注意力",
        "subtitle": "Self-Attention 与多头机制",
        "bullets": [
            "用 Query / Key / Value 计算词与词的关联",
            "多头注意力从不同子空间捕捉多种关系",
            "位置编码为模型注入序列顺序信息",
        ],
    },
    {
        "title": "实验结果",
        "subtitle": "更快、更准",
        "bullets": [
            "WMT14 英德翻译 BLEU 达 28.4，创新高",
            "训练成本显著低于此前的最优模型",
            "可高度并行，充分利用 GPU 算力",
        ],
    },
    {
        "title": "总结与影响",
        "subtitle": "开启大模型时代",
        "bullets": [
            "Transformer 成为 NLP 的通用骨架",
            "催生 BERT、GPT 等预训练大模型",
            "影响扩展到视觉、语音、多模态领域",
        ],
    },
]


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def load_font(size: int) -> ImageFont.FreeTypeFont:
    """按候选列表加载一个可用字体（支持中文）。"""
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def run(cmd: list) -> str:
    """执行命令并返回 stdout，失败则抛出异常并打印 stderr。"""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"命令失败: {' '.join(cmd)}\nSTDERR:\n{proc.stderr}"
        )
    return proc.stdout


def ffprobe_duration(path: Path) -> float:
    """用 ffprobe 读取媒体文件时长（秒）。"""
    out = run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    return float(out.strip())


# ---------------------------------------------------------------------------
# 步骤 1：渲染幻灯片 PNG
# ---------------------------------------------------------------------------
def render_slide(slide: dict, index: int, total: int) -> Path:
    """把一页幻灯片渲染为 1280x720 的 PNG。"""
    img = Image.new("RGB", (WIDTH, HEIGHT), color=(23, 32, 56))  # 深蓝底
    draw = ImageDraw.Draw(img)

    title_font = load_font(58)
    subtitle_font = load_font(34)
    bullet_font = load_font(32)
    footer_font = load_font(22)

    # 顶部装饰条
    draw.rectangle([0, 0, WIDTH, 12], fill=(88, 166, 255))

    # 标题（超宽自动换行）
    y = 90
    for line in textwrap.wrap(slide["title"], width=22):
        draw.text((90, y), line, font=title_font, fill=(255, 255, 255))
        y += 72

    # 副标题
    y += 6
    draw.text((90, y), slide["subtitle"], font=subtitle_font, fill=(88, 166, 255))
    y += 70

    # 要点
    for bullet in slide["bullets"]:
        draw.ellipse([94, y + 14, 110, y + 30], fill=(88, 166, 255))
        for j, line in enumerate(textwrap.wrap(bullet, width=30)):
            draw.text((130, y), line, font=bullet_font, fill=(220, 226, 240))
            y += 44
        y += 16

    # 页脚：页码
    footer = f"第 {index + 1} / {total} 页"
    draw.text((90, HEIGHT - 50), footer, font=footer_font, fill=(120, 132, 160))

    path = SLIDES_DIR / f"slide_{index + 1:02d}.png"
    img.save(path)
    return path


# ---------------------------------------------------------------------------
# 步骤 2：为每页生成口语化讲解词
# ---------------------------------------------------------------------------
def generate_narration(client: OpenAI, slide: dict, index: int, total: int) -> str:
    """调用 gpt-4o-mini，为当前页生成口语化、引导性的讲解文字。"""
    position = (
        "这是开场第一页，请自然地引入主题" if index == 0
        else "这是最后一页，请做收尾总结" if index == total - 1
        else "这是中间页，请与上一页自然衔接、承上启下"
    )
    prompt = (
        "你是一位科普讲师，正在为一段论文讲解视频配音。\n"
        f"当前是第 {index + 1}/{total} 页幻灯片。{position}。\n\n"
        f"幻灯片标题：{slide['title']}\n"
        f"副标题：{slide['subtitle']}\n"
        f"要点：\n- " + "\n- ".join(slide["bullets"]) + "\n\n"
        "请生成这一页的口语化讲解词，要求：\n"
        "1) 是引导性的口语叙述，而不是逐条复述要点；\n"
        "2) 自然流畅、有过渡，像真人讲课；\n"
        "3) 长度控制在 3~4 句话（约 70~110 字）；\n"
        "4) 只输出讲解词正文，不要任何前后缀、标题或列表符号。"
    )
    resp = client.chat.completions.create(
        model=TEXT_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# 步骤 3：TTS 合成语音
# ---------------------------------------------------------------------------
def synthesize_speech(client: OpenAI, text: str, index: int) -> Path:
    """用 OpenAI tts-1 把讲解词合成为 mp3。"""
    path = AUDIO_DIR / f"audio_{index + 1:02d}.mp3"
    # 使用流式写盘接口，避免把整段音频读进内存
    with client.audio.speech.with_streaming_response.create(
        model=TTS_MODEL,
        voice=TTS_VOICE,
        input=text,
    ) as response:
        response.stream_to_file(str(path))
    return path


# ---------------------------------------------------------------------------
# 步骤 4：ffmpeg 合成
# ---------------------------------------------------------------------------
def build_segment(png: Path, mp3: Path, index: int, duration: float) -> Path:
    """把「一页 PNG + 该页音频」合成为一段 mp4。

    用 -t 把整段时长精确锁定为该页音频时长，保证“每页展示时间与语音时长精确匹配”
    （仅靠 -loop + -shortest 会让静态图轨比音频多出约 1~2 秒）。
    """
    out = SEG_DIR / f"seg_{index + 1:02d}.mp4"
    run(
        [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(png),      # 静态图片循环作为视频轨
            "-i", str(mp3),                     # 该页音频
            "-c:v", "libx264", "-tune", "stillimage",
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            "-vf", f"scale={WIDTH}:{HEIGHT}",
            "-c:a", "aac", "-b:a", "192k",
            "-t", f"{duration:.3f}",            # 精确锁定为音频时长
            str(out),
        ]
    )
    return out


def concat_segments(segments: list) -> Path:
    """用 concat demuxer 把各分段无损拼接为最终 mp4。"""
    list_file = SEG_DIR / "concat.txt"
    list_file.write_text(
        "".join(f"file '{seg.name}'\n" for seg in segments), encoding="utf-8"
    )
    run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            str(FINAL_MP4),
        ]
    )
    return FINAL_MP4


# ---------------------------------------------------------------------------
# 自检（不产生任何 API 调用）：检查外部命令与关键配置是否就绪。
# ---------------------------------------------------------------------------
def self_check() -> int:
    """快速自检 ffmpeg/ffprobe、中文字体与关键环境变量，返回退出码。"""
    ok = True
    print("=== 环境自检（不调用任何 API）===")

    for tool in ("ffmpeg", "ffprobe"):
        found = shutil.which(tool)
        print(f"  {'[OK]' if found else '[缺失]'} {tool}: {found or '未找到，请安装 ffmpeg'}")
        ok = ok and bool(found)

    font = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)
    print(f"  {'[OK]' if font else '[回退]'} 中文字体: {font or '未找到系统中文字体，将回退默认字体'}")

    key_set = bool(os.getenv("OPENAI_API_KEY"))
    print(f"  {'[OK]' if key_set else '[缺失]'} OPENAI_API_KEY: {'已设置' if key_set else '未设置'}")
    print(f"  [配置] TEXT_MODEL={TEXT_MODEL}  TTS_MODEL={TTS_MODEL}  TTS_VOICE={TTS_VOICE}")
    print(f"  [配置] OPENAI_BASE_URL={os.getenv('OPENAI_BASE_URL') or '（官方默认）'}")
    print(f"  [配置] 内置幻灯片页数={len(SLIDES)}")

    print("自检" + ("通过。" if ok else "未通过：请先安装缺失的命令行工具。"))
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main(limit: int | None = None) -> None:
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("[错误] 未设置 OPENAI_API_KEY，请复制 env.example 为 .env 并填入。")

    for d in (SLIDES_DIR, AUDIO_DIR, SEG_DIR):
        d.mkdir(parents=True, exist_ok=True)

    # timeout / max_retries：TTS/文本调用偶发网络抖动时自动重试，不至于整轮崩溃
    client = OpenAI(
        base_url=os.getenv("OPENAI_BASE_URL") or None,
        timeout=120.0,
        max_retries=3,
    )

    # --limit / --quick：只处理前 N 页，便于快速冒烟测试（减少 API 调用与耗时）。
    slides = SLIDES[:limit] if limit else SLIDES
    total = len(slides)
    segments = []
    manifest = []

    tag = f"（限 {total}/{len(SLIDES)} 页）" if limit else f"（共 {total} 页）"
    print(f"=== 论文讲解视频自动生成{tag}===\n")

    for i, slide in enumerate(slides):
        print(f"[{i + 1}/{total}] {slide['title']}")

        # 1) 渲染幻灯片
        png = render_slide(slide, i, total)
        print(f"    幻灯片: {png.relative_to(ROOT)}")

        # 2) 生成口语化讲解词
        narration = generate_narration(client, slide, i, total)
        print(f"    讲解词: {narration}")

        # 3) TTS 合成语音
        mp3 = synthesize_speech(client, narration, i)
        dur = ffprobe_duration(mp3)
        print(f"    音频:   {mp3.relative_to(ROOT)}  时长 {dur:.2f}s")

        # 4) 合成分段视频
        seg = build_segment(png, mp3, i, dur)
        segments.append(seg)
        manifest.append(
            {"page": i + 1, "narration": narration,
             "audio": str(mp3.relative_to(ROOT)), "audio_seconds": round(dur, 2)}
        )
        print()

    # 5) 拼接为最终视频
    print("=== 拼接为最终视频 ===")
    concat_segments(segments)

    audio_total = sum(m["audio_seconds"] for m in manifest)
    video_total = ffprobe_duration(FINAL_MP4)

    # 保存讲解词清单，便于查看
    (OUTPUT_DIR / "narration.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"各页音频总时长: {audio_total:.2f}s")
    print(f"最终视频时长:   {video_total:.2f}s")
    print(f"输出文件:       {FINAL_MP4.relative_to(ROOT)}")
    print("\n完成。可用以下命令查看视频元信息：")
    print(f"  ffprobe -v error -show_format -show_streams {FINAL_MP4}")


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="论文讲解视频自动生成：讲解词生成 -> TTS -> ffmpeg 逐页合成。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python demo.py            # 生成全部 5 页的完整讲解视频\n"
            "  python demo.py --quick    # 只跑第 1 页，快速冒烟测试\n"
            "  python demo.py --limit 2  # 只跑前 2 页\n"
            "  python demo.py --check    # 仅环境自检，不调用任何 API"
        ),
    )
    parser.add_argument(
        "--limit", type=int, default=None, metavar="N",
        help="只处理前 N 页幻灯片（快速测试，显著减少 API 调用与耗时）",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help="快速测试：等价于 --limit 1",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="环境自检（检查 ffmpeg/ffprobe/字体/配置）后退出，不产生任何 API 调用",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.check:
        sys.exit(self_check())
    limit = 1 if args.quick else args.limit
    if limit is not None and limit < 1:
        sys.exit("[错误] --limit 必须为正整数。")
    main(limit=limit)
