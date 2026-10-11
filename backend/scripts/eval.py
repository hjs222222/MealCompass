"""检索离线评估（C2 / task-3）：纯向量 vs 混合 RRF vs 混合+重排 的三组消融实验。

用法（在 ``backend/`` 下）::

    .venv\\Scripts\\python.exe -m scripts.eval --validate-only
    .venv\\Scripts\\python.exe -m scripts.eval --mode vector        --output data/eval/reports/vector.json
    .venv\\Scripts\\python.exe -m scripts.eval --mode hybrid        --output data/eval/reports/hybrid.json
    .venv\\Scripts\\python.exe -m scripts.eval --mode hybrid_rerank --output data/eval/reports/hybrid_rerank.json
    .venv\\Scripts\\python.exe -m scripts.eval --mode all --weight-ablation   # 三组 + 权重敏感性，全部落盘
    .venv\\Scripts\\python.exe -m scripts.eval --mode weight                  # 只跑权重敏感性

设计要点（面试可解释性）:

1. **候选池口径统一**：三组都取 **Top50** 作为候选池，指标只在池子的前 5 / 前 10 上截断计算。
   纯向量组的池就是「向量余弦 Top50」，混合组的池是「向量 Top50 ∪ BM25 Top50 经 RRF 融合后的 Top50」，
   重排组的池与混合组完全相同、只是顺序被 bge-reranker 重排。候选池一致，三组数字才可比。
2. **纯向量不走 ``rag/`` 的融合**：`HybridRetriever` 永远融合两路，所以 ``--mode vector`` 由本脚本
   自己发一条 ``order_by(embedding.cosine_distance(v)).limit(50)`` 的查询（评估脚本自身逻辑，不改 ``rag/``）。
3. **指标是纯函数**（本模块顶层，零 IO），被 ``tests/unit/test_eval_metrics.py`` 覆盖。
4. **全部真实调用**：真连本地 PG + 真 SiliconFlow（embedding / rerank）；每条查询单独计时。
   计时前对每条通道各预热一次（连接池 / HTTP 建连只发生一次），否则单条 600ms+ 的冷启动会把 P95 带偏；
   `latency_ms` 因此是**热路径**的端到端耗时（embedding 远程调用 + PG 查询 + 融合/重排）。
5. **不编数字**：embedding / rerank 若走了本地兜底（降级）会如实写进 JSON 的 ``provider_stats``；
   ``provider_stats`` 是**进程累计值**，跑多组时是累加数（真调用证据，不是单组计数）。
6. **权重敏感性消融**（``--weight-ablation`` / ``--mode weight``）：``rag.fusion`` 没有权重参数，
   而 ``rag/**`` 不在本任务可改范围内，所以加权 RRF 用本脚本的本地实现比较
   ``w_bm25 ∈ {0, 0.25, 0.5, 1.0}`` 与「只取各通道 Top10」两档，结果写 ``ablation_weight.json``。
7. 相对路径一律相对**仓库根**解析（``data/eval/**`` 在仓库根，不在 ``backend/`` 下）。

指标定义（二进制相关度，即「relevant 里出现过就算命中」）:

- ``Recall@k = |relevant ∩ retrieved[:k]| / |relevant|``
- ``MRR@k  = 1 / rank(第一个命中项)，未命中为 0``
- ``nDCG@k = DCG@k / IDCG@k``，其中 ``DCG@k = Σ hit_i / log2(i + 1)``（i 为 1 基位置），
  ``IDCG@k`` 是理想排序（命中项全部排最前）的 DCG。
- 无金标准（``relevant`` 为空）时四个指标都返回 ``0.0``：这种查询无法评测，不应进入任何平均。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from collections.abc import Collection, Iterable, Sequence
from datetime import UTC, datetime
from math import log2
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlalchemy as sa  # noqa: E402
import yaml  # noqa: E402

from infra.db import get_engine  # noqa: E402
from infra.embedding_client import build_embedding_client  # noqa: E402
from infra.observability import ObservationType, SpanName, flush, traced  # noqa: E402
from infra.rerank_client import build_rerank_client  # noqa: E402
from infra.tables import recipe_embeddings, recipes  # noqa: E402
from rag.corpus import CardCorpus, load_card_documents  # noqa: E402
from rag.fusion import DEFAULT_RRF_K  # noqa: E402
from rag.retriever import HybridRetriever  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUERIES_PATH = REPO_ROOT / "data" / "eval" / "queries.yaml"
DEFAULT_REPORT_DIR = REPO_ROOT / "data" / "eval" / "reports"

# 三组共用的候选池大小；指标在其前 5 / 前 10 上截断。
POOL_SIZE = 50
TOP_K_SMALL = 5
TOP_K_LARGE = 10

MODES = ("vector", "hybrid", "hybrid_rerank")
MODE_LABELS = {
    "vector": "纯向量（bge-m3 余弦 Top50）",
    "hybrid": "混合 RRF（向量 Top50 + BM25 Top50）",
    "hybrid_rerank": "混合 RRF + bge-reranker-v2-m3 重排",
}
METRIC_KEYS = ("recall@5", "recall@10", "mrr@10", "ndcg@5")


# --------------------------------------------------------------------------- 纯函数指标


def unique_preserving_order(items: Iterable[str]) -> list[str]:
    """按首次出现顺序去重。

    库里存在同名菜谱（如 ``陈皮排骨汤`` 有两条 ``recipes`` 记录），而金标准是按**菜名**
    标注的；不去重会让同一个菜名在第 1、第 3 名各命中一次，虚高 nDCG。
    """
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _top(items: Sequence[str], k: int) -> list[str]:
    if k <= 0:
        return []
    return list(items[:k])


def recall_at_k(retrieved: Sequence[str], relevant: Collection[str], k: int) -> float:
    """Recall@k：命中金标准的比例。``relevant`` 为空时返回 0.0（无金标准的查询不参与平均）。"""
    gold = set(relevant)
    if not gold:
        return 0.0
    hits = len(gold.intersection(_top(retrieved, k)))
    return hits / len(gold)


def hit_rank(retrieved: Sequence[str], relevant: Collection[str], k: int) -> int | None:
    """第一个命中项的 1 基名次；未命中返回 None。用于 per_query 记录与 MRR。"""
    gold = set(relevant)
    if not gold:
        return None
    for position, name in enumerate(_top(retrieved, k), start=1):
        if name in gold:
            return position
    return None


def mrr_at_k(retrieved: Sequence[str], relevant: Collection[str], k: int) -> float:
    """MRR@k：第一个命中项名次的倒数；未命中为 0.0。"""
    rank = hit_rank(retrieved, relevant, k)
    return 0.0 if rank is None else 1.0 / rank


def ndcg_at_k(retrieved: Sequence[str], relevant: Collection[str], k: int) -> float:
    """nDCG@k（二进制相关度）：DCG@k / IDCG@k；``relevant`` 为空时返回 0.0。"""
    gold = set(relevant)
    if not gold:
        return 0.0
    positions = _top(retrieved, k)
    if not positions:
        return 0.0
    dcg = sum(1.0 / log2(position + 1) for position, name in enumerate(positions, start=1) if name in gold)
    ideal_positions = min(len(gold), len(positions))
    idcg = sum(1.0 / log2(position + 1) for position in range(1, ideal_positions + 1))
    return 0.0 if idcg == 0.0 else dcg / idcg


def evaluate_query(retrieved: Sequence[str], relevant: Collection[str]) -> dict[str, float]:
    """对单条查询算四个指标（纯函数，便于单测与复用）。"""
    return {
        "recall@5": recall_at_k(retrieved, relevant, TOP_K_SMALL),
        "recall@10": recall_at_k(retrieved, relevant, TOP_K_LARGE),
        "mrr@10": mrr_at_k(retrieved, relevant, TOP_K_LARGE),
        "ndcg@5": ndcg_at_k(retrieved, relevant, TOP_K_SMALL),
    }


def aggregate_metrics(per_query: Sequence[dict[str, Any]]) -> dict[str, float]:
    """对每条查询的指标取宏平均（先按查询平均，再按指标平均——不按金标准条数加权）。"""
    if not per_query:
        return dict.fromkeys(METRIC_KEYS, 0.0)
    return {key: statistics.fmean(row["metrics"][key] for row in per_query) for key in METRIC_KEYS}


def aggregate_by_category(per_query: Sequence[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """按查询类别聚合指标，便于定位「哪一类查询拉低了整体」。"""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in per_query:
        grouped.setdefault(str(row.get("category", "")), []).append(row)
    return {category: aggregate_metrics(rows) for category, rows in grouped.items()}


def latency_stats(latencies_ms: Sequence[float]) -> dict[str, float]:
    """延迟统计：中位数 / P95 / 均值 / 最小 / 最大（P95 用最近秩法，小样本下更稳）。"""
    if not latencies_ms:
        return {"median": 0.0, "p95": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0}
    ordered = sorted(latencies_ms)
    index = min(len(ordered) - 1, max(0, int(round(0.95 * (len(ordered) - 1)))))
    return {
        "median": statistics.median(ordered),
        "p95": ordered[index],
        "mean": statistics.fmean(ordered),
        "min": ordered[0],
        "max": ordered[-1],
    }


# --------------------------------------------------------------------------- 评估集加载与校验


def load_queries(path: Path) -> list[dict[str, Any]]:
    """读评估集 YAML 并做结构性校验（不连库：菜名是否真实存在由 DB 校验负责）。"""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"评估集必须是 YAML 列表：{path}")
    queries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 条不是映射：{item!r}")
        query_id = str(item.get("id", "")).strip()
        text = str(item.get("query", "")).strip()
        relevant = [str(name).strip() for name in (item.get("relevant") or []) if str(name).strip()]
        if not query_id or not text:
            raise ValueError(f"第 {index} 条缺 id / query：{item!r}")
        if query_id in seen_ids:
            raise ValueError(f"重复的查询 id：{query_id}")
        if not relevant:
            raise ValueError(f"{query_id} 至少要有 1 个 relevant")
        if len(relevant) > 3:
            raise ValueError(f"{query_id} 的 relevant 超过 3 个：{relevant}")
        seen_ids.add(query_id)
        queries.append(
            {
                "id": query_id,
                "category": str(item.get("category", "")).strip(),
                "query": text,
                "relevant": relevant,
                "notes": str(item.get("notes", "")).strip(),
            }
        )
    return queries


async def fetch_recipe_names(conn: Any) -> list[str]:
    rows = (await conn.execute(sa.select(recipes.c.name).order_by(recipes.c.name))).all()
    return [row.name for row in rows]


async def fetch_recipe_id_names(conn: Any) -> dict[str, str]:
    """``recipe_id -> name``：加权消融在 ID 空间融合后映射回菜名算指标。"""
    rows = (await conn.execute(sa.select(recipes.c.id, recipes.c.name))).all()
    return {str(row.id): row.name for row in rows}


def validate_relevant(queries: Sequence[dict[str, Any]], known_names: Collection[str]) -> list[str]:
    """校验每条 relevant 都是库里真实菜名；返回问题列表（空列表 = 全部通过）。"""
    known = set(known_names)
    problems: list[str] = []
    for item in queries:
        for name in item["relevant"]:
            if name not in known:
                problems.append(f"{item['id']} 的 relevant 不存在于 recipes.name：{name}")
    return problems


# --------------------------------------------------------------------------- 三条检索路径


async def vector_search(engine: Any, embedder: Any, query: str, top_n: int) -> list[str]:
    """纯向量基线：直接按 pgvector 余弦距离取 Top-N（不融合、不重排）。"""
    query_vector = (await embedder.embed([query]))[0]
    statement = (
        sa.select(recipes.c.name, recipe_embeddings.c.embedding.cosine_distance(query_vector).label("distance"))
        .join(recipe_embeddings, recipe_embeddings.c.recipe_id == recipes.c.id)
        .order_by("distance")
        .limit(top_n)
    )
    async with engine.connect() as conn:
        rows = (await conn.execute(statement)).all()
    return [row.name for row in rows]


async def vector_search_ranked(engine: Any, query_vector: Sequence[float], top_n: int) -> list[str]:
    """按已算好的查询向量取向量 Top-N 的 **recipe_id**（加权消融里复用同一份向量，省一次远程调用）。

    返回 ID 而不是菜名，是为了与 ``HybridRetriever`` 完全同构（RRF 在 ID 空间融合，
    库里 ``陈皮排骨汤`` 这类同名菜谱是两条不同 ID）。菜名只在算指标时映射。
    """
    statement = (
        sa.select(recipes.c.id)
        .join(recipe_embeddings, recipe_embeddings.c.recipe_id == recipes.c.id)
        .order_by(recipe_embeddings.c.embedding.cosine_distance(query_vector))
        .limit(top_n)
    )
    async with engine.connect() as conn:
        rows = (await conn.execute(statement)).all()
    return [str(row.id) for row in rows]


def bm25_ranked_ids(corpus: CardCorpus, query: str, top_n: int) -> list[str]:
    """BM25 通道的 recipe_id 排名列表（``CardCorpus.search`` 是唯一入口，不改 ``rag/``）。"""
    return [doc_id for doc_id, _ in corpus.search(query, top_n)]


def weighted_rrf(
    ranked_lists: Sequence[tuple[str, float, Sequence[str]]],
    *,
    k: int = DEFAULT_RRF_K,
    top_n: int | None = None,
) -> list[tuple[str, float, list[str]]]:
    """加权 RRF：``score(d) = Σ w_channel / (k + rank_channel(d))``。

    这是**评估脚本自己的本地实现**（用于权重敏感性消融）：``rag.fusion`` 没有权重参数，
    而 ``rag/**`` 不在本任务可改范围内。语义与 ``rag.fusion.reciprocal_rank_fusion`` 一致：
    同一路内重复 id 只计第一次、同分按首次出现位置稳定排序、各通道只贡献排名不贡献原始分。
    ``w=0`` 等价于「不接这条通道」；输入是 ``[(通道名, 权重, 该通道的 id 排名列表)]``。
    """
    scores: dict[str, float] = {}
    channels: dict[str, list[str]] = {}
    first_seen: dict[str, tuple[int, int]] = {}
    for channel_index, (channel_name, weight, ranked_ids) in enumerate(ranked_lists):
        if weight == 0:
            continue
        seen_in_channel: set[str] = set()
        for rank, recipe_id in enumerate(ranked_ids, start=1):
            if recipe_id in seen_in_channel:
                continue
            seen_in_channel.add(recipe_id)
            scores[recipe_id] = scores.get(recipe_id, 0.0) + weight / (k + rank)
            channels.setdefault(recipe_id, []).append(channel_name)
            first_seen.setdefault(recipe_id, (channel_index, rank))
    ordered = sorted(scores, key=lambda recipe_id: (-scores[recipe_id], first_seen[recipe_id]))
    if top_n is not None:
        ordered = ordered[:top_n]
    return [(recipe_id, scores[recipe_id], channels[recipe_id]) for recipe_id in ordered]


async def run_mode(
    mode: str,
    queries: Sequence[dict[str, Any]],
    *,
    engine: Any,
    embedder: Any,
    corpus: CardCorpus,
    reranker: Any | None,
    pool_size: int = POOL_SIZE,
) -> dict[str, Any]:
    """跑一组模式，返回报告 dict（含 per_query 命中位置与延迟）。"""
    retriever = None
    if mode in {"hybrid", "hybrid_rerank"}:
        retriever = HybridRetriever(
            embedder=embedder,
            corpus=corpus,
            reranker=reranker if mode == "hybrid_rerank" else None,
            engine=engine,
        )

    per_query: list[dict[str, Any]] = []
    with traced(
        SpanName.EVAL_RETRIEVAL,
        as_type=ObservationType.EVALUATOR,
        input={"mode": mode, "query_count": len(queries), "pool_size": pool_size},
    ) as run_span:
        # 冷启动成本（DB 连接池 / HTTP 建连）只在第 1 条查询上出现，先各预热一次再计时，
        # 否则单条 600ms+ 的建连开销会把 P95 与均值带偏。
        warmup_query = queries[0]["query"] if queries else "预热"
        if mode == "vector":
            await vector_search(engine, embedder, warmup_query, 1)
        else:
            assert retriever is not None  # 分支保证非空，同时供类型收窄
            await retriever.search(warmup_query, top_k=1)

        for item in queries:
            started = time.perf_counter()
            with traced(
                SpanName.EVAL_RETRIEVAL,
                as_type=ObservationType.EVALUATOR,
                input={"query": item["query"], "relevant": item["relevant"], "mode": mode},
            ) as query_span:
                if mode == "vector":
                    pool = await vector_search(engine, embedder, item["query"], pool_size)
                    evidence = f"pgvector 余弦 Top{pool_size}（recipe_embeddings.embedding）"
                    channel_sources: list[dict[str, Any]] = []
                else:
                    assert retriever is not None  # 分支保证非空，同时供类型收窄
                    candidates = await retriever.search(item["query"], top_k=pool_size)
                    pool = [candidate.name for candidate in candidates]
                    evidence = f"HybridRetriever.search(top_k={pool_size})" + (
                        " + bge-reranker-v2-m3 重排" if mode == "hybrid_rerank" else "（RRF k=60，无重排）"
                    )
                    # 免费证据：候选自带命中通道（vector/bm25）。RRF 阶段双通道共识项分数必高于单通道项，
                    # 这份 sources 让「头部是否被共识项占满」可直接从报告里看出来。
                    channel_sources = [
                        {"name": candidate.name, "sources": list(candidate.sources), "score": round(candidate.score, 6)}
                        for candidate in candidates
                    ]
                elapsed_ms = (time.perf_counter() - started) * 1000
                ranked = unique_preserving_order(pool)
                metrics = evaluate_query(ranked, item["relevant"])
                rank = hit_rank(ranked, item["relevant"], TOP_K_LARGE)
                positions = {
                    name: (ranked.index(name) + 1 if name in ranked[:TOP_K_LARGE] else None)
                    for name in item["relevant"]
                }
                # 去重前的原始前 10（`rag` 层真实返回顺序）留作证据，便于解释同名菜谱的影响。
                retrieved_top10 = pool[:TOP_K_LARGE]
                record = {
                    "id": item["id"],
                    "category": item["category"],
                    "query": item["query"],
                    "relevant": item["relevant"],
                    "hit_rank": rank,
                    "relevant_positions": positions,
                    "retrieved_count": len(pool),
                    "top10": ranked[:TOP_K_LARGE],
                    "evidence_top10": retrieved_top10,
                    "evidence_source": evidence,
                    "channel_sources": channel_sources,
                    "latency_ms": round(elapsed_ms, 1),
                    "metrics": metrics,
                }
                per_query.append(record)
                query_span.update(
                    output={
                        "hit_rank": rank,
                        "relevant_positions": positions,
                        "top10": ranked[:TOP_K_LARGE],
                        "evidence_top10": retrieved_top10,
                        "latency_ms": round(elapsed_ms, 1),
                        "metrics": metrics,
                    }
                )

        metrics = aggregate_metrics(per_query)
        per_query_latency = [float(row["latency_ms"]) for row in per_query]
        latency = latency_stats(per_query_latency)
        by_category = aggregate_by_category(per_query)
        run_span.update(output={"metrics": metrics, "latency_ms": latency, "by_category": by_category})

    report = {
        "mode": mode,
        "mode_label": MODE_LABELS[mode],
        "evaluated_at": datetime.now(UTC).isoformat(),
        "query_count": len(per_query),
        "pool_size": pool_size,
        "metrics": metrics,
        "by_category": by_category,
        "latency_ms": latency,
        "per_query": per_query,
    }
    return report


# --------------------------------------------------------------------------- 加权消融


def weight_configs(pool_size: int) -> list[dict[str, Any]]:
    """权重敏感性消融的配置表。

    - ``w_bm25=0`` 等价纯向量（在**同一个候选池构造流程**里跑，可与 RRF 组直接对比）。
    - ``w_bm25=1.0`` 是现状（等权 RRF，即 ``HybridRetriever`` 的行为）。
    - ``top10`` 那档：两路各只取 Top10 再等权 RRF，验证「BM25 尾部噪声」假设。
    """
    return [
        {"name": "w_bm25=0.0", "w_vector": 1.0, "w_bm25": 0.0, "per_channel_top": pool_size, "note": "退化为纯向量"},
        {"name": "w_bm25=0.25", "w_vector": 1.0, "w_bm25": 0.25, "per_channel_top": pool_size, "note": "弱化 BM25"},
        {"name": "w_bm25=0.5", "w_vector": 1.0, "w_bm25": 0.5, "per_channel_top": pool_size, "note": "半权 BM25"},
        {"name": "w_bm25=1.0", "w_vector": 1.0, "w_bm25": 1.0, "per_channel_top": pool_size, "note": "现状：等权 RRF"},
        {
            "name": "w_bm25=0.25+top10",
            "w_vector": 1.0,
            "w_bm25": 0.25,
            "per_channel_top": 10,
            "note": "弱化 BM25 且只取各通道 Top10（截断尾部噪声）",
        },
        {
            "name": "depth_normalized_top10",
            "w_vector": 1.0,
            "w_bm25": 1.0,
            "per_channel_top": 10,
            "note": "等权但两路都只取 Top10（按召回深度归一）",
        },
    ]


async def run_weight_ablation(
    queries: Sequence[dict[str, Any]],
    *,
    engine: Any,
    embedder: Any,
    corpus: CardCorpus,
    id_to_name: dict[str, str],
    pool_size: int = POOL_SIZE,
) -> dict[str, Any]:
    """对每条查询只算一次「向量 Top50 + BM25 Top50」，然后在本地做加权 RRF 与指标。

    只花 40 次 embedding 远程调用（与单组模式相同），不额外打 SiliconFlow。
    RRF 在 recipe_id 空间融合（与 ``HybridRetriever`` 同构），指标再映射成菜名。
    """
    configs = weight_configs(pool_size)
    prepared: list[dict[str, Any]] = []
    with traced(
        SpanName.EVAL_RETRIEVAL,
        as_type=ObservationType.EVALUATOR,
        input={"mode": "weight_ablation", "query_count": len(queries), "pool_size": pool_size},
    ) as run_span:
        for item in queries:
            started = time.perf_counter()
            query_vector = (await embedder.embed([item["query"]]))[0]
            vector_ids = await vector_search_ranked(engine, query_vector, pool_size)
            bm25_ids = bm25_ranked_ids(corpus, item["query"], pool_size)
            elapsed_ms = (time.perf_counter() - started) * 1000
            prepared.append(
                {
                    "item": item,
                    "vector_ids": vector_ids,
                    "bm25_ids": bm25_ids,
                    "latency_ms": round(elapsed_ms, 1),
                }
            )

        rows: list[dict[str, Any]] = []
        for config in configs:
            per_query: list[dict[str, Any]] = []
            dual_in_top5 = 0
            dual_in_top10 = 0
            gold_dual = 0
            gold_single = 0
            gold_not_recalled = 0
            for entry in prepared:
                item = entry["item"]
                per_channel_top = config["per_channel_top"]
                vector_slice = entry["vector_ids"][:per_channel_top]
                bm25_slice = entry["bm25_ids"][:per_channel_top]
                fused = weighted_rrf(
                    [
                        ("vector", config["w_vector"], vector_slice),
                        ("bm25", config["w_bm25"], bm25_slice),
                    ],
                    k=DEFAULT_RRF_K,
                    top_n=pool_size,
                )
                # 双通道共识 = 同时出现在两路 Top-N 的 id；用于量化"共识项挤占头部"的机制
                dual_ids = set(vector_slice) & set(bm25_slice)
                fused_ids = [recipe_id for recipe_id, _, _ in fused]
                dual_in_top5 += sum(1 for recipe_id in fused_ids[:TOP_K_SMALL] if recipe_id in dual_ids)
                dual_in_top10 += sum(1 for recipe_id in fused_ids[:TOP_K_LARGE] if recipe_id in dual_ids)
                names = [id_to_name.get(recipe_id, "") for recipe_id in fused_ids]
                ranked = unique_preserving_order(names)
                rank = hit_rank(ranked, item["relevant"], TOP_K_LARGE)
                # gold 的通道归属：双通道 / 单通道 / 两路 Top-N 都没召回
                gold_names = set(item["relevant"])
                vector_names_set = {id_to_name.get(rid, "") for rid in vector_slice}
                bm25_names_set = {id_to_name.get(rid, "") for rid in bm25_slice}
                for name in gold_names:
                    in_vector = name in vector_names_set
                    in_bm25 = name in bm25_names_set
                    if in_vector and in_bm25:
                        gold_dual += 1
                    elif in_vector or in_bm25:
                        gold_single += 1
                    else:
                        gold_not_recalled += 1
                per_query.append(
                    {
                        "id": item["id"],
                        "category": item["category"],
                        "query": item["query"],
                        "hit_rank": rank,
                        "top10": ranked[:TOP_K_LARGE],
                        "metrics": evaluate_query(ranked, item["relevant"]),
                    }
                )
            rows.append(
                {
                    "name": config["name"],
                    "note": config["note"],
                    "w_vector": config["w_vector"],
                    "w_bm25": config["w_bm25"],
                    "per_channel_top": config["per_channel_top"],
                    "metrics": aggregate_metrics(per_query),
                    "by_category": aggregate_by_category(per_query),
                    "channel_mix": {
                        "gold_dual_channel": gold_dual,
                        "gold_single_channel": gold_single,
                        "gold_not_recalled_in_top_n": gold_not_recalled,
                        "dual_channel_items_in_top5": dual_in_top5,
                        "dual_channel_items_in_top10": dual_in_top10,
                        "dual_channel_share_of_top10": round(dual_in_top10 / (len(prepared) * TOP_K_LARGE), 4),
                    },
                    "per_query": per_query,
                }
            )
        run_span.update(output={"configs": [{row["name"]: row["metrics"]} for row in rows]})

    return {
        "mode": "weight_ablation",
        "mode_label": "加权 RRF 权重敏感性消融（本地实现，不改 rag/）",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "query_count": len(queries),
        "pool_size": pool_size,
        "rrf_k": DEFAULT_RRF_K,
        "latency_note": "每条查询只算一次 embedding + 一次向量 SQL，延迟含远程 embedding 调用",
        "search_latency_ms": latency_stats([entry["latency_ms"] for entry in prepared]),
        "configs": rows,
    }


def format_weight_ablation(report: dict[str, Any]) -> str:
    header = f"{'配置':<22}{'Recall@5':>12}{'Recall@10':>12}{'MRR@10':>12}{'nDCG@5':>12}"
    lines = [header, "-" * len(header)]
    for config in report["configs"]:
        metrics = config["metrics"]
        lines.append(
            f"{config['name']:<22}"
            + f"{metrics['recall@5'] * 100:>11.2f}%"
            + f"{metrics['recall@10'] * 100:>11.2f}%"
            + f"{metrics['mrr@10']:>12.4f}"
            + f"{metrics['ndcg@5']:>12.4f}"
            + f"   ({config['note']})"
        )
    return "\n".join(lines)


# --------------------------------------------------------------------------- 输出


def format_table(report: dict[str, Any]) -> str:
    rows = [f"模式：{report['mode_label']}（候选池 Top{report['pool_size']}，查询 {report['query_count']} 条）"]
    rows.append(f"{'指标':<10}{'值':>10}")
    for key in METRIC_KEYS:
        rows.append(f"{key:<10}{report['metrics'][key]:>10.4f}")
    latency = report["latency_ms"]
    rows.append(f"{'中位延迟':<10}{latency['median']:>10.1f} ms")
    rows.append(f"{'P95延迟':<10}{latency['p95']:>10.1f} ms")
    rows.append(f"{'平均延迟':<10}{latency['mean']:>10.1f} ms")
    for category, values in report.get("by_category", {}).items():
        rows.append(
            f"  [{category:<11}] recall@5={values['recall@5'] * 100:6.2f}%  "
            f"recall@10={values['recall@10'] * 100:6.2f}%  mrr@10={values['mrr@10']:.4f}  "
            f"ndcg@5={values['ndcg@5']:.4f}"
        )
    return "\n".join(rows)


def format_comparison(reports: dict[str, dict[str, Any]]) -> str:
    """三组对比表 + 混合相对纯向量的提升（百分点 / 相对百分比）。"""
    header = f"{'模式':<16}" + "".join(f"{key:>12}" for key in METRIC_KEYS) + f"{'中位延迟':>14}{'P95延迟':>14}"
    lines = [header, "-" * len(header)]
    for mode in MODES:
        report = reports.get(mode)
        if report is None:
            lines.append(f"{mode:<16}" + "".join(f"{'N/A':>12}" for _ in METRIC_KEYS) + f"{'N/A':>14}{'N/A':>14}")
            continue
        latency = report["latency_ms"]
        row = f"{mode:<16}" + "".join(f"{report['metrics'][key] * 100:>11.2f}%" for key in METRIC_KEYS)
        row += f"{latency['median']:>12.1f}ms{latency['p95']:>12.1f}ms"
        lines.append(row)

    base = reports.get("vector")
    if base is not None:
        lines.append("")
        lines.append("相对纯向量的提升（百分点 / 相对百分比）：")
        for mode in ("hybrid", "hybrid_rerank"):
            report = reports.get(mode)
            if report is None:
                continue
            parts = []
            for key in METRIC_KEYS:
                delta = (report["metrics"][key] - base["metrics"][key]) * 100
                relative = (
                    "—"
                    if base["metrics"][key] == 0
                    else f"{(report['metrics'][key] / base['metrics'][key] - 1) * 100:+.1f}%"
                )
                parts.append(f"{key} {delta:+.2f}pp ({relative})")
            lines.append(f"  {mode}: " + "；".join(parts))
    return "\n".join(lines)


def provider_snapshot(embedder: Any, reranker: Any | None) -> dict[str, Any]:
    """抓一次 embedding / rerank 客户端的累计计数，用于算「本组真实远端调用次数」。"""

    def stats(client: Any, with_model: bool) -> dict[str, Any]:
        entry = {
            "last_provider": getattr(client, "last_provider", None),
            "remote_calls": getattr(client, "remote_count", None),
            "degraded_calls": getattr(client, "degraded_count", None),
            "last_error": getattr(client, "last_error", None),
        }
        if with_model:
            entry["model"] = getattr(client, "model", None)
        return entry

    snapshot = {"embedding": stats(embedder, True)}
    if reranker is not None:
        snapshot["rerank"] = stats(reranker, True)
    return snapshot


def provider_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """本组消耗 = 组后快照 - 组前快照（证明这一组是**真调用**，且没有走本地兜底）。"""
    delta: dict[str, Any] = {}
    for name, after_stats in after.items():
        before_stats = before.get(name, {})
        entry = {key: after_stats.get(key) for key in ("model", "last_provider", "last_error")}
        for key in ("remote_calls", "degraded_calls"):
            now = after_stats.get(key)
            was = before_stats.get(key)
            entry[key] = None if now is None or was is None else now - was
        delta[name] = entry
    return delta


def resolve_path(value: str, default: Path) -> Path:
    """命令行路径：绝对路径原样用；相对路径相对**仓库根**解析（``data/eval/**`` 在仓库根）。"""
    if not value:
        return default
    candidate = Path(value)
    return candidate if candidate.is_absolute() else (REPO_ROOT / candidate)


def write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[写出] {output}")


# --------------------------------------------------------------------------- 主流程


async def run(args: argparse.Namespace) -> int:
    queries_path = resolve_path(args.queries, DEFAULT_QUERIES_PATH)
    queries = load_queries(queries_path)
    category_counts: dict[str, int] = {}
    for item in queries:
        category_counts[item["category"]] = category_counts.get(item["category"], 0) + 1
    print(f"评估集：{queries_path}（{len(queries)} 条，分类 {category_counts}）")

    engine = get_engine()
    embedder = build_embedding_client()
    reranker = build_rerank_client() if args.mode in {"hybrid_rerank", "all"} else None
    selected_modes = [] if args.mode == "weight" else (list(MODES) if args.mode == "all" else [args.mode])
    reports: dict[str, dict[str, Any]] = {}
    try:
        async with engine.connect() as conn:
            known_names = await fetch_recipe_names(conn)
            corpus = CardCorpus(await load_card_documents(conn))
            id_to_name = await fetch_recipe_id_names(conn)

        problems = validate_relevant(queries, known_names)
        distinct_names = len(set(known_names))
        print(f"菜名校验：库中 {len(known_names)} 行菜名（去重 {distinct_names} 个）")
        print(f"relevant 全部存在于 recipes.name = {not problems}")
        for item in queries:
            missing = [name for name in item["relevant"] if name not in set(known_names)]
            if missing:
                print(f"  [FAIL] {item['id']}: {missing}")
        if problems and not args.allow_invalid_relevant:
            print("存在不真实菜名，已中止（用 --allow-invalid-relevant 可跳过，但数字不可信）")
            return 2
        if args.validate_only:
            bad_queries = len({problem.split()[0] for problem in problems})
            print(
                f"--validate-only：仅校验，不跑检索。"
                f"通过 {len(queries) - bad_queries}/{len(queries)} 条，问题 {len(problems)} 处。"
            )
            return 0 if not problems else 2

        for mode in selected_modes:
            print(f"\n=== 开始跑：{mode} ===")
            before = provider_snapshot(embedder, reranker)
            report = await run_mode(
                mode,
                queries,
                engine=engine,
                embedder=embedder,
                corpus=corpus,
                reranker=reranker,
                pool_size=args.pool_size,
            )
            report["provider_stats"] = {
                **provider_delta(before, provider_snapshot(embedder, reranker)),
                "scope": "this_run",
            }
            reports[mode] = report
            print(format_table(report))

        if args.weight_ablation or args.mode == "weight":
            print("\n=== 开始跑：加权 RRF 权重敏感性消融 ===")
            before = provider_snapshot(embedder, reranker)
            ablation = await run_weight_ablation(
                queries,
                engine=engine,
                embedder=embedder,
                corpus=corpus,
                id_to_name=id_to_name,
                pool_size=args.pool_size,
            )
            ablation["provider_stats"] = {
                **provider_delta(before, provider_snapshot(embedder, reranker)),
                "scope": "this_run",
            }
            print(format_weight_ablation(ablation))
            write_report(ablation, DEFAULT_REPORT_DIR / "ablation_weight.json")

        provider_stats = provider_snapshot(embedder, reranker)
        print("\nprovider 进程累计（证明跑过真远端，没走本地兜底）：")
        print(json.dumps(provider_stats, ensure_ascii=False, indent=2))

        for mode, report in reports.items():
            if args.mode == "all":
                write_report(report, DEFAULT_REPORT_DIR / f"{mode}.json")
            else:
                write_report(report, resolve_path(args.output, DEFAULT_REPORT_DIR / f"{mode}.json"))

        if len(reports) > 1:
            print("\n" + format_comparison(reports))
        return 0
    finally:
        closer = getattr(embedder, "aclose", None)
        if closer is not None:
            await closer()
        if reranker is not None:
            rerank_closer = getattr(reranker, "aclose", None)
            if rerank_closer is not None:
                await rerank_closer()
        await engine.dispose()
        flush()


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MealCompass 检索离线评估（三组消融 + 加权敏感性）")
    parser.add_argument(
        "--mode",
        choices=[*MODES, "weight", "all"],
        default="all",
        help="评估模式：all = 三组都跑；weight = 只跑加权 RRF 敏感性消融",
    )
    parser.add_argument("--output", default="", help="单组模式的报告 JSON 路径；相对路径按仓库根解析")
    parser.add_argument("--queries", default="", help="评估集 YAML 路径；相对路径按仓库根解析")
    parser.add_argument("--pool-size", type=int, default=POOL_SIZE, help="三组统一的候选池大小（默认 50）")
    parser.add_argument("--validate-only", action="store_true", help="只校验 relevant 是否是真实菜名")
    parser.add_argument(
        "--weight-ablation",
        action="store_true",
        help="在三组之外额外跑加权 RRF 权重敏感性消融（写出 ablation_weight.json）",
    )
    parser.add_argument(
        "--allow-invalid-relevant",
        action="store_true",
        help="即使 relevant 里有库中不存在的菜名也继续跑（不推荐）",
    )
    return parser.parse_args(argv)


def main() -> int:
    return asyncio.run(run(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
