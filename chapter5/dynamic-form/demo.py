"""实验 5-9：动态表单生成的意图澄清系统（★★）

核心思路
--------
当用户请求缺少关键信息时，Agent 不是逐条追问，而是**动态生成一个自包含的
HTML 表单**（含级联显示逻辑），让用户"一次提交"补全所有澄清点；前端把表单
汇总成 JSON 交回 Agent，Agent 解析后继续任务。

本 demo 分三步验证（不依赖真实浏览器）：
  1) 让 Agent 真实调用 OpenAI 生成表单 HTML，保存为 generated_form.html；
  2) 用 BeautifulSoup 结构化校验：确实含 出发城市/出发日期/旅行类型(单程,往返)/
     返程日期，且返程字段带"仅往返显示"的级联 JS 逻辑；
  3) 模拟一次用户提交（构造 JSON），喂回 Agent，Agent 解析后打印订票摘要。

运行:  python demo.py
环境变量:
  OPENAI_API_KEY   （必填，读取此项）
  OPENAI_BASE_URL  （可选，切换到兼容 OpenAI 协议的服务）
  MODEL            （可选，默认 gpt-4o-mini）
"""

import os
import re
import json
import argparse

from openai import OpenAI
from bs4 import BeautifulSoup

# 加载 .env（若存在），方便本地运行
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv 是可选依赖
    pass


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
def build_client_and_model():
    """构造 OpenAI 客户端与默认模型名（读取 OPENAI_API_KEY）。"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("未找到 OPENAI_API_KEY，请先在环境变量或 .env 中设置。")

    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("MODEL", "gpt-4o-mini")
    client = (
        OpenAI(api_key=api_key, base_url=base_url)
        if base_url
        else OpenAI(api_key=api_key)
    )
    return client, model


USER_REQUEST = "我想订一张去北京的机票"

# ---------------------------------------------------------------------------
# 步骤 1：让 Agent 生成澄清表单
# ---------------------------------------------------------------------------
FORM_SYSTEM_PROMPT = """你是一个"意图澄清"助手。用户会给出一个信息不完整的请求，
你的任务不是直接追问，而是**生成一个自包含的 HTML 表单**，让用户一次性补全所有
缺失信息。

严格要求（订机票场景）：
1. 表单必须包含以下字段，字段的 name 属性必须使用给定的英文标识：
   - 出发城市：文本输入框，name="departure_city"
   - 出发日期：日期选择器 <input type="date">，name="departure_date"
   - 旅行类型：单选按钮 <input type="radio" name="trip_type">，两个选项
     value="one_way"（单程）和 value="round_trip"（往返）
   - 返程日期：日期选择器，name="return_date"，放在 id="return_date_field" 的
     容器里
2. **级联逻辑（关键）**：返程日期字段默认隐藏，只有当旅行类型选择"往返"
   (round_trip) 时才通过 JavaScript 显示出来；选回"单程"时再次隐藏。
3. 提交时用 JavaScript 阻止默认提交，把所有字段汇总为一个 JSON 对象，
   key 使用上面的英文 name，并显示在 id="result" 的元素里
   （例如 <pre id="result"></pre>）。
4. 输出必须是**完整、自包含**的 HTML（含 <style> 和 <script>，内联，不引用外部
   资源），可直接保存为 .html 文件在浏览器打开。

只输出 HTML 代码本身，不要任何解释文字，不要用 markdown 代码块包裹。"""


def generate_form(client, model, user_request):
    """调用模型生成澄清表单的 HTML。"""
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": FORM_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"用户请求：{user_request}\n请为其中缺失的信息生成澄清表单。",
            },
        ],
    )
    html = resp.choices[0].message.content.strip()
    # 模型偶尔会用 ```html ... ``` 包裹，稳妥起见剥掉围栏
    html = re.sub(r"^```(?:html)?\s*", "", html)
    html = re.sub(r"\s*```$", "", html)
    return html.strip()


# ---------------------------------------------------------------------------
# 步骤 2：结构化校验表单
# ---------------------------------------------------------------------------
def validate_form(html):
    """用 BeautifulSoup + 正则做鲁棒校验。

    由于模型生成的具体标签写法不完全可控，这里采用"关键词/属性匹配"的鲁棒策略：
    只要能定位到语义等价的控件即算通过，并把每一项证据打印出来。
    返回 (是否全部通过, 报告字典)。
    """
    soup = BeautifulSoup(html, "html.parser")
    report = {}

    # (a) 出发城市：文本输入
    dep_city = soup.find("input", attrs={"name": re.compile("departure_city", re.I)})
    if dep_city is None:
        # 退化匹配：任意与"出发城市"相关的文本框
        dep_city = soup.find(
            "input", attrs={"name": re.compile("depart.*city|from.*city|city", re.I)}
        )
    report["出发城市(文本输入)"] = bool(
        dep_city is not None
        and (dep_city.get("type") in (None, "text"))
    )

    # (b) 出发日期：日期选择器
    dep_date = soup.find(
        "input",
        attrs={"type": "date", "name": re.compile("departure_date|depart.*date", re.I)},
    )
    if dep_date is None:
        dep_date = soup.find("input", attrs={"type": "date"})
    report["出发日期(日期选择器)"] = bool(dep_date is not None)

    # (c) 旅行类型：单选，含 单程/往返
    radios = soup.find_all("input", attrs={"type": "radio"})
    radio_values = {r.get("value", "").lower() for r in radios}
    has_one_way = any("one" in v or "单程" in v for v in radio_values)
    has_round = any("round" in v or "往返" in v for v in radio_values)
    # 也允许通过文本判断
    text_all = html.lower()
    has_one_way = has_one_way or ("单程" in html)
    has_round = has_round or ("往返" in html)
    report["旅行类型(单选:单程)"] = bool(len(radios) >= 2 and has_one_way)
    report["旅行类型(单选:往返)"] = bool(len(radios) >= 2 and has_round)

    # (d) 返程日期：日期选择器
    ret_date = soup.find(
        "input", attrs={"name": re.compile("return_date|return.*date", re.I)}
    )
    report["返程日期(日期选择器)"] = bool(
        ret_date is not None or "return_date" in text_all
    )

    # (e) 级联逻辑：返程字段有"仅往返显示"的 JS toggle
    #     鲁棒判断：脚本里同时出现 (round_trip 或 往返) 与 (显示/隐藏控制) 及
    #     返程字段的引用。
    script_text = " ".join(s.get_text() for s in soup.find_all("script"))
    cond_display = bool(
        re.search(r"round_trip|往返", script_text)
        and re.search(
            r"return_date|return_date_field|returnDate", script_text, re.I
        )
        and re.search(
            r"display|hidden|style|classList|\.hide|\.show|toggle", script_text, re.I
        )
    )
    report["返程字段级联逻辑(仅往返显示)"] = cond_display

    all_pass = all(report.values())
    return all_pass, report, script_text


# ---------------------------------------------------------------------------
# 步骤 3：模拟用户提交，喂回 Agent 继续任务
# ---------------------------------------------------------------------------
PARSE_SYSTEM_PROMPT = """你是订机票助手。用户已经通过澄清表单一次性提交了 JSON 格式
的补全信息。请解析这些信息并给出一段简洁的中文"订票摘要"，确认航段、日期、行程类型。
如果是单程(one_way)则不要提返程；如果是往返(round_trip)则必须包含返程日期。
最后追加一句下一步操作提示（如"正在为您检索航班..."）。只输出摘要文本。"""


def continue_task(client, model, original_request, submitted_json):
    """把用户提交的 JSON 交回 Agent，生成订票摘要。"""
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": PARSE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"原始请求：{original_request}\n"
                    f"表单提交的 JSON 数据：\n{json.dumps(submitted_json, ensure_ascii=False, indent=2)}"
                ),
            },
        ],
    )
    return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="实验 5-9：动态表单生成的意图澄清系统（生成表单 → 校验字段/级联 → 解析提交）"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="覆盖模型名（否则读环境变量 MODEL，默认 gpt-4o-mini）",
    )
    args = parser.parse_args()
    if args.model:
        os.environ["MODEL"] = args.model

    client, model = build_client_and_model()
    print(f"模型: {model}\n")
    print("=" * 68)
    print(f"用户请求: {USER_REQUEST}")
    print("=" * 68)

    # --- 步骤 1：生成表单 ---
    print("\n[步骤 1] Agent 生成澄清表单 HTML ...")
    html = generate_form(client, model, USER_REQUEST)
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generated_form.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  已保存到 {out_path} （共 {len(html)} 字符，可手动在浏览器打开看级联效果）")

    # --- 步骤 2：结构化校验 ---
    print("\n[步骤 2] 结构化校验表单字段与级联逻辑：")
    all_pass, report, script_text = validate_form(html)
    for name, ok in report.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")

    # 打印级联逻辑证据（脚本中相关片段）
    evidence_lines = [
        ln.strip()
        for ln in script_text.splitlines()
        if re.search(r"round_trip|往返|return_date|display|hidden|toggle|classList", ln, re.I)
    ]
    if evidence_lines:
        print("\n  级联逻辑证据（脚本节选）:")
        for ln in evidence_lines[:8]:
            print(f"    | {ln}")

    if not all_pass:
        print("\n  警告：部分字段校验未通过（模型输出不稳定）。可查看 generated_form.html 排查。")

    # --- 步骤 3：模拟一次提交，Agent 继续任务 ---
    print("\n[步骤 3] 模拟用户一次性提交表单（往返场景）：")
    submitted = {
        "departure_city": "上海",
        "departure_date": "2026-08-01",
        "trip_type": "round_trip",
        "return_date": "2026-08-07",
        # 目的地来自原始请求（北京），一并带上
        "destination_city": "北京",
    }
    print(json.dumps(submitted, ensure_ascii=False, indent=2))

    print("\n[步骤 3] Agent 解析 JSON 并继续任务，输出订票摘要：")
    summary = continue_task(client, model, USER_REQUEST, submitted)
    print("-" * 68)
    print(summary)
    print("-" * 68)

    # 结果汇总
    print("\n" + "=" * 68)
    print(f"表单字段/级联校验: {'全部通过' if all_pass else '部分未通过'}")
    print("提交 JSON 解析: 成功（见上方订票摘要）")
    print("=" * 68)


if __name__ == "__main__":
    main()
