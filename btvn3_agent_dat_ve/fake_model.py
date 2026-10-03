"""SE373 · BTVN#3 · Model giả lập (deterministic) và hàm tạo model thật."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from models import POLICY, REQUIREMENT

DEFAULT_MODEL = "anthropic:claude-haiku-4-5-20251001"


# ================================================================ model giả lập
def message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)


def next_step(history: list[tuple]) -> tuple[str, dict] | None:
    """Chính sách của 'model' giả lập: một agent hợp lý, deterministic. history = [(tool, args, obs)]."""
    req, flights, checks, code, paid, confirmed, blocked = REQUIREMENT, [], {}, None, False, False, set()
    for tool, args, obs in history:
        if tool == "search_flights" and obs.get("status") == "ok":
            flights = obs["flights"]
        elif tool == "check_seat":
            checks[args.get("flight_id")] = obs
        elif tool == "book_seat":
            if obs.get("status") == "ok":
                code = obs["booking_code"]
            elif obs.get("status") == "bi_chan":
                blocked.add(args.get("flight_id"))
        elif tool == "pay" and obs.get("status") == "ok":
            paid = True
        elif tool == "get_booking" and obs.get("booking_status") == "confirmed":
            confirmed = True
    if not flights:
        return "search_flights", {"origin": req.origin, "dest": req.destination, "date": req.date_vn}
    if code:
        if not paid:
            return "pay", {"booking_code": code, "method": POLICY.payment_method}
        return None if confirmed else ("get_booking", {"booking_code": code})
    candidates = sorted((f for f in flights if f["depart_time"] < req.before_time
                         and f["price"] <= req.max_price and f["flight_id"] not in blocked),
                        key=lambda f: f["price"])
    for f in candidates:
        obs = checks.get(f["flight_id"])
        if obs is None or obs.get("status") != "ok":     # chưa check, hoặc lỗi thì thử lại
            return "check_seat", {"flight_id": f["flight_id"]}
        if obs["available"] and obs["price"] <= req.max_price:
            return "book_seat", {"flight_id": f["flight_id"], "seat": "12A"}
    return None


def _remaining_plan(history: list[tuple]) -> list[str]:
    done = {tool for tool, _, obs in history if obs.get("status") == "ok"}
    if "search_flights" not in done:
        return ["search_flights", "check_seat", "book_seat", "pay", "get_booking"]
    if "book_seat" not in done:
        return ["check_seat", "book_seat", "pay", "get_booking"]
    if "pay" not in done:
        return ["pay", "get_booking"]
    return ["get_booking"] if "get_booking" not in done else []


class FakeBookingModel(BaseChatModel):
    """Model giả lập cho cả ba mẫu: ReAct (đọc messages), planner và executor (đọc prompt)."""

    @property
    def _llm_type(self) -> str:
        return "btvn3-model-gia"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FakeBookingModel":
        return self

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                  run_manager: CallbackManagerForLLMRun | None = None, **kw: Any) -> ChatResult:
        ai = self._decide(messages)
        tokens_in = sum(len(message_text(m.content)) + len(json.dumps(getattr(m, "tool_calls", None) or [],
                                                               ensure_ascii=False))
                        for m in messages) // 3 + 450          # 450 ≈ định nghĩa tool
        tokens_out = (len(message_text(ai.content)) + len(json.dumps(ai.tool_calls, ensure_ascii=False))) // 3 + 20
        ai.usage_metadata = {"input_tokens": tokens_in, "output_tokens": tokens_out,
                             "total_tokens": tokens_in + tokens_out}
        return ChatResult(generations=[ChatGeneration(message=ai)])

    def _decide(self, messages: list[BaseMessage]) -> AIMessage:
        last = message_text(messages[-1].content) if messages else ""
        if "[[LAP_KE_HOACH]]" in last:
            history = self._history_from_prompt(last)
            return AIMessage(content=json.dumps(
                {"buoc": [{"tool": t, "muc_dich": ""} for t in _remaining_plan(history)]}))
        if "[[THUC_THI:" in last:
            name = re.search(r"\[\[THUC_THI:(\w+)\]\]", last).group(1)
            step = next_step(self._history_from_prompt(last))
            if not step or step[0] != name:
                return AIMessage(content="Không có tham số hợp lý cho bước này.")
            return AIMessage(content="", tool_calls=[
                {"name": step[0], "args": step[1], "id": "call_pte", "type": "tool_call"}])
        return self._react(messages)

    @staticmethod
    def _history_from_prompt(prompt: str) -> list[tuple]:
        history = []
        for line in prompt.splitlines():
            if line.startswith('{"tool"'):
                d = json.loads(line)
                history.append((d["tool"], d["args"], d["obs"]))
        return history

    @staticmethod
    def _react(messages: list[BaseMessage]) -> AIMessage:
        calls, history = {}, []
        for m in messages:
            if m.type == "ai":
                for c in m.tool_calls:
                    calls[c["id"]] = (c["name"], c["args"])
            elif m.type == "tool":
                tool, args = calls.get(m.tool_call_id, ("?", {}))
                history.append((tool, args, json.loads(m.content)))
        step = next_step(history)
        if step is None:
            return AIMessage(content="Chưa tìm được vé phù hợp với ràng buộc.")
        return AIMessage(content="", tool_calls=[
            {"name": step[0], "args": step[1], "id": f"call_{len(history) + 1}", "type": "tool_call"}])


def real_model():
    from langchain.chat_models import init_chat_model
    return init_chat_model(os.environ.get("SE373_MODEL", DEFAULT_MODEL), temperature=0)
