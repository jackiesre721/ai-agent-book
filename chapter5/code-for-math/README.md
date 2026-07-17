# 实验 5-1：用代码生成工具提升数学解题能力

《深入理解 AI Agent》配套实验（★★）。验证一个结论：给 Agent 配上能执行代码的
Python 沙箱后，它在竞赛数学题上的准确率会**显著高于**纯思维链（Chain-of-Thought, CoT）。

## 目的

大模型「心算」大数、枚举、因式分解时极易出错——不是不会方法，而是算错。
本实验让同一个模型（默认 `gpt-4o-mini`）在同一组题上跑两种模式，直接对比：

- **纯 CoT**：只能用自然语言一步步推理，禁止写代码；
- **代码辅助**：把题目形式化为 Python（sympy 符号计算、numpy 矩阵、scipy 数值求解），
  通过 function calling 调用 `run_python` 工具在**子进程沙箱**里执行，用精确结果替代心算。

## 原理

```
题目 ──► 模型
          │  纯 CoT：直接自然语言推理 ─────────────► 最终答案（易算错）
          │
          └─ 代码辅助：生成 Python 代码
                       │  function calling
                       ▼
                 run_python 工具（子进程沙箱，预装 sympy/numpy/scipy，超时保护）
                       │  返回 stdout
                       ▼
                 模型基于精确结果继续推理 ──────────► 最终答案（更准）
```

- 工具用 OpenAI **function calling** 暴露：模型自主决定何时写代码、写什么代码。
- 沙箱是 `sandbox.py` 里的 `run_python()`：把代码写入临时文件，用子进程执行，
  带 20 秒超时，崩溃/死循环不影响主进程。预导入了 `sympy / numpy / scipy`。
- 题目在 `problems.json`：11 道 AIME 风格竞赛题，**答案均为整数、已用暴力枚举离线校验**，
  覆盖数论、模运算、丢番图方程、生成函数、素因子分解、格点计数等。

## 运行

```bash
pip install -r requirements.txt
cp env.example .env   # 或直接 export OPENAI_API_KEY=...
export OPENAI_API_KEY=sk-...      # 也支持 MOONSHOT_API_KEY / ARK_API_KEY

python demo.py                    # 跑完整对照实验
python demo.py --verbose          # 额外打印模型生成的代码与执行结果
python demo.py --limit 3          # 只跑前 3 题（省钱调试）
```

可用环境变量：`OPENAI_API_KEY`（或 `MOONSHOT_API_KEY` / `ARK_API_KEY`）、
`OPENAI_BASE_URL`（切换兼容端点）、`MODEL`（默认 `gpt-4o-mini`）。

## 预期输出示例 / 结论

真实跑 `gpt-4o-mini`（11 题，`temperature=0`）的一次逐题结果节选：

```
题号   考点                             真值     CoT预测          代码预测
------------------------------------------------------------------------------
2    modular exponentiation        216       216   ✓       216   ✓
4    perfect squares              1464      1495   ✗      1464   ✓
7    prime factorization           661       661   ✓       661   ✓
10   factorials and modular arithmetic    313       113   ✗       313   ✓
11   lattice points               1245      1211   ✗      1245   ✓
------------------------------------------------------------------------------
准确率                                   6/11 =   55%      8/11 =   73%
```

| 模式 | 准确率（典型区间） |
| --- | --- |
| 纯 CoT | 约 5~6 / 11（≈ 45%~55%） |
| 代码辅助 | 约 8~9 / 11（≈ 73%~82%） |

**代码辅助模式准确率稳定地显著高于纯 CoT。** 纯 CoT 在需要大数运算 / 大量枚举的题上
频繁算错——例如大数取模（2^2024 mod 1000）、100! 累加取模、x²+y²<400 的格点计数、
n²+12n−2007 何时为完全平方——而代码辅助把这些交给 sympy/numpy 精确计算，逐题命中。

> **不是 100%，也不该是。** 代码辅助并非万能：`gpt-4o-mini` 偶尔会写出「思路对、
> 细节错」的枚举代码（最常翻车的是第 6 题「两平方和计数」的边界、第 8 题「恰好 6 个
> 约数」的计数逻辑），此时精确执行的是一段有 bug 的代码。因此代码辅助的准确率会在
> 上表区间内随机波动，但「显著高于纯 CoT」这一结论每次运行都稳定成立。换更强的模型
> （见下）通常能把这几道题也补齐到接近满分。

## 如何适配 / 扩展

- **换模型 / 供应商**：设 `MODEL` 环境变量即可换模型（如 `MODEL=gpt-4o`、`MODEL=o4-mini`）；
  换供应商则设 `MOONSHOT_API_KEY`（自动切 Kimi）或 `ARK_API_KEY`（自动切豆包），
  或用 `OPENAI_BASE_URL` 指向任意兼容 OpenAI 协议的端点。更强模型能把偶发的 bug 代码补齐。
- **换题库**：编辑 `problems.json`，每题给出 `question` / `answer`（整数）/ `topic` 即可。
  建议新增题目时像现有题一样**先用暴力枚举离线校验真值**，避免答案本身出错。
- **换沙箱能力**：`sandbox.py` 的 `PREAMBLE` 预导入 sympy/numpy/scipy；要支持更多库
  就在此追加 import 并同步更新 `requirements.txt`。

## 局限

- 沙箱是教学级实现（子进程 + 超时 + 临时目录），**不是安全隔离边界**；生产环境应换成
  容器 / gVisor / 无网络的强隔离沙箱。
- 准确率依赖模型质量：小模型仍可能写出有 bug 的代码（见上），代码辅助降低但不消除错误。
- 答案抽取按 `FINAL ANSWER: <整数>` 解析，仅支持整数型答案；非整数 / 多值答案需改
  `extract_answer` 与判分逻辑。

## 文件

| 文件 | 说明 |
| --- | --- |
| `demo.py` | 主程序：对照实验 + function calling 循环 + 结果表 |
| `sandbox.py` | 子进程 Python 沙箱（`run_python`，超时保护，预装数学库） |
| `problems.json` | 11 道竞赛题（题面 + 已校验的整数真值 + 考点） |
| `requirements.txt` | 依赖 |
| `env.example` | 环境变量样例 |
