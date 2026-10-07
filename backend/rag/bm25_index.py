"""BM25 关键词检索（rank-bm25 + jieba）：T1.8 的关键词通道。

为什么放在应用层而不是 PG tsvector：TECH_STACK 选型是 ``rank-bm25 + jieba``，
372 张卡片的语料在内存里构建只需要一次 SQL + jieba 分词（毫秒~百毫秒级），
无需独立服务。与 ``recipe_embeddings.tsv`` 共用 `rag.tokenization`，词项一致。

类本身零 IO：喂入「文档 id + 分词后的词项」即可，方便单测；
语料加载在 `rag.retriever.CardCorpus`。
"""

from __future__ import annotations

from collections.abc import Sequence

from rank_bm25 import BM25Okapi


class BM25Index:
    """对一批卡片文档建 BM25，查询返回 ``[(doc_id, 分数)]``（降序，去空分）。"""

    def __init__(self, doc_ids: Sequence[str], tokenized_corpus: Sequence[Sequence[str]]) -> None:
        if len(doc_ids) != len(tokenized_corpus):
            raise ValueError("doc_ids 与语料条数不一致")
        self._doc_ids = list(doc_ids)
        tokenized = [list(tokens) for tokens in tokenized_corpus]
        # rank-bm25 对空语料（corpus_size=0）或全空文档（avgdl=0）会除零，退化成本地空索引
        if not doc_ids or not any(tokenized):
            self._bm25 = None
        else:
            self._bm25 = BM25Okapi(tokenized)

    def __len__(self) -> int:
        return len(self._doc_ids)

    def search(
        self, query_tokens: Sequence[str], top_n: int, allowed_ids: set[str] | None = None
    ) -> list[tuple[str, float]]:
        if self._bm25 is None or not query_tokens or top_n <= 0:
            return []
        if allowed_ids is not None and not allowed_ids:
            return []
        scores = self._bm25.get_scores(list(query_tokens))
        ranked = sorted(
            (
                (self._doc_ids[index], float(score))
                for index, score in enumerate(scores)
                if score > 0 and (allowed_ids is None or self._doc_ids[index] in allowed_ids)
            ),
            key=lambda hit: hit[1],
            reverse=True,
        )
        return ranked[:top_n]
