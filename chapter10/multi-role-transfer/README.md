# 实验 10-2：多角色转换 / `transfer_to_agent`（★★）

《深入理解 AI Agent》配套代码。演示**共享上下文下的链式移交（handoff）**：
一个会话里存在多个专业角色 Agent（各有独立系统提示词与专属工具集），
通过一个 `transfer_to_agent(target_role, reason)` 工具在角色间**自主移交**控制权。

## 这个实验想说明什么

- 与 10-1（软件开发单任务的**预定义阶段流水线**）不同，10-2 强调**跨领域**、
  由 Agent **自主判断**该切换到哪个专业角色——不是预先规划好的线性流程，
  而是根据任务进展动态切换。
- 因为**共享同一段对话历史**，移交时完整历史天然保留，
  新角色自动继承此前所有内容（无需显式传参）。
- 机制重点是「自主角色移交」，而非工具本身多强，因此工具用轻量真实实现 / 可控 mock。

## 架构

```
                        共享对话历史 history（user/assistant/tool 消息，全程保留）
                                        ▲   ▲
   每轮调用大模型时：                     │   │
   [ 当前角色的 system prompt ] + history ┘   └ 只暴露 [ 当前角色工具集 + transfer_to_agent ]

   模型两种动作：
     ① 调用自己的专属工具（普通 function calling）
     ② 调用 transfer_to_agent(target_role, reason)
        → 编排器换掉「系统提示词 + 工具集」，history 原样不动
        → 新角色继承全部历史（共享上下文）
```

5 个角色（`roles.py`）：

| 角色 | 说明 | 专属工具集 |
|------|------|-----------|
| `triage` | 前台分诊 / 默认入口，拆解需求并按序移交、最后收尾 | 仅 `transfer_to_agent` |
| `research` | 信息检索 | `web_search`（内置知识库 mock） |
| `coding` | 编程 | `execute_python`（真实执行并捕获输出） |
| `data_analysis` | 数据分析 / 计算 | `calculate`、`descriptive_stats` |
| `writing` | 润色写作 | `count_characters` |

每个角色都额外持有 `transfer_to_agent`，可自主把控制权交给同事。

代码结构：

- `tools.py` —— 各角色专属工具的实现 + OpenAI function-calling schema
- `roles.py` —— 5 个角色定义（系统提示词 + 工具集）+ `transfer_to_agent` schema
- `orchestrator.py` —— 移交编排器（共享历史 + 换系统提示词/工具集的主循环，含防死循环/拒绝自我移交）
- `demo.py` —— 一条命令的演示入口

## 运行方式

```bash
pip install -r requirements.txt

# 配置 key（二选一）
export OPENAI_API_KEY=sk-...        # 直接 export
# 或： cp env.example .env 后填写

python demo.py
```

可配环境变量（均有默认值）：
`OPENAI_API_KEY`（必填）、`OPENAI_BASE_URL`（默认 `https://api.openai.com/v1`）、
`OPENAI_MODEL`（默认 `gpt-4o-mini`）。

也可用命令行参数临时覆盖（不传则行为与上面完全一致）：
`python demo.py --task "..."`（自定义任务）、`--model gpt-4o`（临时换模型）；
运行 `python demo.py --help` 查看说明。

## 演示说明

`demo.py` 抛出一个需要**多次跨领域切换**的复合任务：

> 查中国 2021—2023 三年新能源汽车销量 → 算出年均复合增长率(CAGR) → 写成一段面向投资人的中文总结

预期看到 Agent 自主完成移交链：

```
triage → research → data_analysis → writing
```

- `triage` 判断第一步要查数据，移交 `research`；
- `research` 用 `web_search` 查到三年销量，移交 `data_analysis`；
- `data_analysis` 用 `calculate` 算出 CAGR ≈ 64.22%，移交 `writing`；
- `writing` 综合**此前历史里**的销量数据与 CAGR，直接写出最终成稿。

`writing` 从未自己检索或计算，却能引用准确的销量数字和增长率——
这正是**共享上下文**的证据。运行结束会打印完整移交链、每次移交的 `from→to` 与 `reason`。

> 注：真实 LLM 输出有随机性，某次运行的具体措辞/步数可能略有不同，但移交机制一致。

### 预期输出示例（真实运行截取）

以下是一次 `python demo.py`（`model=gpt-4o-mini`）真实运行的关键片段，未做任何编造或修饰：

```
=== 角色花名册（共 5 个专业角色）===
• triage — 前台分诊（默认入口）
    工具集: ['transfer_to_agent']
    系统提示词(首句): 你是通用助理系统的『前台分诊』角色，也是默认入口。
• research — 信息检索专家
    工具集: ['web_search', 'transfer_to_agent']
    ...（其余角色略，完整列表见上方角色表）

================ 运行汇总 ================
自主移交链: triage → research → data_analysis → writing
移交次数: 3
  1. triage → research  |  reason: 需要查找中国2021、2022、2023三年的新能源汽车销量数据。
  2. research → data_analysis  |  reason: 需要计算2021、2022、2023年新能源汽车销量的年均复合增长率(CAGR)。
  3. data_analysis → writing  |  reason: 需要将新能源汽车销量数据和CAGR的结论写成一段面向投资人的总结。

最终成果:
根据数据显示，中国新能源汽车销量在2021年为352.1万辆，2022年达到688.7万辆，2023年预计为949.5万辆。由此计算得出，2021至2023年间的年均复合增长率（CAGR）为约64.22%。这一强劲的增长趋势表明，新能源汽车市场正处于快速发展阶段，未来潜力巨大，值得投资者关注。
```

## 局限

- 默认模型为 `gpt-4o-mini`；移交是否按预期链路发生，很大程度依赖所选模型的指令遵循能力，换模型效果可能不同。
- `research` 角色的 `web_search` 是**内置知识库 mock**，并非真实联网检索，仅能命中预置的少量关键词（新能源汽车销量、光伏装机、Python GIL），换查询词可能查不到。
- 真实 LLM 输出存在随机性：具体移交步数、每次 `reason` 的措辞、是否途经 `coding` 角色等，不同次运行可能不同，但移交机制本身一致。
- `orchestrator.py` 设有 `max_steps`（默认 20）硬上限，以及「同一 (角色, 工具, 参数) 连续调用 ≥3 次」的纠偏提示，用于防止模型死循环；这是兜底保护，不代表每次运行都会用满这些步数。
