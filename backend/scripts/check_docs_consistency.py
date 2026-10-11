"""把 `README.md` 的评估表与 `docs/evidence/` 入库证据**逐格对账**，不一致就退出码非 0。

为什么需要它：本项目最重的纪律是「正文数字必须能追到 `docs/evidence/` 的原始输出」。
但在这之前，这条纪律**只靠人自觉**——我改过 README 的数字，也改过证据文件，
两者对不上时没有任何东西会报错。手工比对过一次不算机制，能进 CI 才算。

本脚本做三件事：

1. **指标格对账**：README「评估结果」表里每个数字（单值或 `a–b%` 区间）都必须覆盖
   `docs/evidence/eval_reports_summary.json` 里对应报告的真实值。
2. **区间来源对账**：`hybrid_rerank` 那些区间格子必须**恰好**等于
   `docs/evidence/rerank_variance.txt` 记录的跨轮极差（不能手写一个"差不多"的区间）。
3. **来源标注对账**：README 里引用的每个 `docs/evidence/...` 路径都必须真实存在
   （防止文档指向一个已删除/改名/压根没写过的证据文件）。

只读：不改 README，也不改 evidence；`--fix` 不做（自动改正文数字是危险操作）。

用法::

    cd backend
    .venv\\Scripts\\python.exe -m scripts.check_docs_consistency
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_README = "README.md"
DEFAULT_EVIDENCE = "docs/evidence"

MODE_LABELS = {
    "vector": "纯向量",
    "hybrid": "混合（向量 + BM25 + RRF）",
    "hybrid_rerank": "混合 + 重排",
}
# README 表列顺序：模式 | Recall@5 | Recall@10 | MRR@10 | nDCG@5 | ...
TABLE_COLUMNS = (("recall@5", "R@5"), ("recall@10", "R@10"), ("mrr@10", "MRR@10"), ("ndcg@5", "nDCG@5"))

# 单值 `77.50%` 或区间 `77.50–78.33%`（en dash 与连字符都认）
CELL = re.compile(r"^\**(\d+\.\d+)(?:\s*[–-]\s*(\d+\.\d+))?%\**$")
VARIANCE_LINE = re.compile(r"^\s*(?P<key>\w+@\d+): min=(?P<lo>[\d.]+) max=(?P<hi>[\d.]+)", re.MULTILINE)
EVIDENCE_REF = re.compile(r"\]\(\.?/?((?:docs/)?evidence/[^)\s]+)\)")

TOLERANCE = 0.005  # 报告值四舍五入到 2 位小数的容差


def _resolve(candidate: str) -> pathlib.Path:
    path = pathlib.Path(candidate)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def parse_cell(cell: str) -> tuple[float, float] | None:
    """把表里的一个指标格解析成 (下界, 上界)；解析不了返回 None。"""
    match = CELL.match(cell.strip())
    if match is None:
        return None
    low = float(match.group(1))
    high = float(match.group(2)) if match.group(2) else low
    return (low, high)


def check_metrics(readme: str, summary: dict[str, Any]) -> list[str]:
    """README 评估表 vs 评估摘要。返回问题列表（空 = 通过）。"""
    problems: list[str] = []
    by_mode = {item["mode"]: item for item in summary.get("reports", [])}
    lines = readme.splitlines()

    for mode, label in MODE_LABELS.items():
        if mode not in by_mode:
            problems.append(f"证据摘要里缺 mode={mode}")
            continue
        row = next((line for line in lines if line.startswith(f"| {label} ")), None)
        if row is None:
            problems.append(f"README 评估表里找不到「{label}」这一行")
            continue

        cells = [cell.strip() for cell in row.strip("|").split("|")][1 : 1 + len(TABLE_COLUMNS)]
        if len(cells) != len(TABLE_COLUMNS):
            problems.append(f"{label} 这一行只有 {len(cells)} 个指标格（应有 {len(TABLE_COLUMNS)} 个）")
            continue
        metrics = by_mode[mode]["metrics"]
        for cell, (key, header) in zip(cells, TABLE_COLUMNS, strict=True):
            parsed = parse_cell(cell)
            if parsed is None:
                problems.append(f"{label} / {header}：无法解析单元格 {cell!r}")
                continue
            low, high = parsed
            expected = round(metrics[key] * 100, 2)
            if not (low - TOLERANCE <= expected <= high + TOLERANCE):
                shown = f"{low}%" if low == high else f"{low}–{high}%"
                problems.append(f"{label} / {header}：README 写 {shown}，证据报告是 {expected}%")
    return problems


def check_variance_ranges(readme: str, evidence_dir: pathlib.Path) -> list[str]:
    """`hybrid_rerank` 的区间必须恰好等于跨轮极差文件里的 min/max。"""
    problems: list[str] = []
    variance_file = evidence_dir / "rerank_variance.txt"
    if not variance_file.exists():
        return [f"缺跨轮极差文件：{variance_file}"]
    spans = {
        m["key"]: (float(m["lo"]) * 100, float(m["hi"]) * 100)
        for m in VARIANCE_LINE.finditer(variance_file.read_text("utf-8"))
    }

    row = next((line for line in readme.splitlines() if line.startswith("| 混合 + 重排 ")), None)
    if row is None:
        return ["README 找不到「混合 + 重排」行，无法核对区间来源"]
    cells = [cell.strip() for cell in row.strip("|").split("|")][1 : 1 + len(TABLE_COLUMNS)]
    if len(cells) != len(TABLE_COLUMNS):
        return [f"「混合 + 重排」行只有 {len(cells)} 个指标格（应有 {len(TABLE_COLUMNS)} 个）"]

    for cell, (key, header) in zip(cells, TABLE_COLUMNS, strict=True):
        parsed = parse_cell(cell)
        if parsed is None:
            problems.append(f"混合 + 重排 / {header}：无法解析单元格 {cell!r}")
            continue
        low, high = parsed
        if key not in spans:
            problems.append(f"跨轮极差文件里缺 {key}（README 给了区间就该有对应记录）")
            continue
        # 单值格子（R@5 跨轮极差为 0）不要求写成区间
        if low == high and abs(spans[key][0] - spans[key][1]) < TOLERANCE:
            continue
        exp_low, exp_high = round(spans[key][0], 2), round(spans[key][1], 2)
        if abs(low - exp_low) > TOLERANCE or abs(high - exp_high) > TOLERANCE:
            problems.append(f"混合 + 重排 / {header}：README 区间 {low}–{high}%，跨轮极差是 {exp_low}–{exp_high}%")
    return problems


def check_evidence_refs(readme: str, evidence_dir: pathlib.Path) -> list[str]:
    """README 引用的每个证据文件都必须真实存在。"""
    problems: list[str] = []
    refs = {m.group(1) for m in EVIDENCE_REF.finditer(readme)}
    if not refs:
        problems.append("README 里没有任何指向 docs/evidence/ 的来源标注")
    for ref in sorted(refs):
        if not (REPO_ROOT / ref).exists():
            problems.append(f"README 引用了不存在的证据文件：{ref}")
    return problems


def check_evidence_dir(evidence_dir: pathlib.Path) -> list[str]:
    """证据目录不许空，也不许只剩说明文件。"""
    if not evidence_dir.exists():
        return [f"证据目录不存在：{evidence_dir}"]
    files = [p for p in evidence_dir.iterdir() if p.is_file() and p.name != "README.md"]
    if len(files) < 5:
        return [f"证据目录只有 {len(files)} 个证据文件（<5），对账链不完整"]
    return []


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="README 数字 vs docs/evidence 对账")
    parser.add_argument("--readme", default=DEFAULT_README)
    parser.add_argument("--evidence", default=DEFAULT_EVIDENCE)
    args = parser.parse_args(argv)

    readme_path = _resolve(args.readme)
    evidence_dir = _resolve(args.evidence)
    if not readme_path.exists():
        print(f"[FAIL] 找不到 README：{readme_path}")
        return 1

    readme = readme_path.read_text("utf-8")
    summary_path = evidence_dir / "eval_reports_summary.json"
    if not summary_path.exists():
        print(f"[FAIL] 找不到评估摘要：{summary_path}\n       先跑 `python -m scripts.summarize_eval_reports`")
        return 1
    summary = json.loads(summary_path.read_text("utf-8"))

    problems = [
        *check_evidence_dir(evidence_dir),
        *check_metrics(readme, summary),
        *check_variance_ranges(readme, evidence_dir),
        *check_evidence_refs(readme, evidence_dir),
    ]

    if problems:
        print("[FAIL] README 与 docs/evidence 不一致：")
        for item in problems:
            print(f"  - {item}")
        print("\n正文数字必须来自 docs/evidence（见 docs/CONVENTIONS.md §4.6 三条硬规矩）。")
        return 1

    reports = summary.get("reports", [])
    print("[OK] README 与 docs/evidence 全部一致")
    print(f"     对账报告 {len(reports)} 份：" + ", ".join(f"{r['file']}({r['sha256_16']})" for r in reports))
    print(f"     指标格 {len(MODE_LABELS) * len(TABLE_COLUMNS)} 个全部覆盖；区间格子与跨轮极差一致；来源标注全部存在")
    return 0


if __name__ == "__main__":
    sys.exit(main())
