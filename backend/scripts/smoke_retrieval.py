"""T1.8 真实冒烟：真查询 → SiliconFlow embedding → 混合检索 → Top10 打印。

一次 embed（几分钱量级），验证远端链路 + HNSW 向量通道 + BM25 通道 + RRF。
用法：cd backend && .venv\\Scripts\\python.exe -m scripts.smoke_retrieval
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from infra.db import get_engine
from infra.embedding_client import build_embedding_client
from rag.corpus import CardCorpus, load_card_documents
from rag.retriever import HybridRetriever

QUERIES = ["酸甜开胃的家常菜", "怎么做勾芡", "适合冬天的暖胃汤"]


async def main() -> None:
    embedder = build_embedding_client()
    engine = get_engine()
    try:
        async with engine.connect() as conn:
            corpus = CardCorpus(await load_card_documents(conn))
        retriever = HybridRetriever(embedder=embedder, corpus=corpus, engine=engine)
        for query in QUERIES:
            candidates = await retriever.search(query, top_k=10)
            print(f"\n查询：{query}")
            for candidate in candidates:
                print(
                    f"  #{candidate.rank} {candidate.name}  rrf={candidate.score:.4f}  "
                    f"channels={','.join(candidate.sources)}"
                )
    finally:
        closer = getattr(embedder, "aclose", None)
        if closer is not None:
            await closer()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
