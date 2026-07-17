# 实验 10-1：根据执行阶段决定系统提示词（Staged System Prompt）

《深入理解 AI Agent》配套实验代码。

## 实验目的

同一个 Coding Agent，在任务的不同**执行阶段**加载**不同的系统提示词 + 不同的工具集**，
从而在同一段对话里扮演不同角色、表现出不同的行为模式；同时让**对话历史与任务状态在阶段间连续共享**。

本实验用一个「Coding Agent」串起三个阶段：

| 阶段 | 角色 | 系统提示词强调 | 配套工具集 | 触发进入下一阶段的工具 |
| --- | --- | --- | --- | --- |
| 1 需求澄清 | 需求分析师 | 只提问确认、**不写代码** | `ask_clarifying_question` / `save_requirement` / `complete_requirements_analysis` | `complete_requirements_analysis` → 阶段2 |
| 2 代码实现 | 软件工程师 | 按已确认需求写高质量 Python | `write_file` / `read_file` / `execute_code` / `submit_for_review` | `submit_for_review` → 阶段3 |
| 3 代码审查 | 代码审查员 | 批判性把关质量 | `run_linter` / `run_tests` / `analyze_complexity` / `request_revision` / `approve_code` | `request_revision` → **回退阶段2**；`approve_code` → 完成 |

## 架构

```
demo.py                入口：一条命令跑通三阶段（任务 = “写一个整理下载文件夹的 Python 脚本”）
agent.py               StagedAgent：阶段状态机 + 工具调用循环 + 跨阶段共享上下文 + 执行日志
tools.py               三套工具的 Schema 与真实实现（虚拟工作区 / 真实执行代码 / linter / 复杂度分析）
simulated_user.py      模拟用户：需求澄清阶段自动回答 Agent 的提问（预设答案），实现无人值守
config.py              从环境变量读取 API Key / base_url / model
```

关键设计：

- **共享上下文**：`StagedAgent.history` 是一条贯穿始终的消息列表，切换阶段时**只替换 system 提示词、只切换传给模型的 tools**，历史消息（需求、代码、审查意见）全部保留。每次请求都是 `[system(当前阶段)] + history`。
- **阶段转换由工具调用触发**：主循环识别到 `complete_requirements_analysis` / `submit_for_review` / `request_revision` / `approve_code` 这些「信号工具」被调用时，注入一条跨阶段「交接」消息并切换阶段。
- **回退机制**：审查阶段发现问题时调用 `request_revision(issues)`，把问题清单退回实现阶段；设有 `max_revisions` 安全阀，避免无限循环烧 token。
- **真实执行**：`execute_code` / `run_tests` 会把代码写入临时目录并用子进程真实运行；`run_linter` / `analyze_complexity` 基于 `ast` 做真实静态分析，不是假返回。

## 如何运行

```bash
pip install -r requirements.txt

# 配置（二选一）
export OPENAI_API_KEY=sk-...           # 方式 A：直接 export
cp env.example .env && vi .env         # 方式 B：写到 .env

python demo.py

# 查看可选参数（不影响默认行为）
python demo.py --help
```

可选命令行参数（默认值与不加参数完全一致）：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--task` | 整理下载文件夹的任务 | 覆盖交给 Agent 的用户任务 |
| `--max-revisions` | `3` | 审查阶段允许的最大回退次数，超过则强制结束演示 |
| `--model` | 环境变量 `OPENAI_MODEL` | 覆盖使用的模型名 |

可配环境变量（见 `env.example`）：`OPENAI_API_KEY`（必填）、`OPENAI_BASE_URL`（默认官方）、
`OPENAI_MODEL`（默认 `gpt-4o-mini`，便宜省钱）、`OPENAI_TEMPERATURE`（默认 0.3）。
也可切到兼容 OpenAI 协议的 Kimi / Doubao。

## 演示说明了什么问题

一次真实运行（`gpt-4o-mini`）会看到：

1. **需求澄清阶段**：Agent 表现为「不断提问」——主动追问处理哪些文件类型、是否递归、是否保留原名、移动还是复制、目标目录怎么定，并逐条 `save_requirement`。它**完全不写代码**。
2. **代码实现阶段**：同一个 Agent 换了提示词后表现为「写代码」——`write_file` 产出 Python 脚本，`execute_code` 自测，然后 `submit_for_review`。
3. **代码审查阶段**：Agent 表现为「批判审查」——依次跑 `run_linter` / `run_tests` / `analyze_complexity`，发现真实问题（如缺少模块 docstring、冒烟测试 `FileNotFoundError`）后 `request_revision` **退回实现阶段**。
4. 实现阶段据问题清单**重写并修复**，再次提交；审查通过后 `approve_code`，任务完成。

也就是说：**提示词 + 工具集随阶段切换，行为模式随之明显不同**，而任务状态（需求、代码、审查意见）在阶段间始终连续共享。运行结束时会打印每个角色的「行为分布」统计，直观对比三个阶段的行为差异。

## 预期输出示例

以下是一次真实运行（`python demo.py`，`gpt-4o-mini`）的节选，完整展示三阶段的行为切换
（本次运行触发了 4 次审查回退，最终撞到 `max_revisions` 安全阀结束，也是真实运行中常见的一种结局，
详见下方「局限」）：

```
模型：gpt-4o-mini  | base_url：https://api.openai.com/v1

======================================================================
进入阶段：requirements  |  角色：需求分析师  |  可用工具：['ask_clarifying_question', 'save_requirement', 'complete_requirements_analysis']
======================================================================
[需求分析师] 提问: 您希望整理下载文件夹中的哪些文件类型？例如，您是想整理所有文件，还是仅限于某些特定类型（如图片、文档等）？
[需求分析师] 模拟用户回答: 按文件类型分类：图片(jpg/png/gif)、文档(pdf/doc/txt)、音频(mp3/wav)、视频(mp4/mov)、压缩包(zip/rar)，其余归到 Others。
[需求分析师] 记录需求: file_types = 图片(jpg/png/gif)、文档(pdf/doc/txt)、音频(mp3/wav)、视频(mp4/mov)、压缩包(zip/rar)，其余归到 Others
...（继续澄清是否递归、是否保留原名、移动还是复制、目标目录如何指定）
[需求分析师] 完成需求分析 -> 转交实现: 整理下载文件夹中的文件，按类型分类到子文件夹，保留原文件名，移动文件，不递归子目录。

======================================================================
进入阶段：implementation  |  角色：软件工程师  |  可用工具：['write_file', 'read_file', 'execute_code', 'submit_for_review']
======================================================================
[软件工程师] 写文件: 已写入文件 organize_downloads.py（1913 字符，59 行）
[软件工程师] 执行代码自测: import os import shutil import sys  def create_directory(path): ...
[软件工程师] 提交审查 -> 转交审查: organize_downloads.py

======================================================================
进入阶段：review  |  角色：代码审查员  |  可用工具：['run_linter', 'run_tests', 'analyze_complexity', 'request_revision', 'approve_code']
======================================================================
[代码审查员] run_linter: [linter] 发现 4 个问题：
[代码审查员] run_tests: [tests] 冒烟测试结果：PASS
[代码审查员] analyze_complexity: [complexity] 函数数量=3，分支/循环语句=9，最大嵌套深度=5
[代码审查员] 审查不通过 -> 回退实现: 第1次退回：['L7: 行尾有多余空白', 'L13: 行尾有多余空白', ...]

...（实现阶段修复问题后重新提交，审查阶段再次检查，如此循环，直到 approve_code 或达到 max_revisions）

======================================================================
执行小结
======================================================================
[需求分析师] 行为分布：思考/发言×1, 提问×5, 模拟用户回答×5, 记录需求×5, 完成需求分析 -> 转交实现×1
[软件工程师] 行为分布：写文件×4, 执行代码自测×1, 提交审查 -> 转交审查×4
[代码审查员] 行为分布：run_linter×4, run_tests×4, analyze_complexity×4, 审查不通过 -> 回退实现×4, 回退次数达上限×1

已确认需求条数：5
产出文件：['organize_downloads.py']
审查回退次数：4
```

三段「行为分布」清楚对照出同一个 Agent 在三种提示词下的不同行为模式：需求分析师只问不写，
软件工程师只写不审，代码审查员只查不写。

## 局限

- **依赖 gpt-4o-mini 的能力**：默认用便宜模型控制演示成本，其指令遵循与代码质量弱于更强模型，
  换成更强模型（如 `gpt-4o` / `gpt-5`）通常能更快收敛、更少回退。
- **单一固定任务**：内置演示任务是「整理下载文件夹」，虽然新增了 `--task` 参数可覆盖，
  但 `simulated_user.py` 的预设问答是围绕这个任务场景设计的，换成差异很大的任务时模拟用户可能答不上点子上。
- **模拟用户是预设答案**：`SimulatedUser` 按关键词匹配预设回答，不是真正理解语义的用户，
  遇到 Agent 提出预设脚本之外的问题时会退化为兜底回答或催促进入下一阶段。
- **真实 LLM 有随机性**：即使 `temperature=0.3`，不同次运行的提问顺序、代码实现细节、
  审查是否通过、回退次数都可能不同；也可能像上面这次示例一样撞到 `max_revisions` 安全阀
  强制结束，而不是拿到 `approve_code`。
