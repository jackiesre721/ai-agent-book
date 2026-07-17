"""
实验 5-4：基于论文的 PPT 自动生成（提议者-审核者机制）

完整流程：
  1. 从精简论文（paper/sample_paper.md）+ 程序化复现的图表出发；
  2. 【双 Agent】Proposer 生成 slides.md → Slidev 渲染每页 PNG → Reviewer 用 Vision LLM
     看图给出结构化建议 → Proposer 据反馈修订 → 迭代，直到 pass 或达最大轮数；
  3. 【单 Agent 自审】同一个 Agent 生成 → 渲染 → 把自己的截图塞回**同一上下文**自审并修订 → 迭代；
  4. 用同一位“独立评委”（Vision）给两种方案的最终 PPT 打分，公平比较**质量**；
  5. 打印两种方案的**上下文 token 消耗**对比（总量、峰值单次 prompt token）。

运行：python demo.py            # 完整对比（两种方案）
     python demo.py --help     # 查看全部参数
     python demo.py --mode dual --max-rounds 1   # 快速：只跑双 Agent、只出首版
     python demo.py --smoke     # 仅验证 Slidev 渲染链路，不调用任何 LLM
依赖：Node/Slidev（渲染）、OPENAI_API_KEY（gpt-4o 视觉 + 文本）。
"""
import argparse
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from agents import (  # noqa: E402
    Proposer, Reviewer, SelfReviewAgent, TokenMeter, independent_judge,
    TEXT_MODEL, VISION_MODEL,
)
from make_figures import generate_all  # noqa: E402
from renderer import render_slides  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER_PATH = os.path.join(HERE, "paper", "sample_paper.md")
OUT_DIR = os.path.join(HERE, "output")
MAX_ROUNDS = 3  # 每种方案的最大迭代轮数（首轮 + 最多 2 轮修订）


def banner(title):
    print("\n" + "=" * 74)
    print(f"  {title}")
    print("=" * 74)


def save_text(name, text):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def summarize_review(review: dict) -> str:
    n_high = sum(1 for x in review.get("issues", []) if x.get("severity") == "high")
    n_med = sum(1 for x in review.get("issues", []) if x.get("severity") == "medium")
    n_low = sum(1 for x in review.get("issues", []) if x.get("severity") == "low")
    return (f"score={review.get('overall_score')} pass={review.get('pass')} "
            f"issues={len(review.get('issues', []))} (high={n_high}, med={n_med}, low={n_low})")


# --------------------------------------------------------------------------- #
# 方案 A：提议者-审核者（双 Agent）
# --------------------------------------------------------------------------- #
def run_proposer_reviewer(paper_md, figures, max_rounds=MAX_ROUNDS):
    banner("方案 A：提议者-审核者（双 Agent 分工）")
    proposer_meter = TokenMeter("Proposer(纯文本)")
    reviewer_meter = TokenMeter("Reviewer(每轮只看最新截图)")

    proposer = Proposer(proposer_meter, paper_md, figures)
    reviewer = Reviewer(reviewer_meter)

    history = []  # 每轮的 (score, review)
    slides = proposer.propose()
    final_pngs = None

    for rnd in range(1, max_rounds + 1):
        print(f"\n[双 Agent] 第 {rnd} 轮：Proposer 产出 slides.md（{slides.count(chr(10) + '---' + chr(10)) + 1} 段分隔）")
        md_path = save_text(f"dual_round{rnd}_slides.md", slides)
        pngs = render_slides(slides, f"dual_round{rnd}")
        final_pngs = pngs
        print(f"  渲染出 {len(pngs)} 页 PNG，例如：{pngs[0]}")

        review = reviewer.review(pngs)
        print(f"  Reviewer(Vision)审查：{summarize_review(review)}")
        # 打印真实的建议 JSON（前几条）
        print("  Reviewer 结构化建议 JSON：")
        print(_indent(json.dumps(review, ensure_ascii=False, indent=2), 4))
        save_text(f"dual_round{rnd}_review.json",
                  json.dumps(review, ensure_ascii=False, indent=2))
        history.append((review.get("overall_score", 0), review))

        blocking = [i for i in review.get("issues", [])
                    if i.get("severity") in ("high", "medium")]
        if review.get("pass") and not blocking:
            print("  ✓ Reviewer 判定达标（无 high/medium 问题），提前结束迭代。")
            break
        if rnd == max_rounds:
            break

        print("  → Proposer 接收结构化文字反馈并修订（上下文只增文本，不含图片）")
        slides = proposer.revise(review)

    return {
        "slides": slides,
        "final_pngs": final_pngs,
        "history": history,
        "proposer_meter": proposer_meter,
        "reviewer_meter": reviewer_meter,
    }


# --------------------------------------------------------------------------- #
# 方案 B：单 Agent 自审
# --------------------------------------------------------------------------- #
def run_single_agent(paper_md, figures, max_rounds=MAX_ROUNDS):
    banner("方案 B：单 Agent 自我审查（图片累积在同一上下文）")
    meter = TokenMeter("SingleAgent(自审, 图片累积)")
    agent = SelfReviewAgent(meter, paper_md, figures)

    slides = agent.propose()
    final_pngs = None

    for rnd in range(1, max_rounds + 1):
        print(f"\n[单 Agent] 第 {rnd} 轮：生成/修订 slides.md")
        save_text(f"single_round{rnd}_slides.md", slides)
        pngs = render_slides(slides, f"single_round{rnd}")
        final_pngs = pngs
        print(f"  渲染出 {len(pngs)} 页 PNG")
        print(f"  当前上下文峰值 prompt token = {meter.peak_prompt_tokens}")

        if rnd == max_rounds:
            break
        print("  → 把 %d 张截图塞回同一上下文，Agent 自审并修订（历史图片不清除）" % len(pngs))
        slides = agent.self_review_and_revise(pngs)

    return {"slides": slides, "final_pngs": final_pngs, "meter": meter}


def _indent(text, n):
    pad = " " * n
    return "\n".join(pad + line for line in text.splitlines())


def smoke_test():
    """快速冒烟：只验证 Slidev 渲染链路是否可用，不调用任何 LLM，无需 API Key。"""
    from renderer import render_slides
    banner("Smoke test：仅验证 Slidev 渲染链路（不调用 LLM）")
    demo_md = (
        "---\ntheme: default\n---\n\n"
        "# Smoke Test\n\n渲染链路自检\n\n---\n\n"
        "# 第二页\n\n- Slidev + playwright-chromium 正常\n"
    )
    pngs = render_slides(demo_md, "smoke")
    print(f"✓ 渲染成功，产出 {len(pngs)} 页 PNG：")
    for p in pngs:
        print("  ", p)
    print("Slidev 渲染链路可用。")


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="demo.py",
        description="实验 5-4：论文 → PPT 自动生成（提议者-审核者 vs 单 Agent 自审对照）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python demo.py                          # 完整对比：两种方案 + 独立评委 + token 对比\n"
            "  python demo.py --mode dual              # 只跑双 Agent（省一半时间/费用）\n"
            "  python demo.py --max-rounds 1           # 每种方案只出首版（最快的真实 LLM 冒烟）\n"
            "  python demo.py --smoke                  # 仅验证 Slidev 渲染，不调用任何 LLM\n\n"
            "模型/供应商通过环境变量配置（见 env.example）：\n"
            "  OPENAI_API_KEY / OPENAI_BASE_URL / TEXT_MODEL / VISION_MODEL"
        ),
    )
    p.add_argument("--mode", choices=["both", "dual", "single"], default="both",
                   help="运行哪种方案：both=两种都跑并对比（默认）；dual=仅提议者-审核者；"
                        "single=仅单 Agent 自审。只跑一种可显著省时省钱。")
    p.add_argument("--max-rounds", type=int, default=MAX_ROUNDS, metavar="N",
                   help=f"每种方案的最大迭代轮数（默认 {MAX_ROUNDS}）。设为 1 即只出首版、"
                        "不修订，是最快的真实运行冒烟。")
    p.add_argument("--smoke", action="store_true",
                   help="仅验证 Slidev 渲染链路（渲染一个两页 deck），不调用任何 LLM，无需 API Key。")
    return p.parse_args(argv)


def _save_partial_summary(dual, dual_final, single, single_final):
    """单方案运行（--mode dual/single）时，落盘该方案自身的质量与 token 结果。"""
    summary = {"models": {"text": TEXT_MODEL, "vision": VISION_MODEL}}
    if dual:
        pm, rm = dual["proposer_meter"], dual["reviewer_meter"]
        summary["dual_agent"] = {
            "iteration_scores": [h[0] for h in dual["history"]],
            "final_quality": dual_final,
            "total_tokens": pm.total_tokens + rm.total_tokens,
            "peak_context_prompt_tokens": max(pm.peak_prompt_tokens, rm.peak_prompt_tokens),
        }
    if single:
        sm = single["meter"]
        summary["single_agent"] = {
            "final_quality": single_final,
            "total_tokens": sm.total_tokens,
            "peak_context_prompt_tokens": sm.peak_prompt_tokens,
        }
    p = save_text("comparison_summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n结果已保存：{p}")
    print(f"所有 slides.md / review.json / 渲染 PNG 位于：{OUT_DIR}/ 与 slidev_workspace/exports/")


def main(argv=None):
    args = parse_args(argv)

    if args.smoke:
        smoke_test()
        return
    if args.max_rounds < 1:
        print("--max-rounds 至少为 1")
        sys.exit(1)
    if not os.environ.get("OPENAI_API_KEY"):
        print("请先设置 OPENAI_API_KEY（可参考 env.example）")
        sys.exit(1)

    banner("准备：论文 + 程序化复现的图表")
    with open(PAPER_PATH, encoding="utf-8") as f:
        paper_md = f.read()
    figures = generate_all()
    print(f"论文：{PAPER_PATH}（{len(paper_md)} 字符）")
    print(f"文本模型：{TEXT_MODEL}   视觉模型：{VISION_MODEL}")
    print(f"运行模式：{args.mode}   最大轮数：{args.max_rounds}")
    print("已生成图表：")
    for k, v in figures.items():
        print(f"  {k} -> {v}")

    # 方案 A / 方案 B（--mode 控制跑哪一种；只有 both 才能做跨方案对比）
    dual = run_proposer_reviewer(paper_md, figures, args.max_rounds) \
        if args.mode in ("both", "dual") else None
    single = run_single_agent(paper_md, figures, args.max_rounds) \
        if args.mode in ("both", "single") else None

    # ------- 用同一位独立评委给两种方案的最终 PPT 打分（质量对比，尽量公平） -------
    banner("独立评委：对最终 PPT 打分（同一 Vision rubric）")
    judge_meter = TokenMeter("独立评委(不计入两方案成本)")
    dual_final = independent_judge(dual["final_pngs"], judge_meter) if dual else None
    single_final = independent_judge(single["final_pngs"], judge_meter) if single else None
    if dual_final:
        print(f"方案 A（双 Agent）最终质量：{summarize_review(dual_final)}")
    if single_final:
        print(f"方案 B（单 Agent）最终质量：{summarize_review(single_final)}")

    if not (dual and single):
        # 单方案运行：跳过跨方案的 token 对比，仅落盘已有结果
        _save_partial_summary(dual, dual_final, single, single_final)
        return

    # ------- 迭代改善情况（双 Agent） -------
    banner("迭代质量改善（方案 A：提议者-审核者）")
    scores = [h[0] for h in dual["history"]]
    if len(scores) >= 2:
        print(f"Reviewer 打分随迭代变化：{scores}  "
              f"（{'↑ 改善' if scores[-1] >= scores[0] else '↓'} {scores[-1] - scores[0]:+d}）")
    else:
        print(f"仅 1 轮即达标，Reviewer 打分：{scores}")

    # ------- 上下文 token 消耗对比 -------
    banner("上下文 Token 消耗对比：单 Agent 自审 vs 提议者-审核者")
    pm, rm, sm = dual["proposer_meter"], dual["reviewer_meter"], single["meter"]
    dual_total = pm.total_tokens + rm.total_tokens
    dual_peak = max(pm.peak_prompt_tokens, rm.peak_prompt_tokens)

    def row(label, calls, prompt, completion, total, peak):
        print(f"  {label:<34} calls={calls:<3} prompt={prompt:<8} "
              f"completion={completion:<7} total={total:<8} peak_ctx={peak}")

    print("双 Agent（方案 A）拆分：")
    row(pm.name, pm.calls, pm.prompt_tokens, pm.completion_tokens, pm.total_tokens, pm.peak_prompt_tokens)
    row(rm.name, rm.calls, rm.prompt_tokens, rm.completion_tokens, rm.total_tokens, rm.peak_prompt_tokens)
    print("-" * 74)
    row("【方案 A 合计】", pm.calls + rm.calls, pm.prompt_tokens + rm.prompt_tokens,
        pm.completion_tokens + rm.completion_tokens, dual_total, dual_peak)
    row("【方案 B 单Agent自审】", sm.calls, sm.prompt_tokens, sm.completion_tokens,
        sm.total_tokens, sm.peak_prompt_tokens)
    print("-" * 74)
    print(f"每次调用的 prompt token 序列：")
    print(f"  方案A Proposer : {pm.per_call_prompt}")
    print(f"  方案A Reviewer : {rm.per_call_prompt}   ← 每轮独立、只看最新截图，不随迭代累积")
    print(f"  方案B 单Agent  : {sm.per_call_prompt}   ← 图片累积在同一上下文，峰值随迭代上升")
    print()
    print(f"关键结论：")
    print(f"  · 上下文峰值（单次 prompt token，决定是否撑爆上下文窗口）：")
    print(f"      方案 A = {dual_peak}   方案 B = {sm.peak_prompt_tokens}   "
          f"（B/A = {sm.peak_prompt_tokens / max(dual_peak,1):.2f}x）")
    print(f"  · Proposer 全程不看图片，其峰值仅 {pm.peak_prompt_tokens} token（纯文本反馈）。")
    print(f"  · 方案 B 因图片在同一上下文累积，峰值最高；页数越多、迭代越多，差距越大。")

    # 汇总落盘
    summary = {
        "models": {"text": TEXT_MODEL, "vision": VISION_MODEL},
        "dual_agent": {
            "iteration_scores": scores,
            "final_quality": dual_final,
            "proposer_tokens": pm.__dict__,
            "reviewer_tokens": rm.__dict__,
            "total_tokens": dual_total,
            "peak_context_prompt_tokens": dual_peak,
        },
        "single_agent": {
            "final_quality": single_final,
            "tokens": sm.__dict__,
            "total_tokens": sm.total_tokens,
            "peak_context_prompt_tokens": sm.peak_prompt_tokens,
        },
    }
    p = save_text("comparison_summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n完整对比已保存：{p}")
    print(f"所有 slides.md / review.json / 渲染 PNG 位于：{OUT_DIR}/ 与 slidev_workspace/exports/")


if __name__ == "__main__":
    main()
