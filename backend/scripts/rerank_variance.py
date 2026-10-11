"""量化 `hybrid_rerank` 的**跑间抖动**：同一语料、同一脚本连跑多次，指标能差多少。

为什么必须量化它：README 里 `hybrid_rerank` 的 R@10 写成区间（77.50%–78.33%），
若不给原始证据，读的人无法判断这是「抖动」还是「我挑了个好看的数」。

**根因**：远端 bge-reranker 对同一输入的服务端打分**并非逐位确定**，Top10 的名次会被微调。
`vector` / `hybrid` 没有这个非确定性组件，是同输入同输出。

用法::

    cd backend
    $env:TEMP='<仓库>\\.tmp'
    .venv\\Scripts\\python.exe -m scripts.rerank_variance \\
        --runs data/eval/reports/hybrid_rerank.json .tmp/rerank_run2.json .tmp/rerank_run3.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
METRIC_KEYS = ("recall@5", "recall@10", "mrr@10", "ndcg@5")


def _resolve(candidate: str) -> pathlib.Path:
    path = pathlib.Path(candidate)
    if path.is_absolute():
        return path
    if candidate.startswith(".."):
        return path.resolve()
    return (REPO_ROOT / path).resolve()


def load(candidate: str) -> dict[str, Any]:
    path = _resolve(candidate)
    if not path.exists():
        raise SystemExit(f"缺报告：{path}（先用 scripts.eval --mode hybrid_rerank --output <path> 生成）")
    return json.loads(path.read_text("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="量化重排跑间抖动")
    parser.add_argument("--runs", nargs="+", required=True, help="2 份以上 hybrid_rerank 报告路径")
    parser.add_argument("--out", default="docs/evidence/rerank_variance.txt", help="输出路径")
    args = parser.parse_args()

    if len(args.runs) < 2:
        raise SystemExit("至少给 2 份报告才能算抖动")

    reports = [(label, load(label)) for label in args.runs]
    lines: list[str] = []
    lines.append("== 各次运行的指标 ==")
    for label, report in reports:
        metrics = {key: round(float(report["metrics"][key]), 4) for key in METRIC_KEYS}
        lines.append(f"  {label}  evaluated_at={report.get('evaluated_at')}")
        lines.append(f"    {json.dumps(metrics, ensure_ascii=False)}")

    lines.append("")
    lines.append(f"== 跨 {len(reports)} 次运行的极差（这是 README 里 R@10 写成区间的原因） ==")
    for key in METRIC_KEYS:
        values = [float(report["metrics"][key]) for _, report in reports]
        lines.append(f"  {key}: min={min(values):.4f} max={max(values):.4f} 极差={max(values) - min(values):.4f}")

    # 逐查询比对：哪些查询的 Top10 顺序变了、指标有没有因此改变
    base_label, base = reports[0]
    base_rows = {row["id"]: row for row in base["per_query"]}
    lines.append("")
    lines.append(f"== 与 `{base_label}` 的逐查询比对 ==")
    for label, report in reports[1:]:
        rows = {row["id"]: row for row in report["per_query"]}
        changed = [qid for qid in base_rows if base_rows[qid]["top10"] != rows[qid]["top10"]]
        lines.append(f"  vs {label}：Top10 顺序不一致 {len(changed)}/{len(base_rows)} 条")
        for qid in changed:
            a, b = base_rows[qid], rows[qid]
            metrics_a = {key: round(float(a["metrics"][key]), 3) for key in METRIC_KEYS}
            metrics_b = {key: round(float(b["metrics"][key]), 3) for key in METRIC_KEYS}
            lines.append(f"    {qid} [{a['category']}] {a['query']}")
            lines.append(f"      A: {a['top10'][:5]}")
            lines.append(f"      B: {b['top10'][:5]}")
            if metrics_a != metrics_b:
                lines.append(f"      **指标变了** A={json.dumps(metrics_a, ensure_ascii=False)}")
                lines.append(f"                    B={json.dumps(metrics_b, ensure_ascii=False)}")

    lines.append("")
    lines.append("== 怎么用这份数字 ==")
    lines.append("  1. README 里 hybrid_rerank 的 R@10 必须写成区间，不能给三位小数的单一值；")
    lines.append(
        "  2. 任何一次跑的 `provider_stats.degraded_calls != 0` 都必须丢弃重跑（走了本地兜底/降级回 RRF，数字不可比）；"
    )
    lines.append("  3. `vector` / `hybrid` 不存在这个抖动，可复现到小数点，两者不要混在一句话里说。")

    text = "\n".join(lines)
    out = _resolve(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"[留底] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
