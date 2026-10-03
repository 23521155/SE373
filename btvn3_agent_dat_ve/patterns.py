"""SE373 · BTVN#3 · Ba mẫu thiết kế: ReAct, Plan-then-Execute, Lai (LangGraph)."""
from __future__ import annotations

import json
import re
import time
from typing import TypedDict

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from fake_model import message_text
from harness import HarnessStop, LLMCounter, Runner
from lib.harness import kiem_can_cu as check_grounding
from models import BUDGET, POLICY, REQUIREMENT, Result, Scenario
from tools import make_tools


# ============================================================== 4 · BA MẪU
SYSTEM = (
    "Bạn là agent đặt vé máy bay. Chỉ dùng tool để lấy thông tin và hành động, không tự bịa "
    "chuyến bay, giá hay mã vé.\n"
    "Quy tắc: luôn check_seat để lấy giá thật trước khi book_seat; chỉ book chuyến thoả MỌI ràng buộc; "
    "sau book_seat thì pay bằng corp_card rồi get_booking để xác nhận.\n"
    "Nếu tool báo bi_chan hoặc lỗi, đọc huong_di và đổi cách; không lặp lại lời gọi vừa thất bại.\n"
    "Bạn chạy tự động, không có người trả lời giữa chừng: đừng hỏi lại người dùng. Tự chọn chuyến rẻ nhất "
    "thoả ràng buộc và làm tiếp tới khi vé confirmed; chỉ dừng khi xong hoặc không thể tiếp tục.\n"
    "Ràng buộc (JSON, đây là nguồn sự thật): {constraints}"
)
GOAL = "Đặt giúp tôi một vé: " + REQUIREMENT.describe() + "."


def _constraints_json() -> str:
    return json.dumps(REQUIREMENT.__dict__, ensure_ascii=False)


def _package_result(mode, runner, counter, kind, reason, normal, model_text=None) -> Result:
    scenario = runner.scenario
    passed = kind in scenario.expected_outcomes and not (scenario.no_side_effects and runner.env.side_effects)
    # nguồn hợp lệ của một dữ kiện: kết quả tool HOẶC chính yêu cầu của người dùng
    flags = check_grounding(model_text, runner.tool_results + [GOAL])["khong_co_nguon"] if model_text else []
    return Result(mode, scenario.name, kind, reason, passed, counter.calls, runner.tool_count,
                  counter.tokens_in, counter.tokens_out, time.time() - runner.t0,
                  list(runner.env.side_effects),
                  None if normal else runner.handoff(kind, reason), runner.trace, flags)


# ---------------------------------------------------------------- mẫu 1 · ReAct
def run_react(model, scenario: Scenario) -> Result:
    counter = LLMCounter()
    runner = Runner(scenario, counter)
    agent = create_agent(
        model=model, tools=make_tools(runner), system_prompt=SYSTEM.format(constraints=_constraints_json()),
        middleware=[ModelCallLimitMiddleware(run_limit=BUDGET.max_llm_calls, exit_behavior="end")])
    try:
        out = agent.invoke({"messages": [{"role": "user", "content": GOAL}]},
                           {"callbacks": [counter], "recursion_limit": 80})
    except HarnessStop as e:
        return _package_result("react", runner, counter, e.kind, e.reason, e.normal)
    text = message_text(out["messages"][-1].content)
    if counter.calls >= BUDGET.max_llm_calls:
        return _package_result("react", runner, counter, "het_ngan_sach", "ModelCallLimitMiddleware", False, text)
    return _package_result("react", runner, counter, "tu_dung_chua_dat",
                           "model thôi gọi tool nhưng tiêu chí hoàn thành chưa đạt", False, text)


# ------------------------------------------------- mẫu 2, 3 · LangGraph (P&E, Lai)
class GraphState(TypedDict, total=False):
    plan: list[dict]
    idx: int
    history: list[dict]
    plan_attempts: int
    needs_replan: bool
    stop: dict | None


PLAN_PROMPT = (
    "[[LAP_KE_HOACH]]\nMục tiêu: {goal}\nRàng buộc (JSON): {constraints}\n"
    "Tool có thể dùng: search_flights, check_seat, book_seat, pay, get_booking.\n"
    "{history}\n"
    "Hãy lập kế hoạch các bước CÒN LẠI. Chỉ trả JSON, không giải thích: "
    '{{"buoc": [{{"tool": "<tên tool>", "muc_dich": "<1 câu>"}}]}}'
)
EXEC_PROMPT = (
    "[[THUC_THI:{tool}]]\nMục tiêu: {goal}\nRàng buộc (JSON): {constraints}\n"
    "Bước hiện tại: gọi đúng tool `{tool}`. Mục đích: {purpose}\n"
    "Lịch sử tool đã chạy:\n{history}\n"
    "Chọn tham số dựa trên lịch sử và ràng buộc. Chỉ gọi tool, không trả lời văn bản."
)


def _historymessage_text(history: list[dict]) -> str:
    if not history:
        return "Lịch sử tool: (chưa có)"
    return "Lịch sử tool (mỗi dòng một lời gọi):\n" + "\n".join(
        json.dumps(x, ensure_ascii=False) for x in history)


def is_significant_change(obs: dict) -> bool:
    """'Observation đổi đáng kể?' của mẫu lai: lỗi, bị chặn, hết chỗ, hoặc giá vượt trần."""
    return (obs.get("status") != "ok" or obs.get("available") is False
            or obs.get("price", 0) > REQUIREMENT.max_price and "refundable" in obs)


def _parse_plan(text: str) -> list[dict]:
    m = re.search(r"\{.*\}", text, re.S)
    try:
        steps = json.loads(m.group(0))["buoc"]
        return [{"tool": s["tool"], "purpose": s.get("muc_dich", "")} for s in steps]
    except Exception:
        raise HarnessStop("ke_hoach_khong_hop_le", "planner không trả JSON kế hoạch đúng schema")


def _review_plan(plan: list[dict]) -> str | None:
    """Người duyệt bằng luật: kế hoạch nhìn thấy được TRƯỚC khi chạy (S22)."""
    names = [s["tool"] for s in plan]
    if any(n not in POLICY.allowed_tools for n in names):
        return "kế hoạch có tool ngoài danh sách cho phép"
    if len(names) > 8:
        return "kế hoạch quá dài (>8 bước)"
    for before, after in [("check_seat", "book_seat"), ("book_seat", "pay")]:
        if after in names and before in names and names.index(before) > names.index(after):
            return f"sai thứ tự: {after} đứng trước {before}"
    return None


def run_graph(model, scenario: Scenario, hybrid: bool) -> Result:
    mode = "lai" if hybrid else "plan_execute"
    counter = LLMCounter()
    runner = Runner(scenario, counter)
    tools = make_tools(runner)
    tools_by_name = {t.name: t for t in tools}
    config = {"callbacks": [counter]}

    def safe(fn):
        def wrapper(state):
            try:
                return fn(state)
            except HarnessStop as e:
                return {"stop": {"kind": e.kind, "reason": e.reason, "normal": e.normal}}
        return wrapper

    def make_plan(state: GraphState):
        runner.check_budget()
        prompt = PLAN_PROMPT.format(goal=GOAL, constraints=_constraints_json(),
                                    history=_historymessage_text(state.get("history", [])))
        ai = model.invoke([SystemMessage(SYSTEM.format(constraints=_constraints_json())),
                           HumanMessage(prompt)], config)
        plan = _parse_plan(message_text(ai.content))
        error = _review_plan(plan)
        if error:
            raise HarnessStop("ke_hoach_khong_hop_le", error)
        return {"plan": plan, "idx": 0, "plan_attempts": state.get("plan_attempts", 0) + 1,
                "needs_replan": False}

    def execute(state: GraphState):
        step = state["plan"][state["idx"]]
        prompt = EXEC_PROMPT.format(tool=step["tool"], goal=GOAL, constraints=_constraints_json(),
                                    purpose=step["purpose"], history=_historymessage_text(state.get("history", [])))
        ai = model.bind_tools(tools, tool_choice=step["tool"]).invoke(
            [SystemMessage(SYSTEM.format(constraints=_constraints_json())), HumanMessage(prompt)], config)
        if not ai.tool_calls or ai.tool_calls[0]["name"] != step["tool"]:
            raise HarnessStop("khong_goi_tool", f"executor không gọi được `{step['tool']}`")
        call = ai.tool_calls[0]
        obs = tools_by_name[call["name"]].invoke(call["args"])
        history = state.get("history", []) + [{"tool": call["name"], "args": call["args"], "obs": obs}]
        out = {"history": history, "idx": state["idx"] + 1}
        if is_significant_change(obs):
            # plan_attempts gồm cả kế hoạch đầu tiên, nên số lần LẬP LẠI đã dùng là plan_attempts - 1
            if hybrid and state.get("plan_attempts", 1) - 1 < BUDGET.max_planning_attempts:
                out["needs_replan"] = True              # lai: lập lại kế hoạch từ những gì vừa thấy
            else:
                out["stop"] = {"kind": "het_ngan_sach" if hybrid else "ke_hoach_hong",
                               "reason": (f"đã lập lại kế hoạch {BUDGET.max_planning_attempts} lần, "
                                          f"bước `{call['name']}` vẫn lệch" if hybrid else
                                          f"bước `{call['name']}` lệch kế hoạch, mẫu này không lập lại"),
                               "normal": False}
        return out

    def after_execute(state: GraphState):
        if state.get("stop"):
            return END
        if state.get("needs_replan"):
            return "make_plan"
        return END if state["idx"] >= len(state["plan"]) else "execute"

    g = StateGraph(GraphState)
    g.add_node("make_plan", safe(make_plan))
    g.add_node("execute", safe(execute))
    g.add_edge(START, "make_plan")
    g.add_conditional_edges("make_plan", lambda s: END if s.get("stop") else "execute")
    g.add_conditional_edges("execute", after_execute)
    final = g.compile().invoke({"history": [], "plan_attempts": 0, "idx": 0},
                               {**config, "recursion_limit": 100})

    stop = final.get("stop")
    if stop:
        return _package_result(mode, runner, counter, stop["kind"], stop["reason"], stop["normal"])
    return _package_result(mode, runner, counter, "het_ke_hoach", "chạy hết kế hoạch mà tiêu chí chưa đạt", False)


PATTERNS = {"react": lambda m, s: run_react(m, s),
            "plan_execute": lambda m, s: run_graph(m, s, hybrid=False),
            "lai": lambda m, s: run_graph(m, s, hybrid=True)}
