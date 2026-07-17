# -*- coding: utf-8 -*-
"""玩家 Agent：每个玩家 = 一个独立的 LLM Agent，拥有**严格隔离的私有上下文**。

信息隔离的实现要点：
- 每个 PlayerAgent 只维护自己的 `memory`（一串它「观察到 / 被告知」的事件）。
- 法官（judge.py）决定把哪条信息推给哪个 Agent 的 memory——狼人才会收到「队友
  身份」，预言家才会收到「查验结果」，公开发言才会推给所有人。
- Agent 每次思考（发言 / 投票 / 用技能）时，只能看到自己 memory 里的内容，
  因此不可能「偷看」到本不该看到的信息。这就是信息权限控制的落点。
"""

import json
import os
import re
from typing import List, Optional

from openai import OpenAI

from .roles import Role, ROLE_STRATEGY, faction_of


# 全局唯一的 OpenAI 客户端。读取 OPENAI_API_KEY；模型默认 gpt-4o-mini。
# 注意：按实验约束，只用 OpenAI，不用 OPENROUTER/ANTHROPIC/DEEPSEEK/SILICONFLOW。
_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    """返回全局共享的 OpenAI 客户端（懒加载，进程内单例）。"""
    global _client
    if _client is None:
        _client = OpenAI()  # 自动读取环境变量 OPENAI_API_KEY
    return _client


class PlayerAgent:
    """一个玩家 Agent，封装其身份、私有上下文与 LLM 调用。"""

    def __init__(self, name: str, role: Role):
        self.name = name          # 玩家名，如 "P3"
        self.role = role          # 真实身份（只有本人和法官知道）
        self.faction = faction_of(role)
        self.alive = True
        # 私有上下文：这个 Agent「看得到」的全部信息。别的 Agent 无法访问。
        self.memory: List[str] = []

    # ---- 上下文注入：只有法官会调用，用来把信息投递进这个 Agent 的私有上下文 ----
    def observe(self, event: str):
        """把一条信息写入本 Agent 的私有上下文。"""
        self.memory.append(event)

    # ---- system prompt：角色设定 + 策略。狼人的队友身份不写在这里，而是由法官
    #      在游戏开始时通过 observe() 投递，以便审计能记录「谁看到了队友身份」。 ----
    def _system_prompt(self, players: List[str]) -> str:
        return (
            f"你正在玩一局狼人杀。你是玩家 {self.name}。\n"
            f"你的真实身份是【{self.role.value}】，属于【{self.faction.value}】。\n"
            f"本局玩家共 {len(players)} 人：{'、'.join(players)}。\n\n"
            f"{ROLE_STRATEGY[self.role]}\n\n"
            "重要：只能依据你已知的信息推理，不要臆造你无从得知的身份。发言要像真人，"
            "简洁自然，有理有据。"
        )

    def _context_block(self) -> str:
        """把私有上下文拼成给 LLM 的一段文字。"""
        if not self.memory:
            return "（暂无信息）"
        return "\n".join(f"- {m}" for m in self.memory)

    def _chat(self, instruction: str, players: List[str], max_tokens: int,
              json_mode: bool = False) -> str:
        """组装 system + user 消息并调用 LLM；user 消息里只拼接本 Agent 自己的
        私有上下文（`_context_block`），绝不包含其他玩家的私密信息。"""
        messages = [
            {"role": "system", "content": self._system_prompt(players)},
            {"role": "user", "content":
                f"【你目前掌握的信息（仅你可见）】\n{self._context_block()}\n\n"
                f"【当前任务】\n{instruction}"},
        ]
        kwargs = dict(model=_MODEL, messages=messages, temperature=0.8,
                      max_tokens=max_tokens)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = get_client().chat.completions.create(**kwargs)
        return resp.choices[0].message.content.strip()

    # ---------- 三种对外能力：发言 / 决策（选目标）/ 投票 ----------

    def speak(self, players: List[str]) -> str:
        """白天公开发言。返回一段发言文本（公开信息）。"""
        instruction = (
            "现在轮到你在白天公开发言。请结合你掌握的信息，发表一段简短的发言"
            "（2~4 句话，60 字以内）。符合你的身份与策略。直接输出发言内容，不要加引号。"
        )
        return self._chat(instruction, players, max_tokens=180)

    def choose_target(self, prompt: str, candidates: List[str],
                      players: List[str], allow_none: bool = False) -> Optional[str]:
        """让 Agent 从候选人中选一个目标（夜间刀人 / 查验 / 用毒 / 救人判断等）。

        用 JSON 模式返回，鲁棒地解析出目标玩家名。
        """
        opt = "，也可以选择放弃（target 填 \"none\"）" if allow_none else ""
        instruction = (
            f"{prompt}\n候选玩家：{'、'.join(candidates)}{opt}。\n"
            "请只返回 JSON：{\"target\": \"玩家名或none\", \"reason\": \"一句话理由\"}"
        )
        raw = self._chat(instruction, players, max_tokens=120, json_mode=True)
        target = self._parse_target(raw, candidates, allow_none)
        return target

    def vote(self, candidates: List[str], players: List[str]) -> Optional[str]:
        """投票放逐。返回票投给谁（或弃票 none）。"""
        instruction = (
            "现在是白天投票放逐环节。请根据全场发言与你的推理，投出你认为最可能是"
            "狼人的玩家。\n候选玩家：" + "、".join(candidates) + "。\n"
            "请只返回 JSON：{\"target\": \"玩家名\", \"reason\": \"一句话理由\"}"
        )
        raw = self._chat(instruction, players, max_tokens=120, json_mode=True)
        return self._parse_target(raw, candidates, allow_none=True)

    # ---------- 解析工具 ----------
    @staticmethod
    def _parse_target(raw: str, candidates: List[str], allow_none: bool) -> Optional[str]:
        target = None
        try:
            data = json.loads(raw)
            target = str(data.get("target", "")).strip()
        except Exception:
            # 兜底：直接从文本里正则找候选玩家名
            target = raw
        if allow_none and target.lower() in ("none", "", "弃票", "放弃"):
            return None
        # 归一化：精确匹配优先，否则模糊匹配（找出现的候选名）
        if target in candidates:
            return target
        for c in candidates:
            if c in (target or ""):
                return c
        # 最后兜底：从原始串里搜 Pn
        m = re.search(r"P\d+", target or "")
        if m and m.group(0) in candidates:
            return m.group(0)
        # 实在解析不出：好人默认弃票，狼人/必须选的场景由调用方兜底
        return None if allow_none else (candidates[0] if candidates else None)
