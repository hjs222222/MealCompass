"""T1.8 BM25 卡片语料（CardCorpus）：纯逻辑单测，不连库。"""

from __future__ import annotations

from rag.corpus import CardCorpus, CardDocument

R1 = "11111111-1111-1111-1111-111111111111"
R2 = "22222222-2222-2222-2222-222222222222"
R3 = "33333333-3333-3333-3333-333333333333"


def _documents() -> list[CardDocument]:
    return [
        CardDocument(key=R1, name="西红柿炒鸡蛋", text="西红柿炒鸡蛋\n国民下饭菜。\n食材：西红柿、鸡蛋、盐、糖"),
        CardDocument(key=R2, name="红烧肉", text="红烧肉\n肥而不腻。\n食材：五花肉、冰糖、生抽、八角"),
        CardDocument(key=R3, name="番茄鸡蛋汤", text="番茄鸡蛋汤\n清淡开胃。\n食材：番茄、鸡蛋、香油、盐"),
    ]


def test_search_hits_relevant_docs_with_positive_scores() -> None:
    hits = CardCorpus(_documents()).search("鸡蛋", top_n=5)
    assert len(hits) == 2
    assert {doc_id for doc_id, _ in hits} == {R1, R3}
    assert all(score > 0 for _, score in hits)
    # 分数降序
    assert [score for _, score in hits] == sorted((score for _, score in hits), reverse=True)


def test_search_top_n_is_respected() -> None:
    hits = CardCorpus(_documents()).search("鸡蛋", top_n=1)
    assert len(hits) == 1


def test_search_no_match_returns_empty() -> None:
    assert CardCorpus(_documents()).search("龙虾", top_n=5) == []


def test_search_empty_query_returns_empty() -> None:
    assert CardCorpus(_documents()).search("", top_n=5) == []
    assert CardCorpus(_documents()).search("  ！！", top_n=5) == []


def test_empty_corpus_search_returns_empty() -> None:
    assert CardCorpus([]).search("鸡蛋", top_n=5) == []


def test_name_of_resolves_recipe_name() -> None:
    corpus = CardCorpus(_documents())
    assert corpus.name_of(R1) == "西红柿炒鸡蛋"
    assert corpus.name_of("00000000-0000-0000-0000-000000000000") is None


def test_text_of_resolves_card_document() -> None:
    corpus = CardCorpus(_documents())
    assert corpus.text_of(R2) == "红烧肉\n肥而不腻。\n食材：五花肉、冰糖、生抽、八角"
    assert corpus.text_of("00000000-0000-0000-0000-000000000000") is None


def test_doc_ids_are_exposed_as_strings() -> None:
    assert CardCorpus(_documents()).doc_ids == [R1, R2, R3]
