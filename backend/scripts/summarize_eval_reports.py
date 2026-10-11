"""把 `data/eval/reports/*.json` 的关键字段摘成一份**可入库的摘要**。

为什么需要它：完整报告每份 50–360 KB（4 份合计 ~920 KB），且 `data/eval/reports/` 是
gitignore 的**可重建产物**，不进仓库。于是「README 里那些数字从哪来」就缺少留痕。
这份摘要只保留**指标 / 延迟 / 归因 / 文件哈希**，几十 KB 以内，入库后可以直接对账：

    重跑 `--mode all` + `--mode weight` → 与本摘要逐字段比对，即可判断是否复现。

用法::

    cd backend
    .venv\\Scripts\\python.exe -m scripts.summarize_eval_reports --out ../docs/evidence/eval_reports_summary.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

# 与 scripts/eval.py 保持同一套路径口径：相对路径按仓库根解析，
# 否则从 backend/ 下跑会找不到 data/eval/reports。
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

METRIC_KEYS = ("recall@5", "recall@10", "mrr@10", "ndcg@5")


def _round_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    return {key: round(float(metrics[key]), 6) for key in METRIC_KEYS if key in metrics}


def summarize_report(path: pathlib.Path) -> dict[str, Any]:
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    summary: dict[str, Any] = {
        "file": path.name,
        "sha256_16": hashlib.sha256(raw).hexdigest()[:16],
        "bytes": len(raw),
        "mode": data.get("mode"),
        "evaluated_at": data.get("evaluated_at"),
        "query_count": data.get("query_count"),
        "pool_size": data.get("pool_size"),
    }

    if "metrics" in data:
        summary["metrics"] = _round_metrics(data["metrics"])
        summary["latency_ms"] = {key: round(float(value), 1) for key, value in data["latency_ms"].items()}
        summary["by_category"] = {
            category: _round_metrics(values) for category, values in sorted(data.get("by_category", {}).items())
        }
        summary["provider_stats"] = data.get("provider_stats")
        return summary

    # ablation_weight.json 是多配置结构
    summary["rrf_k"] = data.get("rrf_k")
    summary["latency_note"] = data.get("latency_note")
    summary["search_latency_ms"] = data.get("search_latency_ms")
    summary["provider_stats"] = data.get("provider_stats")
    configs: list[dict[str, Any]] = []
    for config in data.get("configs", []):
        entry: dict[str, Any] = {
            "name": config.get("name"),
            "note": config.get("note"),
            "w_vector": config.get("w_vector"),
            "w_bm25": config.get("w_bm25"),
            "per_channel_top": config.get("per_channel_top"),
            "metrics": _round_metrics(config.get("metrics", {})),
            "channel_mix": config.get("channel_mix"),
        }
        diagnostics = config.get("diagnostics")
        if diagnostics is not None:
            entry["diagnostics"] = diagnostics
        configs.append(entry)
    summary["configs"] = configs
    return summary


def _resolve(candidate: str) -> pathlib.Path:
    """相对路径按仓库根解析（与 `scripts/eval.py` 的 `_resolve` 同口径）。"""
    path = pathlib.Path(candidate)
    return path if path.is_absolute() else (REPO_ROOT / path)


def main() -> int:
    parser = argparse.ArgumentParser(description="摘要化评估报告（用于入库留痕）")
    parser.add_argument("--reports-dir", default="data/eval/reports", help="报告目录（相对路径按仓库根解析）")
    parser.add_argument("--out", default="docs/evidence/eval_reports_summary.json", help="输出路径")
    args = parser.parse_args()

    reports_dir = _resolve(args.reports_dir)
    files = sorted(reports_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"没有找到报告：{reports_dir}（请先跑 scripts.eval --mode all / --mode weight）")

    payload = {"reports_dir": str(reports_dir), "count": len(files), "reports": [summarize_report(f) for f in files]}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    target = _resolve(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text + "\n", encoding="utf-8")
    print(f"[摘要] {len(files)} 份报告 → {target}（{len(text)} 字节）")
    for report in payload["reports"]:
        if "metrics" in report:
            metrics = report["metrics"]
            print(
                f"  {report['file']:<24} R@5 {metrics['recall@5']:.4f}  "
                f"R@10 {metrics['recall@10']:.4f}  MRR {metrics['mrr@10']:.4f}  nDCG {metrics['ndcg@5']:.4f}"
            )
        else:
            print(f"  {report['file']:<24} {len(report.get('configs', []))} 档权重配置")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
