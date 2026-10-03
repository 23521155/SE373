"""SE373 · BTVN#3 · Các dataclass dùng chung của agent đặt vé."""
from __future__ import annotations

from dataclasses import dataclass, field

USD_PER_TOKEN = (1.0, 5.0)        # (vào, ra) của Haiku 4.5, dùng ước lượng chi phí


# Ràng buộc và chính sách là DỮ LIỆU: đổi ở đây, không sửa logic (S62).
@dataclass(frozen=True)
class Requirement:
    origin: str = "SGN"
    destination: str = "DAD"
    date_vn: str = "07/10"
    date_iso: str = "2026-10-07"
    before_time: str = "12:00"
    max_price: int = 2_000_000

    def describe(self) -> str:
        return (f"Đặt 1 vé {self.origin}→{self.destination} ngày {self.date_vn}, khởi hành trước "
                f"{self.before_time}, giá không quá {self.max_price:,}đ".replace(",", "."))


@dataclass(frozen=True)
class Policy:
    allowed_tools: frozenset = frozenset(
        {"search_flights", "check_seat", "book_seat", "pay", "get_booking"})
    non_refundable_ticket_limit: int = 1_500_000    # vé không hoàn và vượt mức này → cần người duyệt
    payment_method: str = "corp_card"


@dataclass(frozen=True)
class Budget:
    max_tool_calls: int = 12
    max_llm_calls: int = 16
    max_tokens: int = 80_000
    max_seconds: float = 180.0
    max_planning_attempts: int = 3


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    steps: list
    expected_outcomes: frozenset            # outcome được coi là đúng
    no_side_effects: bool      # True: dừng đúng nghĩa là CHƯA đặt/trả gì
    out_of_stock: frozenset = frozenset()
    actual_prices: dict = field(default_factory=dict)      # flight_id → giá thật lúc check_seat
    check_timeout: bool = False


@dataclass
class Result:
    mode: str
    scenario: str
    outcome: str
    reason: str
    passed: bool

    llm_calls: int
    tool_calls: int

    input_tokens: int
    output_tokens: int

    elapsed_seconds: float

    side_effects: list
    handoff: dict | None
    trace: list
    flags: list

    @property
    def cost(self) -> float:
        return (self.input_tokens * USD_PER_TOKEN[0] + self.output_tokens * USD_PER_TOKEN[1]) / 1e6


# Ràng buộc, chính sách, ngân sách mặc định (dữ liệu, đổi ở đây).
REQUIREMENT, POLICY, BUDGET = Requirement(), Policy(), Budget()
