"""通道归因复算：验证「RRF 等权融合的结构性缺陷」这条核心结论。

产出（就是 `README.md`「结论二」里那些数字的原始来源）：

1. 从 `vector.json` / `hybrid.json` 找出 Recall@5 **回落**的查询；
2. 对每条查询、每个金标准，算出 `{vector 名次, BM25 名次, RRF 名次}` 三元组，
   分类为「双通道 / 仅向量 / 仅 BM25 / 两路均未召回」；
3. 汇总 40 条查询 Top5/Top10 的双通道占比。

**为什么不改 `rag/`**：这里只用与 `scripts/eval.py` **同一份向量 SQL** 和
`rag.fusion.reciprocal_rank_fusion` 复算，属于**只读归因**，不引入第二套实现。

用法::

    cd backend
    $env:TEMP='<仓库>\\.tmp'
    .venv\\Scripts\\python.exe -m scripts.channel_attribution --out ../docs/evidence/channel_attribution.txt

前置：`data/eval/reports/{vector,hybrid}.json` 已存在（`scripts.eval --mode all`），
且库里有向量索引（`scripts.build_index`）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
from typing import Any

import sqlalchemy as sa
import yaml

from infra.db import get_engine
from infra.embedding_client import build_embedding_client
from infra.tables import recipe_embeddings, recipes
from rag.corpus import CardCorpus, load_card_documents
from rag.fusion import DEFAULT_RRF_K, reciprocal_rank_fusion

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
POOL = 50
TOP_K = 10


def recall5(row: dict[str, Any]) -> float:
    top5 = set(row["top10"][:5])
    relevant = set(row["relevant"])
    return len(top5 & relevant) / len(relevant) if relevant else 0.0


def _resolve(candidate: str) -> pathlib.Path:
    """路径口径：默认值（`docs/evidence/...`）按**仓库根**解析；

    显式写成 `../...` 的（例如从 `backend/` 下跑时 `--out ../docs/...`）按**当前工作目录**解析。
    这样两种直觉都不会踩到 `REPO_ROOT / "../docs"` 越出仓库的坑。
    """
    path = pathlib.Path(candidate)
    if path.is_absolute():
        return path
    if candidate.startswith(".."):
        return path.resolve()
    return (REPO_ROOT / path).resolve()


def _classify(v_rank: int | None, b_rank: int | None) -> str:
    if v_rank and b_rank:
        return "双通道"
    if v_rank:
        return "仅向量"
    if b_rank:
        return "仅BM25"
    return "两路Top50均未召回"


async def run(out_path: pathlib.Path) -> str:
    queries = {
        item["id"]: item for item in yaml.safe_load((REPO_ROOT / "data" / "eval" / "queries.yaml").read_text("utf-8"))
    }
    report_dir = REPO_ROOT / "data" / "eval" / "reports"
    vector_report = json.loads((report_dir / "vector.json").read_text("utf-8"))
    hybrid_report = json.loads((report_dir / "hybrid.json").read_text("utf-8"))

    v_rows = {row["id"]: row for row in vector_report["per_query"]}
    h_rows = {row["id"]: row for row in hybrid_report["per_query"]}
    regressed = [qid for qid in v_rows if recall5(h_rows[qid]) < recall5(v_rows[qid])]

    engine = get_engine()
    embedder = build_embedding_client()
    lines: list[str] = []
    try:
        async with engine.connect() as conn:
            corpus = CardCorpus(await load_card_documents(conn))
            id_to_name = {
                str(row.id): row.name for row in (await conn.execute(sa.select(recipes.c.id, recipes.c.name))).all()
            }
        name_to_ids: dict[str, list[str]] = {}
        for rid, name in id_to_name.items():
            name_to_ids.setdefault(name, []).append(rid)

        stats = {"gold_total": 0, "dual": 0, "vector_only": 0, "bm25_only": 0, "neither": 0, "dual_head": 0}
        lines.append(f"Recall@5 回落查询：{len(regressed)} 条 → {regressed}")
        lines.append("")
        for qid in regressed:
            item = queries[qid]
            vector = (await embedder.embed([item["query"]]))[0]
            statement = (
                sa.select(recipes.c.id)
                .join(recipe_embeddings, recipe_embeddings.c.recipe_id == recipes.c.id)
                .order_by(recipe_embeddings.c.embedding.cosine_distance(vector))
                .limit(POOL)
            )
            async with engine.connect() as conn:
                vector_ids = [str(row.id) for row in (await conn.execute(statement)).all()]
            bm25_ids = [doc_id for doc_id, _ in corpus.search(item["query"], POOL)]
            fused = reciprocal_rank_fusion({"vector": vector_ids, "bm25": bm25_ids}, k=DEFAULT_RRF_K, top_n=POOL)
            fused_ids = [rid for rid, _, _ in fused]
            dual = set(vector_ids) & set(bm25_ids)
            stats["dual_head"] += sum(1 for rid in fused_ids[:TOP_K] if rid in dual)
            lines.append(f"{qid} [{item['category']}] {item['query']}")
            lines.append(
                f"    R@5 vector={recall5(v_rows[qid]):.3f} → hybrid={recall5(h_rows[qid]):.3f}；双通道交集={len(dual)}"
            )
            for name in item["relevant"]:
                stats["gold_total"] += 1
                ids = name_to_ids.get(name, [])
                in_fused = [rid for rid in ids if rid in fused_ids]
                v_rank = next((vector_ids.index(rid) + 1 for rid in ids if rid in vector_ids), None)
                b_rank = next((bm25_ids.index(rid) + 1 for rid in ids if rid in bm25_ids), None)
                rrf_rank = next((fused_ids.index(rid) + 1 for rid in in_fused), None)
                kind = _classify(v_rank, b_rank)
                stats[
                    "dual"
                    if kind == "双通道"
                    else "vector_only"
                    if kind == "仅向量"
                    else "bm25_only"
                    if kind == "仅BM25"
                    else "neither"
                ] += 1
                lines.append(f"    gold {name}: {kind}  vector_rank={v_rank}  bm25_rank={b_rank}  rrf_rank={rrf_rank}")
        lines.append("")
        lines.append(f"== 汇总（{len(regressed)} 条回落查询） ==")
        lines.append(
            f"  gold 项数={stats['gold_total']}：双通道={stats['dual']} 仅向量={stats['vector_only']} "
            f"仅BM25={stats['bm25_only']} 两路均未召回={stats['neither']}"
        )
        lines.append(f"  Top10 中双通道共识项={stats['dual_head']}/{TOP_K * len(regressed)}")
        lines.append("")
        lines.append("== 40 条全量头部构成（来自 hybrid.json 的 channel_sources） ==")
        d5 = d10 = b10 = v10 = 0
        for row in hybrid_report["per_query"]:
            src = {entry["name"]: entry["sources"] for entry in row["channel_sources"]}
            for rank, nm in enumerate(row["top10"], start=1):
                channels = src.get(nm, [])
                if len(channels) > 1:
                    d10 += 1
                    d5 += rank <= 5
                elif channels == ["bm25"]:
                    b10 += 1
                else:
                    v10 += 1
        lines.append(
            f"  Top5 双通道={d5}/200 ({d5 / 2:.1f}%)；Top10 双通道={d10}/400 ({d10 / 4:.1f}%) "
            f"BM25-only={b10} 向量-only={v10}"
        )
        lines.append("")
        lines.append(f"== 机制（k={DEFAULT_RRF_K}，池={POOL}） ==")
        lines.append(
            f"  单通道项上界 1/(k+1)={1 / (DEFAULT_RRF_K + 1):.6f} < "
            f"双通道项下界 2/(k+{POOL})={2 / (DEFAULT_RRF_K + POOL):.6f}"
        )
    finally:
        closer = getattr(embedder, "aclose", None)
        if closer is not None:
            await closer()
        await engine.dispose()

    text = "\n".join(lines)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text + "\n", encoding="utf-8")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description="RRF 通道归因复算")
    parser.add_argument("--out", default="docs/evidence/channel_attribution.txt", help="输出路径")
    args = parser.parse_args()
    text = asyncio.run(run(_resolve(args.out)))
    print(text)
    print(f"[留底] {_resolve(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
