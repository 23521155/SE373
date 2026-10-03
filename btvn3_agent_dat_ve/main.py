"""SE373 · BTVN#3 · Agent đặt vé máy bay: harness + 3 mẫu thiết kế + đánh giá.

Một file, ba phần:

    1. MÔI TRƯỜNG   tool mockup (search_flights, check_seat, book_seat, pay,
                    get_booking) với bốn kịch bản kiểm thử
    2. HARNESS      ràng buộc là dữ liệu · tiêu chí hoàn thành kiểm bằng code ·
                    kiểm quyền · phát hiện lặp/bế tắc · ngân sách · bàn giao
    3. BA MẪU       ReAct · Plan-then-Execute (LangGraph) ·
                    Lai "ReAct + Plan" (LangGraph, lập lại kế hoạch khi cần)

Cả ba mẫu dùng CHUNG một harness, nên khác biệt đo được là của mẫu
thiết kế chứ không phải của harness.

Chạy:
    python btvn3_agent_dat_ve.py                  # ANTHROPIC_API_KEY → model thật
    python btvn3_agent_dat_ve.py --gia-lap        # model giả lập, chạy lặp lại được
    python btvn3_agent_dat_ve.py --kich-ban doi_giua_chung --mau react --trace
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

from dotenv import load_dotenv

from fake_model import DEFAULT_MODEL, FakeBookingModel, real_model
from models import Result
from patterns import PATTERNS
from tools import SCENARIOS

load_dotenv()


# ======================================================= 5 · ĐÁNH GIÁ
def summarize(results: list[Result]) -> str:
    avg = lambda xs: sum(xs) / len(xs)
    lines = ["| Kịch bản | Mẫu | Đúng | Outcome | Lượt LLM | Lượt tool | Token | Giây | USD |",
             "|---|---|---|---|---|---|---|---|---|"]
    for scenario in dict.fromkeys(r.scenario for r in results):
        for mode in dict.fromkeys(r.mode for r in results):
            rows = [r for r in results if r.scenario == scenario and r.mode == mode]
            if not rows:
                continue
            outcomes = ", ".join(f"{o}×{n}" if n > 1 else o for o, n in Counter(r.outcome for r in rows).items())
            lines.append(f"| {scenario} | {mode} | {sum(r.passed for r in rows)}/{len(rows)} | {outcomes} | "
                         f"{avg([r.llm_calls for r in rows]):.1f} | {avg([r.tool_calls for r in rows]):.1f} | "
                         f"{avg([r.input_tokens + r.output_tokens for r in rows]):.0f} | "
                         f"{avg([r.elapsed_seconds for r in rows]):.1f} | "
                         f"{avg([r.cost for r in rows]):.4f} |")
    lines += ["", "**Tổng theo mẫu (mọi kịch bản):**", "",
              "| Mẫu | Tỉ lệ đúng | Lượt LLM TB | Token TB | Giây TB | USD TB | Dừng có bàn giao | Bịa dữ kiện |",
              "|---|---|---|---|---|---|---|---|"]
    for mode in dict.fromkeys(r.mode for r in results):
        rows = [r for r in results if r.mode == mode]
        lines.append(f"| {mode} | {sum(r.passed for r in rows)}/{len(rows)} | "
                     f"{avg([r.llm_calls for r in rows]):.1f} | "
                     f"{avg([r.input_tokens + r.output_tokens for r in rows]):.0f} | "
                     f"{avg([r.elapsed_seconds for r in rows]):.1f} | "
                     f"{avg([r.cost for r in rows]):.4f} | {sum(r.handoff is not None for r in rows)} | "
                     f"{sum(len(r.flags) for r in rows)} |")
    return "\n".join(lines)


def print_trace(result: Result) -> None:
    print(f"\n── trace · {result.mode} · {result.scenario} ──")
    for t in result.trace:
        args = ", ".join(f"{a}={v!r}" for a, v in t["args"].items())
        print(f"[V{t['round']}] {t['tool']}({args}) → {t['obs']}" + (f"   ⚠ {t['warning']}" if t["warning"] else ""))
    print(f"Dừng: {result.outcome} · {result.reason}")
    if result.handoff:
        print("Bàn giao:", json.dumps(result.handoff, ensure_ascii=False))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="BTVN#3 · so sánh ReAct / Plan-then-Execute / Lai")
    p.add_argument("--gia-lap", dest="use_fake", action="store_true", help="dùng model giả lập, không cần API key")
    p.add_argument("--lan", dest="runs", type=int, default=3, help="số lần lặp mỗi (mẫu, kịch bản) với model thật")
    p.add_argument("--kich-ban", dest="scenario", default="all", choices=["all", *SCENARIOS])
    p.add_argument("--mau", dest="pattern", default="all", choices=["all", *PATTERNS])
    p.add_argument("--trace", action="store_true", help="in trace của lần chạy đầu mỗi tổ hợp")
    p.add_argument("--xuat", dest="output", default=None,
                   help="tên file kết quả; bỏ trống thì tự đặt theo kiểu chạy (giả lập / thật đầy đủ / thật một phần)")
    args = p.parse_args()

    use_fake = args.use_fake or not os.environ.get("ANTHROPIC_API_KEY")
    model = FakeBookingModel() if use_fake else real_model()
    runs = 1 if use_fake else args.runs
    if args.output is None:                      # mỗi kiểu chạy một file, không ghi đè nhau
        kind = "gia_lap" if use_fake else "that"
        if args.scenario == "all" and args.pattern == "all":
            args.output = f"ket_qua_{kind}.md"
        else:
            args.output = f"ket_qua_{kind}_{args.scenario}_{args.pattern}.md"
    model_name = "model giả lập (token là ước lượng)" if use_fake else os.environ.get("SE373_MODEL", DEFAULT_MODEL)
    print(f"Model: {model_name} · {runs} lần/tổ hợp")

    results = []
    for scenario in (SCENARIOS.values() if args.scenario == "all" else [SCENARIOS[args.scenario]]):
        for pattern in (PATTERNS if args.pattern == "all" else [args.pattern]):
            for i in range(runs):
                r = PATTERNS[pattern](model, scenario)
                results.append(r)
                print(f"  {scenario.name:15} {pattern:13} #{i + 1} → {r.outcome:16} {'ĐÚNG' if r.passed else 'SAI '} "
                      f"llm={r.llm_calls} tool={r.tool_calls} tok={r.input_tokens + r.output_tokens}")
                if args.trace and i == 0:
                    print_trace(r)

    table = summarize(results)
    print("\n" + table)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(f"Model: {model_name} · {runs} lần/tổ hợp\n\n{table}\n")
    print(f"\nĐã ghi {args.output}")


if __name__ == "__main__":
    main()
