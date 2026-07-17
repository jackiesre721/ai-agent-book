# 实验 5-6：基于 API 的智能视频剪辑

《深入理解 AI Agent》配套实验。用户给一段含多个场景的视频 + 一句自然语言需求
（如"把冲浪部分剪出来"），Agent 自动定位目标场景、剪出片段并自我审查。

## 目的

验证两个核心机制在多媒体处理中的作用：

1. **两步 Vision 定位**：Proposer 无法直接"看懂"视频，于是委托一个**视频分析子 Agent**，
   用 ffmpeg 抽帧 + Vision LLM 读图来定位目标场景的时间边界。
2. **提议者-审核者（Proposer / Reviewer）**：Proposer 剪辑后无法自证效果，
   由 Reviewer 抽取成片关键帧、用 Vision LLM 检查是否剪对，不合格则反馈、迭代。

## 两步定位原理

Vision LLM 逐帧扫全片既慢又贵，因此采用"先粗后细"：

- **第一步（粗粒度）**：每 **10 秒**抽一帧，把全片的稀疏截图连同"要找哪个场景"一起
  交给 Vision，得到大致区间（如"冲浪在 20–30s"）。
- **第二步（细粒度）**：在粗区间上下各外扩一个粗间隔，每 **1 秒**抽一帧，
  再问 Vision 精确边界（如"15–29s"）。

把这套抽帧-读图封装成**独立子 Agent**：几十张截图只进入子 Agent 的一次性上下文，
不会污染主 Agent（Proposer/Reviewer）的对话历史。demo 末尾会打印两者的 token 对比。

## 提议者-审核者

```
NL 需求 ──► Proposer 解析意图（目标场景 + 特效）
              │
              ▼
         视频分析子 Agent 两步定位 ──► [start, end]
              │
              ▼
         Proposer 用 ffmpeg 剪辑（可加字幕/慢动作）
              │
              ▼
         Reviewer 抽首/中/尾关键帧 ──► Vision 检查 pass/fail + 反馈
              │pass?  否 → Proposer 据反馈修正边界，重剪（最多 3 轮）
              ▼是
           输出成片 final.mp4
```

## 运行

```bash
pip install -r requirements.txt
cp env.example .env        # 填入有效的 OPENAI_API_KEY
python demo.py             # 默认需求"把冲浪的部分剪出来"（完整流程）
python demo.py "把滑雪部分剪出来，并加上字幕 Winter"   # 自定义需求
python demo.py --quick     # 快速模式：粗采样 + 单轮审查，Vision 调用最少（省时省钱）
python demo.py --smoke     # 冒烟自检：仅 ffmpeg 抽帧/剪辑，不调用任何 API
python demo.py --help      # 查看全部参数
```

一条命令即可跑通：生成测试视频 → 两步定位 → 剪辑 → 审查 → 输出 `output/final.mp4`。
每次运行都会清空 `output/`，从干净状态开始（幂等可重复）。完整流程会多次调用
Vision 模型（较慢/耗费额度）；只想验证链路时先跑 `--smoke`（零 API），或用 `--quick`。

## 预期输出示例

以下为 `python demo.py --quick`（默认需求"把冲浪的部分剪出来"）的真实节选：

```text
步骤 1 | Proposer 解析自然语言需求
解析结果：目标场景='surfing scene'  特效=[]

步骤 2 | 视频分析子 Agent：两步 Vision 定位（--quick 快速采样）
  [粗粒度] 每 15s 采样 5 帧 → Vision 得区间 [15, 30]s（依据：The word 'SURFING' appears at t=15s and changes at t=30s.）
  [细粒度] 窗口 [0.0, 45.0] 内每 2s 采样 23 帧 → 精确边界 [16.0, 28.0]s
  >>> 最终定位：起 16.0s  止 28.0s
  真值 [15, 30]s → 起点误差 1.0s，终点误差 2.0s（验收要求 ≤ 3s）

步骤 3-4 | Proposer 剪辑 + Reviewer 审查（迭代）
  Proposer 剪出片段 [16.0, 28.0]s，成片时长 12.0s
  Reviewer：pass=... score=... 检查帧=['0.5', '6.0', '11.5']

Token 统计（子 Agent 隔离截图，主上下文不被污染）
  主 Agent（Proposer+Reviewer）：573 tokens
  子 Agent（两步定位截图）    ：2934 tokens
```

产物（`output/` 目录，真实文件）：

| 文件 | 时长 | 说明 |
| --- | --- | --- |
| `source.mp4` | 54.0s | 程序化生成的 4 场景测试原片 |
| `cut_round1.mp4` | 12.0s | 第 1 轮剪出的候选片段 |
| `final.mp4` | 12.0s | 采用的成片（H.264 + AAC，1280x720@30fps） |

Token 统计印证了核心结论：几十张截图（2934 tokens）只进入**子 Agent**的一次性
上下文，主 Agent 的对话历史（573 tokens）几乎不受截图污染。
（注：合成测试片仅显示"SURFING"字样而非真实冲浪画面，Reviewer 有时会据此判为
不通过——这正是审核者按画面内容如实反馈的体现；换真实视频即无此现象。）

## 依赖

- **ffmpeg / ffprobe**：本机实际剪辑与抽帧。`brew install ffmpeg`（macOS）/
  `apt install ffmpeg`（Ubuntu）。本项目在 ffmpeg 8.0 上验证通过。
- **OPENAI_API_KEY**：用 `gpt-4o` 做视觉定位/审查与文本规划（视觉模型须支持图像输入）。

## 如何适配 / 扩展

### 换模型 / 供应商

模型与端点全部通过**环境变量**注入（见 `env.example`），无需改代码：

- `TEXT_MODEL`：规划/边界修正的文本模型（默认 `gpt-4o`）。
- `VISION_MODEL`：定位/审查的视觉模型，**必须支持图像输入**（默认 `gpt-4o`）。
- `OPENAI_BASE_URL`：换成任何兼容 OpenAI 协议的端点（自建代理、Azure OpenAI、
  或其他厂商网关），配合对应的 `OPENAI_API_KEY` 即可。

```bash
export OPENAI_BASE_URL=https://your-gateway.example.com/v1
export VISION_MODEL=gpt-4o-mini        # 例：用更便宜的视觉模型
export TEXT_MODEL=gpt-4o-mini
```

`agents.py` 里的 `OpenAI()` 客户端会自动读取上述变量（`client()` 惰性初始化）。

### 换输入视频

`make_test_video.py` 用 ffmpeg **程序化生成**一段 54s 的视频，含 4 个明显不同的场景
（HIKING 绿 / SURFING 蓝 / SKIING 白 / CYCLING 橙），每段都叠加大号场景名与时间码水印，
让 Vision 仅凭画面就能准确定位——便于复现验收。

换成**你自己的真实视频**：把 `demo.py` 里的 `SOURCE_VIDEO` 指向你的 mp4，
并注释掉步骤 0 里的 `make_test_video(...)` 调用即可，其余流程完全不变。

### Blender vs. ffmpeg（执行后端）

本项目的**实际剪辑后端是 ffmpeg**（本机未安装 Blender）。
书中原方案用 **Blender Python API（bpy）** 驱动视频序列编辑器完成剪辑。
本机未安装 Blender，故本 demo 用 **ffmpeg** 完成等价的裁剪/拼接/字幕/慢动作。

- 执行层集中在 `video_editor.py`，`apply_edit()` 是唯一的剪辑出口；
- 该文件末尾以注释给出了**等价的 Blender bpy 骨架**（新建序列、设 frame_offset、
  TEXT/SPEED 特效、`bpy.ops.render.render`），读者装好 Blender 后**只需替换这一个文件**，
  `agents.py`/`demo.py` 无需改动——因为核心的"两步 Vision 定位 + 提议者-审核者"与执行层解耦。

**如何切换与取舍：** 装好 Blender 后（`blender --version` 可用），把 `apply_edit()`
改为生成一段 bpy 脚本并用 `blender --background --python edit.py` 执行即可。两种后端的取舍：

| | ffmpeg（当前） | Blender（bpy） |
| --- | --- | --- |
| 定位 | 裁剪/拼接/字幕/变速等 2D 流水线 | 3D 场景、合成、关键帧动画、粒子/摄像机 |
| 上手 | 单二进制、无 GUI、CI 友好 | 需装完整 Blender，体积大、渲染慢 |
| 适用 | 绝大多数"剪一段 + 简单特效"需求 | 需要 3D 合成/复杂转场/图层混合时才值得 |

结论：本实验只做时间轴裁剪与轻量特效，ffmpeg 更快更省依赖；仅当需要真正的 3D/合成
能力时，才建议切到 Blender。

## 文件

| 文件 | 作用 |
| --- | --- |
| `demo.py` | 一条命令跑通的编排入口（含启动自检、迭代循环、token 统计） |
| `agents.py` | `VideoAnalyzerAgent`（两步定位）/ `ProposerAgent` / `ReviewerAgent` |
| `video_editor.py` | ffmpeg 剪辑执行层 + Blender 版接口参考 |
| `make_test_video.py` | 程序化生成含 4 个场景的测试视频 |
| `ffmpeg_utils.py` | ffmpeg/ffprobe 薄封装（统一错误检查、抽帧、探测时长/流） |

`output/`（生成的视频、截图、成片）已被 `.gitignore` 忽略，避免仓库膨胀。

## 局限

- 定位精度取决于场景在画面上的可辨识度；真实视频若场景过渡渐变，边界误差会大于纯色测试片。
- 细粒度步长固定 1s，边界精度上限即 ±1s 量级（满足书中 ±3s 验收）。
- 慢动作音频用 `atempo` 变速，倍率过大时音质下降；转场/多轨混音等复杂特效未覆盖。
- Reviewer 仅抽首/中/尾三帧，长片段中段的偶发错误可能漏检（可调高抽帧密度）。
