"""SE373 · BTVN#3 · Harness: tiêu chí hoàn thành, kiểm quyền, phát hiện lặp, ngân sách, bàn giao."""
from __future__ import annotations

import json
import time
from typing import Callable

from langchain_core.callbacks import BaseCallbackHandler

from lib.harness import LoopDetector
from lib.harness import ban_giao as build_handoff
from models import BUDGET, POLICY, REQUIREMENT, Requirement, Scenario
from tools import Environment


# ============================================================= 3 · HARNESS
def check_completion(booking: dict | None, req: Requirement = REQUIREMENT) -> tuple[bool, list[str]]:
    """Tiêu chí hoàn thành = vị từ chạy bằng code, độc lập với lời của model (S43)."""
    if not booking:
        return False, ["chưa có booking"]
    errors = []
    if booking["state"] != "confirmed":
        errors.append(f"status={booking['state']}")
    if not booking["paid"]:
        errors.append("chưa thanh toán")
    if booking["price"] > req.max_price:
        errors.append(f"giá {booking['price']} > {req.max_price}")
    if booking["depart_date"] != req.date_iso:
        errors.append(f"sai ngày {booking['depart_date']}")
    if not booking["depart_time"] < req.before_time:
        errors.append(f"sai giờ {booking['depart_time']}")
    return not errors, errors


class HarnessStop(Exception):
    """Harness quyết định dừng. normal=True khi đạt mục tiêu."""

    def __init__(self, kind: str, reason: str, normal: bool = False):
        super().__init__(reason)
        self.kind, self.reason, self.normal = kind, reason, normal


class LLMCounter(BaseCallbackHandler):
    """Đếm lượt gọi model và token thật từ usage_metadata."""

    def __init__(self):
        self.calls = self.tokens_in = self.tokens_out = 0

    def on_llm_end(self, response, **kw):
        self.calls += 1
        for g in response.generations[0]:
            usage = getattr(getattr(g, "message", None), "usage_metadata", None) or {}
            self.tokens_in += usage.get("input_tokens", 0)
            self.tokens_out += usage.get("output_tokens", 0)

    @property
    def total(self) -> int:
        return self.tokens_in + self.tokens_out


class Runner:
    """Lớp harness: mọi lời gọi tool của cả ba mẫu đều đi qua run_tool().

    Thứ tự theo checklist S35:
        0 kiểm quyền → (thực thi) → 1 tiêu chí hoàn thành → 2 lặp → 3 bế tắc → 4 ngân sách
    Ngân sách kiểm CUỐI CÙNG để không che mất chẩn đoán.
    """

    def __init__(self, scenario: Scenario, counter: LLMCounter,
                 approver: Callable[[dict], bool] = lambda request: False):
        self.scenario, self.env, self.counter = scenario, Environment(scenario), counter
        self.approver = approver                # "người duyệt"; mặc định không có ai online
        self.detector = LoopDetector(window=6, repeat_k=3, same_obs_k=4, stall_n=5)
        self.t0 = time.time()
        self.tool_count = 0
        self.trace: list[dict] = []
        self.seen_flights: dict[str, dict] = {}  # flight_id → thông tin đã thấy (search + check)
        self.booking_codes: list[str] = []
        self.milestones: set[str] = set()        # cột mốc tiến triển của bài toán
        self.tool_results: list[str] = []

    # ---- lớp 0 · kiểm quyền và ràng buộc, chạy TRƯỚC khi thực thi
    def check_permission(self, name: str, args: dict) -> tuple[str, str]:
        if name not in POLICY.allowed_tools:
            return "bi_chan", f"tool '{name}' không nằm trong danh sách cho phép"
        if name == "book_seat":
            flight = self.seen_flights.get(args.get("flight_id"))
            if not flight or "checked_price" not in flight:
                return "bi_chan", "chưa check_seat chuyến này: phải xác nhận chỗ và giá thật trước"
            if not flight.get("in_stock"):
                return "bi_chan", "chuyến này hết chỗ theo check_seat"
            if flight["checked_price"] > REQUIREMENT.max_price:
                return "bi_chan", f"giá thật {flight['checked_price']} vượt trần {REQUIREMENT.max_price}"
            if not flight["depart_time"] < REQUIREMENT.before_time or flight["depart_date"] != REQUIREMENT.date_iso:
                return "bi_chan", "sai ngày hoặc giờ so với yêu cầu gốc"
            if not flight["refundable"] and flight["checked_price"] > POLICY.non_refundable_ticket_limit:
                request = {"tool": name, "args": args, "gia": flight["checked_price"], "hoan": False}
                if not self.approver(request):
                    return "cho_nguoi", (f"vé không hoàn {flight['checked_price']:,}đ vượt hạn mức "
                                         f"{POLICY.non_refundable_ticket_limit:,}đ".replace(",", "."))
        if name == "pay":
            booking = self.env.read_booking(args.get("booking_code", ""))
            if not booking or booking["price"] > REQUIREMENT.max_price:
                return "bi_chan", "booking không tồn tại hoặc giá vượt trần"
        return "cho_phep", ""

    # ---- vòng harness quanh một lời gọi tool
    def run_tool(self, name: str, args: dict) -> dict:
        self.tool_count += 1
        decision, reason = self.check_permission(name, args)
        if decision == "cho_nguoi":
            self._record(name, args, {"status": "cho_phe_duyet"}, "CẦN NGƯỜI")
            raise HarnessStop("cho_nguoi", reason)
        if decision == "bi_chan":
            obs = {"status": "bi_chan", "ly_do": reason,
                   "huong_di": "Chọn chuyến khác thoả ràng buộc, hoặc dừng và báo người dùng"}
        else:
            obs = self.env.call(name, args)
            self._update_state(name, args, obs)
        self.tool_results.append(json.dumps(obs, ensure_ascii=False))

        # lớp 1 · tiêu chí hoàn thành: đọc thẳng nguồn sự thật, không tin lời model
        for code in self.booking_codes:
            done, _ = check_completion(self.env.read_booking(code))
            if done:
                self._record(name, args, obs, "ĐẠT MỤC TIÊU")
                raise HarnessStop("dat_muc_tieu", f"booking {code} thoả mọi tiêu chí", True)

        # lớp 2, 3 · lặp và bế tắc
        warning = self.detector.check(name, args, observation=obs, progress=len(self.milestones))
        self._record(name, args, obs, warning)
        if warning:
            raise HarnessStop("lap" if warning.startswith("LOOP") else "be_tac", warning)
        self.check_budget()                      # lớp 4 · kiểm cuối cùng
        return obs

    def check_budget(self) -> None:
        b = BUDGET
        if self.tool_count >= b.max_tool_calls:
            raise HarnessStop("het_ngan_sach", f"chạm trần {b.max_tool_calls} lượt tool")
        if self.counter.calls >= b.max_llm_calls:
            raise HarnessStop("het_ngan_sach", f"chạm trần {b.max_llm_calls} lượt gọi model")
        if self.counter.total >= b.max_tokens:
            raise HarnessStop("het_ngan_sach", f"chạm trần {b.max_tokens} token")
        if time.time() - self.t0 >= b.max_seconds:
            raise HarnessStop("het_ngan_sach", f"chạm trần {b.max_seconds:.0f} giây")

    def _update_state(self, name: str, args: dict, obs: dict) -> None:
        if obs.get("status") != "ok":
            return
        if name == "search_flights" and obs["flights"]:
            self.milestones.add("search")
            for f in obs["flights"]:
                self.seen_flights.setdefault(f["flight_id"], {}).update(
                    depart_date=f["depart_date"], depart_time=f["depart_time"])
        elif name == "check_seat":
            self.seen_flights.setdefault(obs["flight_id"], {}).update(
                checked_price=obs["price"], in_stock=obs["available"], refundable=obs["refundable"])
            if obs["available"] and obs["price"] <= REQUIREMENT.max_price:
                self.milestones.add("check_ok")
        elif name == "book_seat":
            self.milestones.add("book")
            self.booking_codes.append(obs["booking_code"])
        elif name == "pay":
            self.milestones.add("pay")
        elif name == "get_booking" and obs["booking_status"] == "confirmed":
            self.milestones.add("confirmed")

    def _record(self, name: str, args: dict, obs: dict, warning) -> None:
        self.trace.append(dict(round=len(self.trace) + 1, tool=name, args=args,
                               obs=json.dumps(obs, ensure_ascii=False)[:110], warning=warning))

    # ---- lớp bàn giao
    def handoff(self, kind: str, reason: str) -> dict:
        question = {
            "cho_nguoi": "Có duyệt đặt vé này không? (vé không hoàn, vượt hạn mức tự động)",
            "lap": "Tool đang lỗi liên tục. Thử lại sau, đổi kênh đặt, hay báo khách?",
            "be_tac": "Đã đổi hướng nhiều lần mà không nhích thêm. Nới ràng buộc nào?",
            "het_ngan_sach": "Hết ngân sách khi chưa xong. Tiếp tục với ngân sách mới hay nới ràng buộc?",
        }.get(kind, "Agent dừng khi chưa đạt mục tiêu. Bước tiếp theo nên là gì?")
        return build_handoff(
            ly_do=f"{kind} · {reason}",
            da_thu=[f"{t['tool']}({','.join(str(v) for v in t['args'].values())})" for t in self.trace],
            trang_thai={"cot_moc": sorted(self.milestones), "ma_ve": self.booking_codes,
                        "tac_dung_phu": self.env.side_effects, "so_tool": self.tool_count},
            cau_hoi=question)
