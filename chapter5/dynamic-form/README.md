# 实验 5-9：动态表单生成的意图澄清系统（★★）

## 目的

验证 Agent 在面对**信息不完整**的用户请求时，不是逐条一问一答，而是**动态生成
一个自包含的 HTML 表单**来一次性澄清意图。表单内置**级联逻辑**（某些字段仅在特定
选择下才显示），用户**一次提交**即可补全全部信息；前端把表单汇总成 JSON 交回
Agent，Agent 解析后继续任务。

验收场景：用户输入"我想订一张去北京的机票"，Agent 生成的表单包含：
- 出发城市（文本输入）
- 出发日期（日期选择器）
- 旅行类型（单选：单程 / 往返）
- **返程日期（仅当选择"往返"时才显示）** ← 级联逻辑

## 机制

`demo.py` 分三步，全程真实调用 OpenAI：

1. **生成表单**：把用户请求发给模型，system prompt 约束它输出一个自包含的
   HTML（内联 `<style>` + `<script>`，含级联显示逻辑和"提交汇总为 JSON"逻辑），
   保存为 `generated_form.html`。
2. **结构化校验（不依赖浏览器）**：用 BeautifulSoup + 正则检查表单确实含要求的
   四类字段，且返程字段带"仅往返显示"的 JS toggle 逻辑，并打印级联逻辑的脚本证据。
3. **模拟提交**：构造一份用户提交的 JSON（往返场景），喂回 Agent；Agent 解析后
   输出订票摘要，验证"解析 JSON → 继续任务"闭环。

## 运行

```bash
pip install -r requirements.txt
cp env.example .env        # 填入 OPENAI_API_KEY（或直接用环境变量）
python demo.py             # 跑完整三步流程（本 demo 为单场景，无需 --limit）
python demo.py --model gpt-4o   # 可选：覆盖模型；python demo.py --help 查看用法
```

跑通后：
- 生成的表单存为 `generated_form.html`，可**手动在浏览器打开**，切换"单程/往返"
  即可看到返程日期字段的级联显示效果，点"提交"会在页面底部打印汇总 JSON。
- 终端会打印字段校验结果、级联逻辑证据、以及 Agent 对提交 JSON 的解析摘要。

环境变量：
- `OPENAI_API_KEY`（必填）
- `OPENAI_BASE_URL`（可选，兼容 OpenAI 协议的第三方端点）
- `MODEL`（可选，默认 `gpt-4o-mini`）

## 真实运行输出（gpt-4o-mini）

```
[步骤 2] 结构化校验表单字段与级联逻辑：
  [PASS] 出发城市(文本输入)
  [PASS] 出发日期(日期选择器)
  [PASS] 旅行类型(单选:单程)
  [PASS] 旅行类型(单选:往返)
  [PASS] 返程日期(日期选择器)
  [PASS] 返程字段级联逻辑(仅往返显示)

  级联逻辑证据（脚本节选）:
    | const returnDateField = document.getElementById('return_date_field');
    | if (this.value === 'round_trip') {
    | returnDateField.style.display = 'block';
    | returnDateField.style.display = 'none';

[步骤 3] Agent 解析 JSON 并继续任务，输出订票摘要：
您选择的航段是从上海到北京，出发日期为2026年8月1日，返程日期为2026年8月7日，
行程类型为往返。正在为您检索航班...
```

## 局限

- **字段命名不完全可控**：不同模型/温度下，生成的 `name`、id 写法可能不同。
  system prompt 已约定英文 `name` 标识（`departure_city` / `departure_date` /
  `trip_type` / `return_date`），校验也采用**鲁棒的关键词/属性匹配**（先按约定
  name 找，找不到再退化到语义匹配 + 文本关键词），因此偶发命名漂移一般仍能通过。
  若某项 `FAIL`，可打开 `generated_form.html` 查看模型实际输出。
- **不依赖真实浏览器**：本机无 playwright，级联逻辑通过"静态解析 JS + 关键词
  匹配"来间接验证，而非真实渲染点击。要看真实级联效果请手动打开 HTML。
- **提交是模拟的**：步骤 3 用一份构造的 JSON 代替真实前端提交，用来验证 Agent
  的"解析 → 继续任务"环节；真实系统里这份 JSON 由表单 `submit` 回调 POST 回后端。
- 生成质量依赖模型；`temperature=0` 以尽量稳定复现。
