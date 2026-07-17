"""
实验 8-4 演示：主动工具发现 vs 全量注入

对同一组跨领域任务，分别用两种模式运行 gpt-4o-mini：
- 全量注入：126 个工具 schema 一次性进上下文
- 主动发现：少量基础工具 + discover_tools 元工具，按需嵌入检索加载

对每个任务打印：注入 token 数、实际调用的工具、是否选对（判分）、是否误用通用工具。
最后打印汇总对比。

用法：
    python demo.py            # 跑全部任务
    python demo.py --tasks finance+news,crypto+news
"""

import argparse
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

from agent import run_active_discovery, run_full_injection
from discovery import ToolIndex
from tools_library import TASKS, grade

load_dotenv()

MODEL = os.getenv("MODEL", "gpt-4o-mini")


def _fmt_grade(g):
    tag = "✅ 精确选对" if g["precise"] else ("⚠️ 完成但错选" if g["correct"] else "❌ 出错")
    detail = f"{g['filled_slots']}/{g['total_slots']} 能力槽位命中"
    extra = ""
    if g["missed_slots"]:
        extra += f"｜漏用: {[s[0] for s in g['missed_slots']]}"
    if g["used_generic_substitute"]:
        extra += f"｜错选通用工具: {g['used_generic_substitute']}"
    return f"{tag}（{detail}{extra}）"


def main():
    ap = argparse.ArgumentParser(
        description="实验 8-4：主动工具发现 vs 全量注入 的对比演示。"
                    "对每个任务分别用两种模式运行，打印注入 token / 调用轨迹 / 选择精度对比。",
        epilog="示例：python demo.py --tasks finance+news,crypto+news")
    ap.add_argument("--tasks",
                    help="逗号分隔的任务 id（见 tools_library.py 的 TASKS），缺省跑全部 8 个任务。")
    args = ap.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        print("请先设置 OPENAI_API_KEY（见 env.example）")
        sys.exit(1)

    tasks = TASKS
    if args.tasks:
        want = set(args.tasks.split(","))
        tasks = [t for t in TASKS if t["id"] in want]

    client = OpenAI()
    print(f"模型: {MODEL}  |  嵌入: text-embedding-3-small  |  任务数: {len(tasks)}\n")
    index = ToolIndex(client)

    summary = []
    for task in tasks:
        print("=" * 88)
        print(f"任务 [{task['id']}]: {task['prompt']}")
        print("-" * 88)

        # ---- 全量注入 ----
        full = run_full_injection(client, MODEL, task["prompt"])
        gf = grade(task, full["called"])
        print(f"[全量注入] 注入工具 schema: {full['injected_tokens']:>6} tokens "
              f"（{full['num_tools_exposed']} 个工具全部进上下文）")
        print(f"           调用轨迹: {full['called']}")
        print(f"           判定: {_fmt_grade(gf)}")

        # ---- 主动发现 ----
        act = run_active_discovery(client, MODEL, task["prompt"], index)
        ga = grade(task, act["called"])
        print(f"[主动发现] 注入工具 schema: {act['injected_tokens']:>6} tokens "
              f"（基础工具+discover_tools+按需发现 {len(act['discovered'])} 个专用工具）")
        for line in act["trace"]:
            if line.startswith("[discover_tools]"):
                print(f"           {line}")
        print(f"           发现并加载: {act['discovered']}")
        print(f"           调用轨迹: {act['called']}")
        print(f"           判定: {_fmt_grade(ga)}")

        saved = full["injected_tokens"] - act["injected_tokens"]
        ratio = full["injected_tokens"] / max(act["injected_tokens"], 1)
        print(f"[对比] 注入 token 节省: {saved} （{ratio:.1f}× 精简）  "
              f"| 全量注入调用 {len(full['called'])} 个工具, 主动发现调用 {len(act['called'])} 个")
        print()

        summary.append((task["id"], full["injected_tokens"], act["injected_tokens"],
                        gf["precise"], ga["precise"]))

    # ---- 汇总 ----
    print("=" * 88)
    print("汇总（『精确选对』= 覆盖全部能力槽位 且 未错选通用兜底工具）")
    print("=" * 88)
    print(f"{'任务':<18}{'全量注入token':>14}{'主动发现token':>14}{'全量精确?':>11}{'发现精确?':>11}")
    tf = ta = cf = ca = 0
    for tid, ft, at, fc, ac in summary:
        tf += ft; ta += at; cf += int(fc); ca += int(ac)
        print(f"{tid:<18}{ft:>14}{at:>14}{('✅' if fc else '❌'):>10}{('✅' if ac else '❌'):>10}")
    print("-" * 88)
    n = len(summary)
    print(f"{'合计/精确率':<16}{tf:>14}{ta:>14}{f'{cf}/{n}':>11}{f'{ca}/{n}':>11}")
    if ta:
        print(f"\n注入 token 总量：全量注入 {tf} vs 主动发现 {ta}，"
              f"平均每任务精简约 {tf/ta:.1f} 倍。")
    print(f"精确选对率：全量注入 {cf}/{n} vs 主动发现 {ca}/{n}"
          f"（差异主要来自『诱导任务』上全量注入错选了通用 web_search）。")


if __name__ == "__main__":
    main()
