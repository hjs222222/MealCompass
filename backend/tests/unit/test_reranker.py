"""T1.9 重排编排：候选重排 + 失败降级（纯单测，不连库不联网）。"""

from __future__ import annotations

from domain.models.retrieval import RecipeCandidate
from rag.corpus import CardCorpus, CardDocument
from rag.reranker import rerank_candidates

DOCS = [
    CardDocument(key="a", name="A菜", text="A菜\n简介甲\n食材：a1、a2"),
    CardDocument(key="b", name="B菜", text="B菜\n简介乙\n食材：b1、b2"),
    CardDocument(key="c", name="C菜", text="C菜\n简介丙\n食材：c1、c2"),
]
CORPUS = CardCorpus(DOCS)


def _candidates() -> list[RecipeCandidate]:
    return [
        RecipeCandidate(recipe_id="a", name="A菜", score=0.03, rank=1, sources=["vector"]),
        RecipeCandidate(recipe_id="b", name="B菜", score=0.02, rank=2, sources=["bm25"]),
        RecipeCandidate(recipe_id="c", name="C菜", score=0.01, rank=3, sources=["vector", "bm25"]),
    ]


class FakeRerank:
    """可控重排：默认把顺序反成 [a, c, b]；可注入异常。"""

    def __init__(self, hits: list[tuple[int, float]] | None = None, error: Exception | None = None) -> None:
        self._hits = hits if hits is not None else [(0, 0.5), (2, 0.4), (1, 0.1)]
        self._error = error
        self.last_provider: str = "remote"
        self.calls: list[tuple[str, list[str], int]] = []

    async def rerank(self, query: str, documents: list[str], top_k: int = 10) -> list[tuple[int, float]]:
        self.calls.append((query, list(documents), top_k))
        if self._error is not None:
            raise self._error
        return list(self._hits[:top_k])


async def test_success_reranks_and_fills_scores() -> None:
    reranker = FakeRerank()
    out = await rerank_candidates("查询", _candidates(), reranker, corpus=CORPUS)

    # hits=[0(a),2(c),1(b)] → 顺序 a, c, b
    assert [candidate.recipe_id for candidate in out] == ["a", "c", "b"]
    assert [candidate.rank for candidate in out] == [1, 2, 3]
    assert out[0].rerank_score == 0.5
    assert out[1].rerank_score == 0.4
    # provider=remote，未降级
    assert not any(candidate.degraded for candidate in out)
    # 传给重排的是卡片索引文本（与检索同一份）
    assert reranker.calls[0][1] == [DOCS[0].text, DOCS[1].text, DOCS[2].text]
    # 原 RRF 分保留
    assert [candidate.score for candidate in out] == [0.03, 0.01, 0.02]


async def test_failure_falls_back_to_original_rrf_order() -> None:
    reranker = FakeRerank(error=RuntimeError("远程重排挂了"))
    out = await rerank_candidates("查询", _candidates(), reranker, corpus=CORPUS)

    # 降级：保持 RRF 原顺序，标记 degraded
    assert [candidate.recipe_id for candidate in out] == ["a", "b", "c"]
    assert all(candidate.degraded for candidate in out)
    assert all(candidate.rerank_score is None for candidate in out)


async def test_local_provider_is_marked_degraded() -> None:
    reranker = FakeRerank()
    reranker.last_provider = "local"
    out = await rerank_candidates("查询", _candidates(), reranker, corpus=CORPUS)

    assert [candidate.recipe_id for candidate in out] == ["a", "c", "b"]
    assert all(candidate.degraded for candidate in out)  # 走了本地兜底 = 降级路径


async def test_top_k_limits_reranked_results() -> None:
    reranker = FakeRerank()
    out = await rerank_candidates("查询", _candidates(), reranker, corpus=CORPUS, top_k=2)
    assert [candidate.recipe_id for candidate in out] == ["a", "c"]
    assert reranker.calls[0][2] == 2


async def test_empty_candidates_returns_empty_without_calling() -> None:
    reranker = FakeRerank()
    out = await rerank_candidates("查询", [], reranker, corpus=CORPUS)
    assert out == []
    assert reranker.calls == []


async def test_missing_text_falls_back_to_name() -> None:
    # 语料里没有的 doc_id：text_of 返回 None，用候选 name 兜底，不能让重排断掉
    unknown = [RecipeCandidate(recipe_id="zzz", name="神秘菜", score=0.5, rank=1, sources=["vector"])]
    reranker = FakeRerank(hits=[(0, 0.9)])
    out = await rerank_candidates("查询", unknown, reranker, corpus=CORPUS)
    assert out[0].recipe_id == "zzz"
    assert reranker.calls[0][1] == ["神秘菜"]
