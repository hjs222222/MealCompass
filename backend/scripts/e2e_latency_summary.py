"""把多轮端到端探针的输出**聚合成一张区间表**，供 README 直接引用。

为什么需要它：`/recommend` 的延迟含两次 LLM 往返，**单次测量不可代表**。
本项目实测同一份代码、同一份语料，`西红柿炒鸡蛋` 在 7.6–12.0 s 之间跳
（差异全在生成阶段，检索侧稳定在 0.4 s 量级）。所以 README 的端到端表给**区间**，
而区间必须由**多轮原始输出**算出来，不能靠手挑。

本脚本只读 `docs/evidence/e2e_run*.txt`（不含 `*_OLD_PROBE_*` 那种已知有 bug 的轮次），
按 `=== 方法 路径 {JSON}` 分组，输出每次延迟与 min–max。

用法::

    cd backend
    .venv\\Scripts\\python.exe -m scripts.e2e_latency_summary
"""

from __future__ import annotations

import argparse
import pathlib
import re
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CASE_RE = re.compile(r"^=== (?P<method>\w+) (?P<path>/\S+) (?P<payload>\{.*\})$")
LATENCY_RE = re.compile(r"HTTP (?P<status>\d+)\s+耗时 (?P<ms>\d+) ms")

# 这些轮次已被判定不可用（脚本自身有 bug），聚合时必须排除，否则区间是错的
EXCLUDED_MARKERS = ("OLD_PROBE",)


def _resolve(candidate: str) -> pathlib.Path:
    path = pathlib.Path(candidate)
    if path.is_absolute():
        return path
    if candidate.startswith(".."):
        return path.resolve()
    return (REPO_ROOT / path).resolve()


def parse_runs(directory: pathlib.Path) -> tuple[list[str], list[dict[str, Any]]]:
    """返回 (参与聚合的文件名, 每条用例的记录列表)。"""
    used: list[str] = []
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("e2e_run*.txt")):
        if any(marker in path.name for marker in EXCLUDED_MARKERS):
            continue
        used.append(path.name)
        current: dict[str, Any] | None = None
        for line in path.read_text("utf-8").splitlines():
            header = CASE_RE.match(line.strip())
            if header:
                current = {
                    "run": path.name,
                    "case": f"{header['method']} {header['path']} {header['payload']}",
                    "status": None,
                    "ms": None,
                }
                records.append(current)
                continue
            latency = LATENCY_RE.search(line)
            if latency and current is not None and current["ms"] is None:
                current["status"] = int(latency["status"])
                current["ms"] = int(latency["ms"])
                current = None
    return used, records


def summarize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record["case"], []).append(record)

    rows: list[dict[str, Any]] = []
    for case, items in grouped.items():
        values = sorted(int(item["ms"]) for item in items if item["ms"] is not None)
        statuses = sorted({int(item["status"]) for item in items if item["status"] is not None})
        rows.append(
            {
                "case": case,
                "runs": len(items),
                "statuses": statuses,
                "min_ms": values[0] if values else None,
                "max_ms": values[-1] if values else None,
                "spread_ms": (values[-1] - values[0]) if len(values) > 1 else 0,
                "values": values,
            }
        )
    rows.sort(key=lambda row: row["min_ms"] or 0, reverse=True)
    return rows


def format_table(rows: list[dict[str, Any]], used: list[str]) -> str:
    lines = [f"参与聚合的轮次（{len(used)}）：{', '.join(used)}", ""]
    lines.append(f"{'场景':<58} {'轮数':>4} {'min':>8} {'max':>8} {'极差':>8}  状态码")
    for row in rows:
        case = row["case"] if len(row["case"]) <= 56 else row["case"][:53] + "..."
        spread = f"{row['spread_ms'] / 1000:.1f}s" if row["spread_ms"] > 1000 else f"{row['spread_ms']}ms"
        lines.append(
            f"{case:<58} {row['runs']:>4} {row['min_ms']:>7}ms {row['max_ms']:>7}ms {spread:>8}  "
            f"{'/'.join(str(s) for s in row['statuses'])}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="聚合多轮端到端探针输出")
    parser.add_argument("--dir", default="docs/evidence", help="证据目录")
    parser.add_argument("--out", default="docs/evidence/e2e_latency_summary.txt", help="输出路径")
    parser.add_argument("--print-only", action="store_true", help="只打印，不写文件")
    args = parser.parse_args()

    directory = _resolve(args.dir)
    used, records = parse_runs(directory)
    if not used:
        raise SystemExit(f"没找到可聚合的轮次：{directory}\\e2e_run*.txt")

    rows = summarize(records)
    text = format_table(rows, used)

    # 把"哪些轮次被排除"也写清楚，避免区间看起来像手挑的
    excluded = [p.name for p in sorted(directory.glob("e2e_run*.txt")) if any(m in p.name for m in EXCLUDED_MARKERS)]
    if excluded:
        text += "\n\n已排除的轮次（已知脚本 bug，不得参与统计）：" + ", ".join(excluded)

    text += (
        "\n\n怎么用：\n"
        "  1. README 的端到端表用这里的 min–max，不要用单次值；\n"
        "  2. 波动几乎全部来自 LLM 生成阶段——检索侧（/recipes/search）三轮极差只有几十毫秒；\n"
        "  3. 含 LLM 往返的指标默认按多次运行给区间，这是仓库规矩（见 docs/mistakes.md）。"
    )

    print(text)
    if not args.print_only:
        target = _resolve(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
        print(f"\n[留底] {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
