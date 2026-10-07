"""T1.8 BM25 通道：小语料单测（不加载 jieba 词典，直接喂词项）。"""

from __future__ import annotations

import pytest

from rag.bm25_index import BM25Index

# 三张「卡片」：西红柿炒鸡蛋 / 红烧肉 / 番茄鸡蛋汤（已分词）
DOC_IDS = ["tomato-egg", "hongshao-pork", "tomato-egg-soup"]
CORPUS = [
    ["西红柿", "炒", "鸡蛋", "食用油", "盐", "葱花"],
    ["五花肉", "冰糖", "生抽", "八角", "姜"],
    ["番茄", "鸡蛋", "香油", "盐", "葱"],
]


def _index() -> BM25Index:
    return BM25Index(DOC_IDS, CORPUS)


def test_dimensions_must_match() -> None:
    with pytest.raises(ValueError):
        BM25Index(["a"], [["x"], ["y"]])


def test_query_matches_expected_docs_and_ranks_shorter_doc_higher() -> None:
    hits = _index().search(["鸡蛋"], top_n=5)
    ids = [doc_id for doc_id, _ in hits]
    # 「红烧肉」不含鸡蛋，不命中
    assert "hongshao-pork" not in ids
    assert set(ids) == {"tomato-egg", "tomato-egg-soup"}
    # 两道菜都只出现一次「鸡蛋」，短文档长度归一化后分更高
    assert ids[0] == "tomato-egg-soup"


def test_synonym_query_via_caller_tokenization() -> None:
    # 「西红柿」与「番茄」的同义和由查询扩展负责（词表）；BM25 只做精确词项匹配。
    # 这里直接验证：查「番茄」只命中番茄鸡蛋汤，查「西红柿」只命中西红柿炒鸡蛋。
    assert [doc_id for doc_id, _ in _index().search(["番茄"], top_n=5)] == ["tomato-egg-soup"]
    assert [doc_id for doc_id, _ in _index().search(["西红柿"], top_n=5)] == ["tomato-egg"]


def test_no_match_returns_empty() -> None:
    assert _index().search(["龙虾"], top_n=5) == []


def test_empty_query_or_corpus_returns_empty() -> None:
    assert _index().search([], top_n=5) == []
    assert BM25Index([], []).search(["鸡蛋"], top_n=5) == []


def test_allowed_ids_limit_after_scoring_and_empty_intersection_is_empty() -> None:
    index = BM25Index(
        [f"recipe-{number}" for number in range(60)],
        [["egg", f"token-{number}"] for number in range(60)],
    )

    hits = index.search(["egg", "token-59"], top_n=50, allowed_ids={"recipe-59"})

    assert [doc_id for doc_id, _ in hits] == ["recipe-59"]
    assert index.search(["egg"], top_n=50, allowed_ids={"missing"}) == []


def test_top_n_is_respected() -> None:
    assert len(_index().search(["鸡蛋"], top_n=1)) == 1
