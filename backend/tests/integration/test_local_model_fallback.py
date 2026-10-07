"""T1.7 收尾：**真·本地模型**的集成测试。

与 `test_siliconflow_smoke.py` 互补——那边验远程，这边验本地兜底真的能跑，
而且验证两者在**同一个向量空间**（这是"兜底"成立的前提）。

模型没下载或没装 sentence-transformers 时自动跳过，不会拖累普通 `pytest`。
首次跑要几十秒（加载 2.2 GB 权重）。
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from core.config import get_settings
from infra.model_cache import prepare_local_model_cache

REPO_ROOT = Path(__file__).resolve().parents[3]
prepare_local_model_cache()  # 必须在 import sentence_transformers 之前

settings = get_settings()
PROBE = "番茄炒蛋怎么做"
DOCS = ["红烧肉的做法", "西红柿炒鸡蛋的家常做法"]


def _models_ready() -> bool:
    if importlib.util.find_spec("sentence_transformers") is None:
        return False
    cache = Path(os.environ["SENTENCE_TRANSFORMERS_HOME"])
    return all(
        (cache / f"models--{repo.replace('/', '--')}").exists()
        for repo in (settings.embedding_model, settings.reranker_model)
    )


pytestmark = pytest.mark.skipif(
    not _models_ready(),
    reason="本地模型未就绪：先跑 scripts/download_local_models.py 装好 sentence-transformers 与权重",
)


@pytest.fixture(scope="module")
def encoder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model, device="cpu")


@pytest.fixture(scope="module")
def cross_encoder():
    from sentence_transformers import CrossEncoder

    return CrossEncoder(settings.reranker_model, device="cpu")


async def test_local_embedding_returns_schema_dimension(encoder) -> None:
    """维度必须与 `vector(1024)` 对齐，否则本地兜底写不进库。"""
    from infra.embedding_client import LocalEmbedding

    vectors = await LocalEmbedding(model=settings.embedding_model, encoder_loader=encoder).embed([PROBE])

    assert len(vectors) == 1
    assert len(vectors[0]) == 1024


async def test_local_embedding_shares_vector_space_with_remote(encoder) -> None:
    """同模型 → 同一向量空间。相似度低说明本地兜底会毁掉索引，必须报警。"""
    if not settings.embedding_key:
        pytest.skip(".env 里没有 key，跳过远程对比")

    from infra.embedding_client import LocalEmbedding, RemoteEmbedding

    local = (await LocalEmbedding(model=settings.embedding_model, encoder_loader=encoder).embed([PROBE]))[0]
    remote_client = RemoteEmbedding(
        api_key=settings.embedding_key,
        base_url=settings.embedding_url,
        model=settings.embedding_model,
    )
    try:
        remote = (await remote_client.embed([PROBE]))[0]
    finally:
        await remote_client.aclose()

    dot = sum(a * b for a, b in zip(local, remote, strict=True))
    norm = (sum(a * a for a in local) ** 0.5) * (sum(b * b for b in remote) ** 0.5)
    similarity = dot / norm

    assert similarity > 0.98, f"本地与远程向量余弦相似度只有 {similarity:.4f}，向量空间可能不一致"


async def test_local_rerank_orders_semantically(cross_encoder) -> None:
    from infra.rerank_client import LocalRerank

    hits = await LocalRerank(model=settings.reranker_model, encoder_loader=cross_encoder).rerank(
        "番茄炒蛋", DOCS, top_k=2
    )

    assert hits[0][0] == 1  # 西红柿炒鸡蛋
    assert hits[0][1] > hits[-1][1]


async def test_fallback_degrades_to_real_local_model(encoder) -> None:
    """远程打不通时，真的切到本地模型并产出可用向量（不是假编码器）。"""
    from infra.embedding_client import FallbackEmbedding, LocalEmbedding, RemoteEmbedding

    broken = RemoteEmbedding(
        api_key="broken",
        base_url="https://127.0.0.1:9/v1",
        model=settings.embedding_model,
        timeout=2.0,
    )
    client = FallbackEmbedding(broken, LocalEmbedding(model=settings.embedding_model, encoder_loader=encoder))
    try:
        vectors = await client.embed([PROBE])
    finally:
        await broken.aclose()

    assert client.last_provider == "local"
    assert client.degraded_count == 1
    assert client.last_error is not None
    assert len(vectors[0]) == 1024
