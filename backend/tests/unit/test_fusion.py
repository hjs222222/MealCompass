"""T1.8 RRF 融合：先写测试（纯函数）。"""

from __future__ import annotations

from rag.fusion import DEFAULT_RRF_K, reciprocal_rank_fusion


def test_single_channel_keeps_order() -> None:
    fused = reciprocal_rank_fusion({"vector": ["a", "b", "c"]})
    assert [item[0] for item in fused] == ["a", "b", "c"]
    assert fused[0][1] == 1.0 / (DEFAULT_RRF_K + 1)
    assert fused[0][2] == ["vector"]


def test_two_channels_agree_winner_ranks_first() -> None:
    fused = reciprocal_rank_fusion(
        {"vector": ["a", "b"], "bm25": ["a", "c"]},
    )
    assert fused[0][0] == "a"  # 两路都第一
    # a 的分数 = 两个第一名之和
    assert fused[0][1] == 2.0 / (DEFAULT_RRF_K + 1)
    assert fused[0][2] == ["vector", "bm25"]


def test_consensus_beats_single_channel_high_rank() -> None:
    """两路都召回但排名靠后者，分数应高于只在一路排第一者。"""
    fused = reciprocal_rank_fusion(
        {"vector": ["only_vector", "shared"], "bm25": ["only_bm25", "shared"]},
    )
    by_id = {item[0]: item for item in fused}
    assert by_id["shared"][1] > by_id["only_vector"][1]
    assert by_id["shared"][1] > by_id["only_bm25"][1]
    assert fused[0][0] == "shared"


def test_top_n_limits_results() -> None:
    fused = reciprocal_rank_fusion({"vector": ["a", "b", "c", "d"]}, top_n=2)
    assert [item[0] for item in fused] == ["a", "b"]


def test_duplicate_id_in_one_channel_counts_once() -> None:
    fused = reciprocal_rank_fusion({"vector": ["a", "a", "b"]})
    by_id = {item[0]: item for item in fused}
    # 只计第一次出现的排名（第 1 名）
    assert by_id["a"][1] == 1.0 / (DEFAULT_RRF_K + 1)


def test_tie_break_is_deterministic() -> None:
    """同分（不同通道、相同排名）时按通道声明顺序稳定排序。"""
    fused1 = reciprocal_rank_fusion({"vector": ["x"], "bm25": ["y"]})
    fused2 = reciprocal_rank_fusion({"vector": ["x"], "bm25": ["y"]})
    assert [item[0] for item in fused1] == [item[0] for item in fused2] == ["x", "y"]


def test_empty_input() -> None:
    assert reciprocal_rank_fusion({}) == []
