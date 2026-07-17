"""
实验 10-1 演示入口：一条命令跑通“需求澄清 -> 代码实现 -> 代码审查”三阶段。

    python demo.py                 # 默认任务、默认模型、最多 3 次审查回退
    python demo.py --help          # 查看全部可选参数

演示任务：用户想要“写一个整理下载文件夹的 Python 脚本”。
需求本身模糊，因此需求澄清阶段的 Agent 会主动提问，由模拟用户自动回答；
之后进入实现阶段写代码、审查阶段严格把关（可能回退重写）。
"""

import argparse

from agent import StagedAgent
from config import Config


USER_TASK = "帮我写一个整理下载文件夹的 Python 脚本。"
DEFAULT_MAX_REVISIONS = 3


def parse_args() -> argparse.Namespace:
    """解析命令行参数。不传任何参数时，行为与原始固定脚本完全一致。"""
    parser = argparse.ArgumentParser(
        prog="demo.py",
        description=(
            "实验 10-1：阶段化系统提示词（需求澄清 -> 代码实现 -> 代码审查）演示。"
            "不加参数运行即为默认演示。"
        ),
    )
    parser.add_argument(
        "--task",
        default=USER_TASK,
        help=f"交给 Agent 的用户任务（默认：{USER_TASK!r}）",
    )
    parser.add_argument(
        "--max-revisions",
        type=int,
        default=DEFAULT_MAX_REVISIONS,
        help=f"审查阶段允许的最大回退次数，超过则强制结束演示（默认：{DEFAULT_MAX_REVISIONS}）",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"覆盖 OPENAI_MODEL 环境变量指定的模型名（默认：使用环境变量，当前为 {Config.MODEL!r}）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.model:
        Config.MODEL = args.model

    print("模型：%s  | base_url：%s" % (Config.MODEL, Config.BASE_URL))
    agent = StagedAgent(max_revisions=args.max_revisions, verbose=True)
    agent.run(args.task)
    agent.print_summary()

    # 打印最终产出的主文件，方便肉眼确认实现阶段真的写了代码
    if agent.workspace.files:
        print("\n" + "=" * 70)
        print("最终产出文件内容：")
        print("=" * 70)
        for path, content in agent.workspace.files.items():
            print(f"\n--- {path} ---\n{content}")


if __name__ == "__main__":
    main()
