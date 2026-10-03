"""SE373 · BTVN#3 · Môi trường tool mockup, kịch bản kiểm thử và khai báo tool cho LangChain."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from models import POLICY, REQUIREMENT, Scenario

if TYPE_CHECKING:
    from harness import Runner


# MÔI TRƯỜNG
def _format_vnd(n: int) -> str:
    return f"{n:,}".replace(",", ".") + "đ"


# (id, giờ, giá, hoàn được)
BASE_FLIGHTS = [
    ("VJ604", "06:15", 1_450_000, True),
    ("QH118", "09:30", 1_750_000, True),
    ("VN122", "08:00", 1_850_000, True),
    ("VN134", "14:20", 1_600_000, True),     # chiều: sai giờ
    ("VJ612", "10:40", 2_310_000, False),    # quá giá
]
APPROVAL_FLIGHTS = [
    ("VJ604", "06:15", 1_950_000, False),    # chuyến duy nhất hợp lệ, nhưng vé không hoàn > 1,5 triệu
    ("QH118", "09:30", 2_450_000, True),
    ("VN134", "14:20", 1_600_000, True),
    ("VJ612", "10:40", 2_310_000, False),
]


SCENARIOS = {s.name: s for s in [
    Scenario("binh_thuong", "Mọi thứ trơn tru: chuyến rẻ nhất hợp lệ đặt được ngay",
             BASE_FLIGHTS, frozenset({"dat_muc_tieu"}), False),
    Scenario("doi_giua_chung", "Môi trường đổi: VJ604 hết chỗ, giá QH118 nhảy lên 2,05 triệu lúc check",
             BASE_FLIGHTS, frozenset({"dat_muc_tieu"}), False,
             out_of_stock=frozenset({"VJ604"}), actual_prices={"QH118": 2_050_000}),
    Scenario("tool_loi", "check_seat timeout liên tục: không thể hoàn thành, phải dừng sớm và báo người",
             BASE_FLIGHTS, frozenset({"lap", "be_tac", "ke_hoach_hong", "tu_dung_chua_dat"}), True,
             check_timeout=True),
    Scenario("can_duyet", "Chuyến duy nhất hợp lệ là vé không hoàn 1,95 triệu: phải chờ người duyệt",
             APPROVAL_FLIGHTS, frozenset({"cho_nguoi"}), True),
]}


class Environment:
    """Tool mockup. Dữ liệu tĩnh, không mạng, mỗi lần chạy ra cùng kết quả."""

    BOOKING_CODES = ["4XJ2", "7KQ9", "2MZ5", "9PL3"]

    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.flights = {i: dict(id=i, time=t, price=p, refundable=r) for i, t, p, r in scenario.steps}
        self.bookings: dict[str, dict] = {}
        self.side_effects: list[str] = []          # mọi hành động có tác dụng phụ đã xảy ra

    def call(self, name: str, args: dict) -> dict:
        return getattr(self, name)(**args)

    # ---- tool 1
    def search_flights(self, origin: str, dest: str, date: str) -> dict:
        if not re.fullmatch(r"\d{2}/\d{2}", date):
            return {"status": "invalid_param", "param": "date", "allowed_format": "dd/mm"}
        if (origin, dest, date) != (REQUIREMENT.origin, REQUIREMENT.destination, REQUIREMENT.date_vn):
            return {"status": "ok", "matched": 0, "flights": [],
                    "hint": f"Chỉ có dữ liệu {REQUIREMENT.origin}→{REQUIREMENT.destination} ngày {REQUIREMENT.date_vn}"}
        found = [dict(flight_id=f["id"], depart_date=REQUIREMENT.date_iso, depart_time=f["time"],
                      price=f["price"], price_text=_format_vnd(f["price"])) for f in self.flights.values()]
        return {"status": "ok", "matched": len(found), "flights": found}

    # ---- tool 2
    def check_seat(self, flight_id: str) -> dict:
        if self.scenario.check_timeout:
            return {"status": "error", "error": "timeout",
                    "hint": "Dịch vụ tồn kho chưa phản hồi"}
        flight = self.flights.get(flight_id)
        if not flight:
            return {"status": "invalid_param", "param": "flight_id",
                    "allowed": list(self.flights)}
        sold_out = flight_id in self.scenario.out_of_stock
        price = self.scenario.actual_prices.get(flight_id, flight["price"])
        return {"status": "ok", "flight_id": flight_id, "available": not sold_out,
                "seats_left": 0 if sold_out else 3, "price": price, "price_text": _format_vnd(price),
                "refundable": flight["refundable"]}

    # ---- tool 3
    def book_seat(self, flight_id: str, seat: str) -> dict:
        flight = self.flights.get(flight_id)
        if not flight or flight_id in self.scenario.out_of_stock:
            return {"status": "error", "error": "sold_out_or_unknown", "flight_id": flight_id}
        code = self.BOOKING_CODES[len(self.bookings)]
        self.bookings[code] = dict(code=code, flight_id=flight_id, seat=seat, state="held", paid=False,
                                   price=self.scenario.actual_prices.get(flight_id, flight["price"]),
                                   depart_date=REQUIREMENT.date_iso, depart_time=flight["time"])
        self.side_effects.append(f"book_seat({flight_id},{seat})")
        return {"status": "ok", "booking_code": code, "booking_status": "held", "flight_id": flight_id}

    # ---- tool 4
    def pay(self, booking_code: str, method: str) -> dict:
        booking = self.bookings.get(booking_code)
        if not booking:
            return {"status": "error", "error": "booking_not_found"}
        if method != POLICY.payment_method:
            return {"status": "invalid_param", "param": "method",
                    "allowed": [POLICY.payment_method]}
        booking.update(state="paid", paid=True)
        self.side_effects.append(f"pay({booking_code})")
        return {"status": "ok", "booking_code": booking_code, "booking_status": "paid"}

    # ---- tool 5
    def get_booking(self, booking_code: str) -> dict:
        booking = self.bookings.get(booking_code)
        if not booking:
            return {"status": "error", "error": "booking_not_found"}
        if booking["state"] == "paid":           # xác nhận đến muộn một nhịp, như hệ thống thật
            booking["state"] = "confirmed"
        return {"status": "ok", "booking_code": booking["code"], "booking_status": booking["state"],
                "paid": booking["paid"], "price": booking["price"], "price_text": _format_vnd(booking["price"]),
                "depart_date": booking["depart_date"], "depart_time": booking["depart_time"],
                "flight_id": booking["flight_id"]}

    def read_booking(self, code: str) -> dict | None:
        """Đọc thẳng nguồn sự thật, không qua tool, không đổi trạng thái (kiểm chứng chéo)."""
        return self.bookings.get(code)


# ============================================================ tool cho LangChain
class SearchArgs(BaseModel):
    origin: str = Field(description="Mã sân bay đi, ví dụ SGN")
    dest: str = Field(description="Mã sân bay đến, ví dụ DAD")
    date: str = Field(description="Ngày bay dạng dd/mm, ví dụ 07/10")


class FlightArgs(BaseModel):
    flight_id: str = Field(description="Mã chuyến lấy từ search_flights, ví dụ VN122")


class BookArgs(BaseModel):
    flight_id: str
    seat: str = Field(description="Số ghế, ví dụ 12A")


class PayArgs(BaseModel):
    booking_code: str
    method: str = Field(description="Phương thức thanh toán, dùng corp_card")


class BookingArgs(BaseModel):
    booking_code: str


TOOL_SPECS = {
    "search_flights": ("Tìm chuyến bay theo tuyến và ngày. Trả danh sách chuyến kèm giờ và giá tham khảo.", SearchArgs),
    "check_seat": ("Kiểm tra chỗ trống và GIÁ THẬT của một chuyến. Bắt buộc gọi trước book_seat.", FlightArgs),
    "book_seat": ("Giữ chỗ một ghế trên chuyến đã check_seat. Có tác dụng phụ.", BookArgs),
    "pay": ("Thanh toán một booking đang giữ chỗ. Có tác dụng phụ, không hoàn tác.", PayArgs),
    "get_booking": ("Đọc trạng thái booking: confirmed, đã trả tiền, giá, ngày giờ bay.", BookingArgs),
}


def make_tools(runner: "Runner") -> list[StructuredTool]:
    def wrap(name, description, schema):
        return StructuredTool.from_function(
            func=lambda **kw: runner.run_tool(name, kw),
            name=name, description=description, args_schema=schema)
    return [wrap(n, d, s) for n, (d, s) in TOOL_SPECS.items()]
