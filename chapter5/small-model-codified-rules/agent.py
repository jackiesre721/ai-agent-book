"""
航空客服 Agent（实验 5-3）

两种模式：
  - control（控制组）：系统提示只有自然语言政策；工具描述极简、无 expected_* 参数；
    工具内部不做任何校验（天真执行）。政策是否被遵守完全靠模型自身推理。
  - codified（实验组）：三重保障——
      (1) 系统提示保留同样的自然语言政策；
      (2) 工具描述列出完整政策，并以可选 expected_* 参数引导模型"调用前逐条核对"；
      (3) 工具内部基于数据库真值做代码化校验，可拒绝违规操作。
"""

from __future__ import annotations

import json
import os
import time

from openai import OpenAI

from airline_env import AirlineEnv


MODEL = os.environ.get("MODEL", "gpt-4o-mini")  # 默认用小模型作为代表
MAX_TURNS = 6


# ---------------------------------------------------------------------------
# 自然语言政策（两组共享，放进系统提示）
# ---------------------------------------------------------------------------
NL_POLICY = """你是 SkyWing 航空公司的客服 Agent，可以帮乘客查询和取消预订。

【退款政策（自然语言）】
- 经济舱基础票（basic_economy）默认不可退款。
- 例外 1：下单后 24 小时内，可全额退款。
- 例外 2：航班被航司取消，或发生重大延误（延误 ≥ 3 小时），可全额退款。
- 经济舱灵活票（economy_flex）与商务舱（business）可全额退款。
- 若不可退款：应礼貌解释政策，并主动提议替代方案（如保留客票改签、申请旅行信用点），
  绝不能给用户退款。

请先判断能否退款，再决定是否调用取消/退款工具。乘客自述的信息（舱位、下单时间等）
可能不准确，应以系统查询到的预订信息为准。"""

CONTROL_SYSTEM = NL_POLICY

CODIFIED_SYSTEM = NL_POLICY + """

【操作要求】
调用 cancel_reservation 前，请先用 get_reservation 查询真实预订信息，逐条核对退款政策，
并在 expected_refundable / expected_reason 参数中如实填写你的判断（这是一份调用前 checklist）。
系统会以数据库真值为准进行校验：若你的判断与真值不符或存在违规，调用会被拒绝。"""


# ---------------------------------------------------------------------------
# 工具 schema
# ---------------------------------------------------------------------------
GET_RESERVATION_TOOL = {
    "type": "function",
    "function": {
        "name": "get_reservation",
        "description": "查询预订的详细信息（舱位、下单时间、下单时长、航班状态、价格等，均为系统真值）。",
        "parameters": {
            "type": "object",
            "properties": {
                "reservation_id": {"type": "string", "description": "预订编号，如 R001"},
            },
            "required": ["reservation_id"],
        },
    },
}

CONTROL_CANCEL_TOOL = {
    "type": "function",
    "function": {
        "name": "cancel_reservation",
        "description": "取消一个预订并处理退款。",
        "parameters": {
            "type": "object",
            "properties": {
                "reservation_id": {"type": "string", "description": "预订编号"},
            },
            "required": ["reservation_id"],
        },
    },
}

CODIFIED_CANCEL_TOOL = {
    "type": "function",
    "function": {
        "name": "cancel_reservation",
        "description": (
            "取消预订并按政策退款。调用前请逐条核对退款政策（这是一份 checklist）：\n"
            "1) 舱位是否为 basic_economy？非基础经济票可退。\n"
            "2) 若为基础经济票：下单是否在 24 小时内？（以系统返回的 hours_since_booking 为准）\n"
            "3) 若为基础经济票：航班是否被航司取消，或延误 ≥ 3 小时（重大延误）？\n"
            "满足 1 的非基础票、或满足 2/3 例外之一，才可退款。\n"
            "请在 expected_refundable / expected_reason 中如实填写你的核对结论。"
            "系统会以数据库真值校验，不可退款的调用将被拒绝。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reservation_id": {"type": "string", "description": "预订编号"},
                "expected_refundable": {
                    "type": "boolean",
                    "description": "你核对政策后判断该预订是否可退款（checklist 自报值）。",
                },
                "expected_reason": {
                    "type": "string",
                    "enum": ["flexible_fare", "within_24h", "airline_caused", "non_refundable_basic_economy"],
                    "description": "你判断可退/不可退的政策依据。",
                },
            },
            "required": ["reservation_id", "expected_refundable", "expected_reason"],
        },
    },
}


def _make_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("未设置 OPENAI_API_KEY，请参考 env.example 配置。")
    return OpenAI(api_key=api_key)


def _dispatch(env: AirlineEnv, mode: str, name: str, args: dict) -> dict:
    """把模型的工具调用路由到对应模式的环境方法。"""
    if name == "get_reservation":
        return env.get_reservation(args.get("reservation_id", ""))
    if name == "cancel_reservation":
        if mode == "control":
            return env.cancel_reservation_naive(args.get("reservation_id", ""))
        return env.cancel_reservation_codified(
            args.get("reservation_id", ""),
            expected_refundable=args.get("expected_refundable"),
            expected_reason=args.get("expected_reason"),
        )
    return {"status": "error", "message": f"未知工具 {name}"}


def run_agent(env: AirlineEnv, user_message: str, mode: str, verbose: bool = False,
              model: str | None = None) -> dict:
    """跑一个 case，返回 {final_text, transcript}。env 被就地修改（状态即真值）。

    model 为空时回退到模块级默认 MODEL（小模型）。三方对照实验里，可用它把
    "控制组"跑在一个更大的模型上，验证"小模型+代码化规则"能否追平"大模型裸跑"。
    """
    assert mode in ("control", "codified")
    model = model or MODEL
    client = _make_client()

    if mode == "control":
        system, tools = CONTROL_SYSTEM, [GET_RESERVATION_TOOL, CONTROL_CANCEL_TOOL]
    else:
        system, tools = CODIFIED_SYSTEM, [GET_RESERVATION_TOOL, CODIFIED_CANCEL_TOOL]

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_message},
    ]
    transcript: list[dict] = []
    final_text = ""

    for _turn in range(MAX_TURNS):
        resp = _chat_with_retry(client, messages, tools, model=model)
        msg = resp.choices[0].message

        if msg.tool_calls:
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls
                ],
            })
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = _dispatch(env, mode, tc.function.name, args)
                transcript.append({"tool": tc.function.name, "args": args, "result": result})
                if verbose:
                    print(f"    [tool] {tc.function.name}({args}) -> {result.get('status')}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
            continue

        final_text = msg.content or ""
        messages.append({"role": "assistant", "content": final_text})
        break

    return {"final_text": final_text, "transcript": transcript}


def _chat_with_retry(client: OpenAI, messages, tools, model: str | None = None, retries: int = 3):
    last_err = None
    model = model or MODEL
    for i in range(retries):
        try:
            return client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                temperature=0.0,  # 尽量降低随机性，保证可复现
            )
        except Exception as e:  # noqa: BLE001 —— 网络/限流等，简单重试
            last_err = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f"OpenAI 调用失败：{last_err}")
