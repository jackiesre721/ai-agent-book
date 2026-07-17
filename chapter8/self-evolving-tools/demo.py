"""
实验 8-5 一键演示：`python demo.py`

演示两件事：
  1) 进化：Agent 从零基础工具出发 —— 搜索 → 读文档 → 沙箱测试 → 封装工具 →
     用新工具给出 NVIDIA(NVDA) 的真实股价与「相对一周前」的真实涨跌幅。
  2) 复用：换一支股票(AAPL) 再问一次。Agent 应先 search_tools 命中已创建的工具并直接复用，
     不再重新上网搜索、重新造轮子。程序会打印轨迹并自动校验「复用」是否成立。

注意：真实联网 + 真实调用 OpenAI，请先在环境中配置 OPENAI_API_KEY。

用法：
    python demo.py           # 跑「进化 + 复用」两个任务
    python demo.py --fresh   # 先清空 tool_library/ 再跑（重现「从零进化」，重复演示时推荐）
    python demo.py --help    # 查看全部参数

提示：工具库会持久化到 tool_library/。若上一轮已封装出 get_stock_price，再次直接运行时
任务一会在第 0 步就命中并复用它，从而看不到「进化」过程；想重现进化请加 --fresh。
"""

import argparse
import glob
import os
import sys

from agent import SelfEvolvingAgent
from tool_manager import LIBRARY_DIR


TASK_1 = "查询 NVIDIA(股票代码 NVDA) 的最新股价，以及与一周前相比的涨跌幅（百分比）。请给出真实数据。"
TASK_2 = "查询 Apple(股票代码 AAPL) 的最新股价，以及与一周前相比的涨跌幅（百分比）。请给出真实数据。"


def _clear_library():
    """清空持久化的工具库（仅删除生成的 *.json 工件），用于重现「从零进化」。"""
    removed = 0
    for p in glob.glob(os.path.join(str(LIBRARY_DIR), "*.json")):
        try:
            os.remove(p)
            removed += 1
        except OSError:
            pass
    print(f"[--fresh] 已清空 tool_library/（删除 {removed} 个已封装工具），将从零开始进化。\n")


def main():
    parser = argparse.ArgumentParser(
        description="实验 8-5：Agent 从网络寻找工具、自我进化的一键演示。")
    parser.add_argument(
        "--fresh", action="store_true",
        help="运行前清空 tool_library/，以重现任务一的「从零进化」过程（重复演示时推荐）。")
    args = parser.parse_args()

    if args.fresh:
        _clear_library()

    try:
        agent = SelfEvolvingAgent(verbose=True)
    except RuntimeError as e:
        print(f"[配置错误] {e}", file=sys.stderr)
        print(
            "请先配置对应供应商的 API Key（默认 OpenAI）：\n"
            "  cp env.example .env  然后在 .env 中填入 OPENAI_API_KEY；\n"
            "  或直接 export OPENAI_API_KEY=sk-...\n"
            "如需切换供应商：export LLM_PROVIDER=moonshot|ark 并配置对应的 "
            "MOONSHOT_API_KEY / ARK_API_KEY。",
            file=sys.stderr,
        )
        return 2

    # ---------- 任务一：从零进化 ----------
    print("\n########## 任务一：NVDA（演示 搜索→测试→封装→用）##########")
    agent.trajectory = []
    ans1 = agent.run(TASK_1)
    traj1 = list(agent.trajectory)

    created = [t for t in agent.library.list_tools()]
    print(f"\n>>> 任务一结束。当前工具库已封装工具: {[t['name'] for t in created]}")
    print(f">>> 任务一动作轨迹: {traj1}")

    # ---------- 任务二：复用 ----------
    print("\n########## 任务二：AAPL（演示 工具复用）##########")
    agent.trajectory = []
    ans2 = agent.run(TASK_2)
    traj2 = list(agent.trajectory)
    print(f"\n>>> 任务二动作轨迹: {traj2}")

    # ---------- 复用校验 ----------
    reused = (
        "search_tools" in traj2
        and "web_search" not in traj2
        and "create_tool" not in traj2
        and any(t not in {"web_search", "read_webpage", "code_interpreter",
                          "create_tool", "search_tools"} for t in traj2)
    )
    print("\n" + "=" * 70)
    print("结论汇总")
    print("=" * 70)
    print(f"[任务一 · NVDA] {ans1}")
    print(f"[任务二 · AAPL] {ans2}")
    print("-" * 70)
    print(f"任务二是否复用了已创建工具(未重新搜索/创建): {'是 ✅' if reused else '否 ❌'}")
    print(f"  证据：任务二轨迹调用了 search_tools 且未出现 web_search/create_tool。")
    return 0 if reused else 1


if __name__ == "__main__":
    sys.exit(main())
