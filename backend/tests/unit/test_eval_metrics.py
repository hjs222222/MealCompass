"""C2 评估指标纯函数单测（TDD 覆盖：完美命中 / 完全未命中 / 部分命中 / 空 relevant）。

被测对象：``scripts.eval`` 顶层的四个指标函数（``recall_at_k`` / ``mrr_at_k`` /
``ndcg_at_k`` / ``hit_rank``）与 ``evaluate_query`` / ``aggregate_metrics`` /
``latency_stats`` / ``unique_preserving_order``。纯函数、零 IO、不连库。
"""

from __future__ import annotations

import math
import statistics

import pytest

from rag.fusion import DEFAULT_RRF_K, reciprocal_rank_fusion
from scripts.eval import (
    METRIC_KEYS,
    TOP_K_LARGE,
    TOP_K_SMALL,
    aggregate_metrics,
    evaluate_query,
    hit_rank,
    latency_stats,
    mrr_at_k,
    ndcg_at_k,
    provider_delta,
    recall_at_k,
    unique_preserving_order,
    weighted_rrf,
)

GOLD = ["西红柿炒鸡蛋", "西红柿鸡蛋汤"]


# --------------------------------------------------------------------- Recall@k


def test_recall_perfect_hit() -> None:
    retrieved = ["西红柿炒鸡蛋", "西红柿鸡蛋汤", "地三鲜"]
    assert recall_at_k(retrieved, GOLD, 5) == 1.0
    assert recall_at_k(retrieved, GOLD, 1) == 0.5  # 只召回 1/2


def test_recall_complete_miss() -> None:
    retrieved = ["地三鲜", "麻婆豆腐"]
    assert recall_at_k(retrieved, GOLD, 5) == 0.0
    assert recall_at_k(retrieved, GOLD, 10) == 0.0


def test_recall_partial_hit_respects_k() -> None:
    """命中项排在第 6 位：Recall@5 拿不到，Recall@10 拿得到。"""
    retrieved = ["a", "b", "c", "d", "e", "西红柿鸡蛋汤", "f"]
    assert recall_at_k(retrieved, GOLD, 5) == 0.0
    assert recall_at_k(retrieved, GOLD, 10) == 0.5


def test_recall_empty_relevant_is_zero() -> None:
    assert recall_at_k(["a", "b"], [], 5) == 0.0


def test_recall_k_zero_is_zero() -> None:
    assert recall_at_k(GOLD, GOLD, 0) == 0.0


# --------------------------------------------------------------------- MRR@k / hit_rank


def test_hit_rank_and_mrr_perfect_hit() -> None:
    assert hit_rank(["西红柿炒鸡蛋", "x"], GOLD, 10) == 1
    assert mrr_at_k(["西红柿炒鸡蛋", "x"], GOLD, 10) == 1.0


def test_hit_rank_partial_hit_uses_first_hit_only() -> None:
    retrieved = ["x", "y", "西红柿鸡蛋汤", "西红柿炒鸡蛋"]
    assert hit_rank(retrieved, GOLD, 10) == 3
    assert mrr_at_k(retrieved, GOLD, 10) == pytest.approx(1 / 3)


def test_mrr_complete_miss_and_empty() -> None:
    assert mrr_at_k(["a", "b"], GOLD, 10) == 0.0
    assert mrr_at_k(GOLD, [], 10) == 0.0
    assert hit_rank(["a"], [], 10) is None


def test_mrr_respects_k_cutoff() -> None:
    retrieved = ["a", "b", "c", "d", "e", "西红柿炒鸡蛋"]
    assert mrr_at_k(retrieved, GOLD, 5) == 0.0
    assert mrr_at_k(retrieved, GOLD, 10) == pytest.approx(1 / 6)


# --------------------------------------------------------------------- nDCG@k


def test_ndcg_perfect_ranking_is_one() -> None:
    retrieved = ["西红柿炒鸡蛋", "西红柿鸡蛋汤", "地三鲜"]
    assert ndcg_at_k(retrieved, GOLD, 5) == pytest.approx(1.0)


def test_ndcg_matches_manual_formula() -> None:
    """命中项排第 2：DCG = 1/log2(3)，IDCG = 1/log2(2) + 1/log2(3)。"""
    retrieved = ["x", "西红柿炒鸡蛋", "y"]
    expected = (1 / math.log2(3)) / (1 / math.log2(2) + 1 / math.log2(3))
    assert ndcg_at_k(retrieved, GOLD, 5) == pytest.approx(expected)


def test_ndcg_complete_miss_is_zero() -> None:
    assert ndcg_at_k(["a", "b", "c"], GOLD, 5) == 0.0


def test_ndcg_empty_relevant_or_empty_retrieved_is_zero() -> None:
    assert ndcg_at_k(GOLD, [], 5) == 0.0
    assert ndcg_at_k([], GOLD, 5) == 0.0


def test_ndcg_ideal_uses_min_of_gold_and_k() -> None:
    """金标准 2 条但只看 Top1：命中第 1 位就是满分（IDCG 只算 1 位）。"""
    assert ndcg_at_k(["西红柿炒鸡蛋", "x"], GOLD, 1) == pytest.approx(1.0)


def test_ndcg_respects_k_cutoff() -> None:
    retrieved = ["a", "b", "c", "d", "e", "西红柿炒鸡蛋"]
    assert ndcg_at_k(retrieved, GOLD, 5) == 0.0


# --------------------------------------------------------------------- 组合函数


def test_evaluate_query_keys_and_values() -> None:
    metrics = evaluate_query(["西红柿炒鸡蛋", "西红柿鸡蛋汤"], GOLD)
    assert set(metrics) == set(METRIC_KEYS)
    assert metrics["recall@5"] == 1.0
    assert metrics["recall@10"] == 1.0
    assert metrics["mrr@10"] == 1.0
    assert metrics["ndcg@5"] == pytest.approx(1.0)


def test_evaluate_query_uses_documented_k_values() -> None:
    assert (TOP_K_SMALL, TOP_K_LARGE) == (5, 10)


def test_aggregate_metrics_is_macro_average() -> None:
    per_query = [
        {"metrics": {"recall@5": 1.0, "recall@10": 1.0, "mrr@10": 1.0, "ndcg@5": 1.0}},
        {"metrics": {"recall@5": 0.0, "recall@10": 0.5, "mrr@10": 0.0, "ndcg@5": 0.0}},
    ]
    aggregated = aggregate_metrics(per_query)
    assert aggregated["recall@5"] == pytest.approx(0.5)
    assert aggregated["recall@10"] == pytest.approx(0.75)
    assert aggregated["mrr@10"] == pytest.approx(0.5)
    assert aggregated["ndcg@5"] == pytest.approx(0.5)


def test_aggregate_metrics_empty_input_is_all_zero() -> None:
    assert aggregate_metrics([]) == dict.fromkeys(METRIC_KEYS, 0.0)


def test_unique_preserving_order_dedupes_same_name() -> None:
    """库里有同名菜谱（陈皮排骨汤 ×2），同名只算第一次出现的位置。"""
    ranked = unique_preserving_order(["陈皮排骨汤", "地三鲜", "陈皮排骨汤"])
    assert ranked == ["陈皮排骨汤", "地三鲜"]


# --------------------------------------------------------------------- 延迟统计


def test_latency_stats_median_and_p95() -> None:
    latency = latency_stats([100.0, 200.0, 300.0, 400.0, 500.0])
    assert latency["median"] == 300.0
    assert latency["p95"] == 500.0
    assert latency["min"] == 100.0
    assert latency["max"] == 500.0
    assert latency["mean"] == pytest.approx(300.0)


def test_latency_stats_single_sample() -> None:
    latency = latency_stats([42.0])
    assert set(latency.values()) == {42.0}


def test_latency_stats_empty_input() -> None:
    assert latency_stats([]) == {"median": 0.0, "p95": 0.0, "mean": 0.0, "min": 0.0, "max": 0.0}


def test_latency_stats_p95_is_within_range() -> None:
    values = [12.5, 33.1, 7.0, 900.0, 55.2, 61.0, 48.8, 72.3]
    latency = latency_stats(values)
    assert statistics.median(values) == latency["median"]
    assert latency["min"] <= latency["p95"] <= latency["max"]


# ------------------------------------------------------- 加权 RRF（消融脚本本地实现）


def test_weighted_rrf_equal_weights_matches_upstream_rrf() -> None:
    """w=1/1 时，本脚本的加权实现必须与 ``rag.fusion`` 的输出逐位一致（含同分排序）。"""
    vector = ["a", "b", "c"]
    bm25 = ["c", "a", "d"]
    expected = reciprocal_rank_fusion({"vector": vector, "bm25": bm25}, k=DEFAULT_RRF_K)
    actual = weighted_rrf([("vector", 1.0, vector), ("bm25", 1.0, bm25)], k=DEFAULT_RRF_K)
    assert [(rid, round(score, 12), ch) for rid, score, ch in actual] == [
        (rid, round(score, 12), ch) for rid, score, ch in expected
    ]


def test_weighted_rrf_zero_bm25_weight_is_pure_vector() -> None:
    ranked = weighted_rrf([("vector", 1.0, ["a", "b", "c"]), ("bm25", 0.0, ["z", "b"])], k=DEFAULT_RRF_K)
    assert [rid for rid, _, _ in ranked] == ["a", "b", "c"]
    assert "z" not in {rid for rid, _, _ in ranked}


def test_weighted_rrf_downweights_noisy_channel() -> None:
    """BM25 第 1 名的噪声 z 挤掉向量第 40 名的真值 a；BM25 降权后真值回到前面。

    这正是评估里观察到的真实回归形态：真值只被向量通道以靠后的名次召回，
    而 BM25 的头部候选靠词面重叠拿到 1/(k+1) 的高分。
    """
    vector = [f"filler{index}" for index in range(1, 40)] + ["a"]
    bm25 = ["z"]
    assert vector.index("a") + 1 == 40
    equal = {rid: score for rid, score, _ in weighted_rrf([("vector", 1.0, vector), ("bm25", 1.0, bm25)])}
    downweighted = {rid: score for rid, score, _ in weighted_rrf([("vector", 1.0, vector), ("bm25", 0.25, bm25)])}
    assert equal["z"] > equal["a"]  # 等权：BM25 噪声反超真值
    assert downweighted["a"] > downweighted["z"]  # 降权到 0.25：真值回到前面
    assert downweighted["z"] < equal["z"]  # 降权严格压低噪声分


def test_weighted_rrf_top_n_and_channel_tags() -> None:
    ranked = weighted_rrf(
        [("vector", 1.0, ["a", "b"]), ("bm25", 0.5, ["b", "c"])],
        k=DEFAULT_RRF_K,
        top_n=2,
    )
    assert [rid for rid, _, _ in ranked] == ["b", "a"]
    assert ranked[0][2] == ["vector", "bm25"]
    assert ranked[1][2] == ["vector"]


def test_weighted_rrf_empty_input() -> None:
    assert weighted_rrf([]) == []
    assert weighted_rrf([("vector", 1.0, [])]) == []


# ------------------------------------------------------- provider 计数快照（真调用证据）


def test_provider_delta_subtracts_snapshots() -> None:
    before = {"embedding": {"remote_calls": 100, "degraded_calls": 0, "model": "m", "last_provider": "remote"}}
    after = {"embedding": {"remote_calls": 140, "degraded_calls": 2, "model": "m", "last_provider": "local"}}
    delta = provider_delta(before, after)
    assert delta["embedding"]["remote_calls"] == 40
    assert delta["embedding"]["degraded_calls"] == 2
    assert delta["embedding"]["last_provider"] == "local"


def test_provider_delta_handles_missing_snapshot() -> None:
    delta = provider_delta({}, {"embedding": {"remote_calls": 7, "degraded_calls": 1}})
    assert delta["embedding"]["remote_calls"] is None
    assert delta["embedding"]["degraded_calls"] is None
