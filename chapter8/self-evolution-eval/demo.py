"""
实验 8-6 一键演示：python demo.py

流程：
1) 打印数据集概览与几条"不暗示工具名"的任务示例。
2) 用 strong 参考 Agent 在 2-3 个任务上跑完四层验证（含真实 LLM-as-a-Judge 打分）。
3) 用 weak 参考 Agent 做对照，展示四层的区分度。
4) 复用层对照：strong 第二次相似任务直接检索已注册工具；weak 则重复搜索创建。

用法：
    python demo.py            # 默认：strong 跑 3 个任务 + weak 对照 1 个任务
    python demo.py --quick    # 快速演示：strong / weak 各只跑 1 个任务，省时省钱
    python demo.py --tasks task-01,task-07   # 指定要评估的任务 id（逗号分隔）
"""

import argparse
import json
import os
import sys

from agent import STRONG, WEAK, SelfEvolutionAgent, ToolRegistry
from config import Config
from harness import FourLayerEvaluator

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO_TASK_IDS = ["task-01", "task-17", "task-07"]  # 多媒体 / 地理空间 / 天气


def load_dataset():
    with open(os.path.join(HERE, "dataset.json"), encoding="utf-8") as f:
        return json.load(f)


def fmt(x):
    return "N/A" if x is None else f"{x:.3f}"


def print_dataset_overview(ds):
    tasks = ds["tasks"]
    print("=" * 78)
    print(f"数据集：{ds['meta']['name']}  共 {len(tasks)} 个任务，覆盖领域：")
    domains = [t["domain"] for t in tasks]
    print("  " + " | ".join(domains))
    print("-" * 78)
    print("任务示例（注意：只说目标，不暗示工具名 / 库名）：")
    for t in tasks[:4]:
        print(f"  [{t['id']}] ({t['domain']}) {t['goal']}")
    print("=" * 78 + "\n")


def print_report(rep):
    L = rep["layers"]
    print(f"■ 任务 {rep['task_id']} ({rep['domain']}) | 画像={rep['profile']}")
    print(f"  L1 任务正确性     : {fmt(L['L1']['score'])}  | {L['L1']['detail']}")
    print(f"  L2 工具发现有效性 : {fmt(L['L2']['score'])}  | {L['L2']['detail']}")
    l3 = L["L3"]
    print(f"  L3 工具创造质量   : {fmt(l3['score'])}  | {l3['detail']}")
    if l3.get("rubric"):
        r = l3["rubric"]
        print(f"       Rubric: 错误处理={r.get('error_handling')} 参数校验={r.get('input_validation')} "
              f"文档={r.get('documentation')} 健壮性={r.get('robustness')}")
        print(f"       LLM-Judge 点评: {r.get('comment', '')}")
    print(f"  L4 工具复用能力   : {fmt(L['L4']['score'])}  | {L['L4']['detail']}")
    print(f"  >> 总评 overall   : {fmt(rep['summary']['overall'])}  (计入层: {rep['summary']['used_layers']})")
    print()


def run_profile(name, profile, tasks, evaluator):
    print("#" * 78)
    print(f"# 用 {name} 参考 Agent 评估（每个任务：先做首次任务，再做相似任务测复用）")
    print("#" * 78 + "\n")
    registry = ToolRegistry()  # 每个画像独立的注册表
    agent = SelfEvolutionAgent(registry=registry, model=Config.AGENT_MODEL)
    for task in tasks:
        first = agent.run(task, profile, use_variant=False)   # 首次：发现+创造+注册（strong 真调 LLM 生成工具）
        variant = agent.run(task, profile, use_variant=True)  # 第二次相似任务：测复用
        rep = evaluator.evaluate(task, first, variant)
        print_report(rep)
        # 展示复用层的轨迹差异证据
        v_actions = [s["action"] for s in variant["steps"]]
        print(f"    [复用探针] 第二次相似任务的动作序列: {v_actions}")
        print()


def parse_args():
    ap = argparse.ArgumentParser(
        description="实验 8-6：为自我进化 Agent 设计评估数据集 · 四层验证演示")
    ap.add_argument("--quick", action="store_true",
                    help="快速演示：strong / weak 各只跑 1 个任务，减少 API 调用与耗时。")
    ap.add_argument("--tasks", metavar="IDS",
                    help="逗号分隔的任务 id（如 task-01,task-07），缺省用内置的示例任务。")
    return ap.parse_args()


def main():
    args = parse_args()
    try:
        Config.get_client()
    except Exception as e:
        print(f"[配置错误] {e}")
        sys.exit(1)

    print(f"PROVIDER={Config.PROVIDER}  AGENT_MODEL={Config.resolve_default_model()}  "
          f"JUDGE_MODEL={Config.JUDGE_MODEL}\n")

    ds = load_dataset()
    print_dataset_overview(ds)

    by_id = {t["id"]: t for t in ds["tasks"]}
    # 任务选择：--tasks 指定 > --quick 取 1 个 > 默认 3 个示例任务
    if args.tasks:
        want = [i.strip() for i in args.tasks.split(",") if i.strip()]
        missing = [i for i in want if i not in by_id]
        if missing:
            print(f"[错误] 数据集中不存在这些任务 id：{missing}")
            sys.exit(1)
        task_ids = want
    elif args.quick:
        task_ids = DEMO_TASK_IDS[:1]
    else:
        task_ids = DEMO_TASK_IDS
    tasks = [by_id[i] for i in task_ids]
    evaluator = FourLayerEvaluator(judge_model=Config.JUDGE_MODEL)

    # strong：好发现 + LLM 生成的高质量工具 + 复用
    run_profile("STRONG(强)", STRONG, tasks, evaluator)

    # weak 对照：坏发现 + 粗糙 stub + 从不复用（只跑第一个任务，凸显区分度）
    run_profile("WEAK(弱)", WEAK, tasks[:1], evaluator)

    print("=" * 78)
    print("结论：四层验证对'强/弱'两种被测 Agent 给出了不同分数；")
    print("其中 L2 依据搜索关键词/选库判定发现有效性，L3 由 LLM-as-a-Judge 按 Rubric 对")
    print("工具代码打分，L4 通过第二次相似任务的动作序列区分'复用'与'重复搜索'。")
    print("=" * 78)


if __name__ == "__main__":
    main()
