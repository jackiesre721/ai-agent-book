# 实验 8-5：Agent 从网络上寻找工具，实现自我进化（Alita 式）

> 《深入理解 AI Agent》配套代码 · ★★★
> 核心理念：**「最小预定义，最大自我进化」**。

## 目的

大多数 Agent 的能力上限由「人类预先写好的工具」决定。本实验反其道而行之：Agent **不预置任何领域工具**，
只有五个通用的「元工具」。当它遇到自己不会做的任务时，会自己上网**寻找开源库 / API**、**阅读文档**、
**在沙箱里测试**、把可行方案**封装成新工具存入工具库**，然后用新工具完成任务——像 Alita 一样自我进化。
再次遇到同类任务时，它会先在工具库里**复用**已造好的工具，而不是重新造轮子。

全程强调**幻觉控制**：所有数字与结论必须来自真实的搜索结果、文档或代码执行输出。

## 五个基础工具（没有任何领域工具）

| 工具 | 作用 | 实现 |
| --- | --- | --- |
| `web_search` | 搜索开源库 / API | DuckDuckGo，**无需 key**（lite + html 双端点，带退避重试） |
| `read_webpage` | 阅读 README / API 文档 | requests + BeautifulSoup 抽取正文 |
| `code_interpreter` | 沙箱里真实执行代码验证方案 | **子进程沙箱** + 超时；可 `pip_install` 到临时目录 |
| `create_tool` | 把验证过的功能封装为标准工具并持久化 | 写入 `tool_library/<name>.json`（元数据 + 代码） |
| `search_tools` | 从工具库按名称/描述检索，用于**复用** | 关键词匹配 |

## 自我进化流水线

```
分析任务
  → search_tools（先查工具库是否已有可复用工具）
      命中 ─────────────────► 直接调用该工具作答（工具复用）
      未命中 ↓
  → web_search  找无需 key 的开源 Python 库
  → read_webpage 读 README / PyPI 文档
  → code_interpreter 在沙箱里真跑，print 出真实数据（可 pip 安装依赖）
  → create_tool 封装为「通用、参数化」的标准工具，存入工具库
  → 调用新工具，用真实数据作答
```

为抑制幻觉与「偷懒」，代码里内置了几道**守卫**：

- 未用 `code_interpreter` 打印出真实数据前，**禁止** `create_tool`；
- `create_tool` 的代码若含 `mock / 模拟 / 示例数据 / fake` 等字样，**拒绝**入库；
- 已验证真实数据却想跳过封装直接作答时，强制提醒先 `create_tool`；
- 工具库里的工具需先经 `search_tools` 命中（或刚创建）才「解锁」为可调用——从而强制「先检索复用」的流程。

## 运行

```bash
pip install -r requirements.txt
cp env.example .env        # 填入 OPENAI_API_KEY（默认模型 gpt-4o-mini）
python demo.py             # 跑「进化 + 复用」两个任务
python demo.py --fresh     # 先清空 tool_library/ 再跑，重现「从零进化」（重复演示时推荐）
python demo.py --help      # 查看全部参数
```

> 工具库会**持久化**到 `tool_library/`。若上一轮已封装出 `get_stock_price`，再次直接运行时任务一会在第 0 步
> 就 `search_tools` 命中并复用它，从而看不到"进化"全过程；想重现进化请加 `--fresh`。

`demo.py` 会连续跑两个任务：

1. **NVDA**（演示进化）：从零基础工具出发，搜索→读文档→沙箱测试→封装 `get_stock_price` 工具→给出 NVIDIA 真实股价与周涨跌幅。
2. **AAPL**（演示复用）：`search_tools` 命中刚创建的 `get_stock_price`，**直接复用**，不再重新搜索/创建。

> 也可切换到其它 OpenAI 兼容供应商：`LLM_PROVIDER=moonshot|ark`（配合对应的 `MOONSHOT_API_KEY` / `ARK_API_KEY`），
> 或用 `LLM_MODEL` 覆盖模型名。搜索用 DuckDuckGo，不需要任何搜索 key。

## 一次真实运行的轨迹（节选，真实联网 + 真实调用 OpenAI）

**任务一 · NVDA**（自我进化，注意错误恢复）：

```
[step 1] search_tools("stock price")      -> 命中 0 个（工具库为空）
[step 2] web_search("open source python library stock price") -> yfinance · PyPI ...
[step 3] read_webpage(pypi.org/project/yfinance) / github.com/ranaroussi/yfinance
[step 4] code_interpreter(...)  -> stdout 为空，note: “没有 print 出真实数据，不算验证通过”
[step 5] code_interpreter(...)  -> "最新股价: 205.91..., 涨跌幅: 1.54"   ← 真实数据，验证通过
[step 6] create_tool("get_stock_price", 参数化 ticker/period, 内部真调 yfinance)
[step 7] get_stock_price(ticker="NVDA") -> {latest_price: 205.71, change_percentage: 1.44}
[最终回答] NVIDIA(NVDA) 最新股价 205.71 美元，与一周前相比 +1.44%。数据来源 yfinance。
```

**任务二 · AAPL**（工具复用，未重新搜索/创建）：

```
[step 1] search_tools("stock price")  -> 命中 get_stock_price（复用！）
[step 2] get_stock_price(ticker="AAPL") -> {latest_price: 330.48, change_percentage: 4.51}
[最终回答] Apple(AAPL) 最新股价 330.48 美元，与一周前相比 +4.51%。
任务二轨迹 = ['search_tools', 'get_stock_price']  → 没有 web_search / create_tool ✅ 复用成立
```

（数字随行情实时变化，每次运行不同；上面是某次真实运行的结果。）

## 结论

- Agent 从**零领域工具**出发，仅凭五个元工具，就自主发现了 `yfinance`、封装出通用 `get_stock_price` 工具，并给出**真实**股价与涨跌幅。
- 第二个任务通过 `search_tools` **命中并复用**了已造好的工具，未重复搜索/造轮子——工具库让 Agent「越用越强」。
- 空输出提醒 + 反 mock 守卫 + 「先验证再封装」有效**抑制了幻觉**：一次跑通中，模型第一次测试代码忘了 `print`，被 note 提醒后自行修正，最终基于真实执行结果作答。

## 关于书中任务一（YouTube 字幕）

书中「任务一：YouTube 字幕理解，答案 100000000」依赖 `youtube-transcript-api` + 特定视频，联网/风控/视频下架都可能导致不稳定，故本仓库**用可稳定复现的实时金融任务来实际验证机制**。
若要复现 YouTube 场景，同一套流水线适用：让 Agent `web_search` 找到 `youtube-transcript-api` → 读文档 → 沙箱测试 → `create_tool` 封装字幕抓取工具即可。

## ⚠️ 安全边界提醒（务必阅读）

本实验会**执行模型生成的代码**并**从网络安装第三方包**，天然带有风险：

- **供应链风险**：`code_interpreter` 会 `pip install` 模型选中的包。真实/生产环境必须对包来源做**白名单/审计/固定版本与哈希**，谨防拼写抢注（typosquatting）与恶意包。
- **代码执行隔离**：这里的沙箱仅为**演示级**（子进程隔离 + 超时），**不是安全沙箱**。生产环境应使用容器 / gVisor / seccomp / 无网络命名空间 / 只读文件系统 / 资源限额等强隔离，并最好断网或仅放通白名单域名。
- **自进化工具库需人审**：`create_tool` 落盘的工具会被后续任务反复复用，等于把「模型写的代码」变成常驻能力。建议对入库工具做人工/自动审查，并记录来源与审计日志。
- 本目录默认把 `tool_library/*.json` 与 `.sandbox_packages/` 纳入 `.gitignore`（运行时产物）。
