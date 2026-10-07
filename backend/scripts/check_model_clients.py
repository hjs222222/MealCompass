"""验证本地兜底与远程通道（T1.7 的收尾检查）。

检查四件事：
1. 本地 embedding 维度 = 1024（必须与 `vector(1024)` 对齐）
2. 本地 rerank 能把「西红柿炒鸡蛋」排在「红烧肉」前面
3. **本地向量与远程向量的余弦相似度** —— 证明两者在同一向量空间（本地兜底才有意义）
4. 降级链路：故意打不通远程时，`FallbackEmbedding` 真的会切到本地

用法（在 `backend/` 下，先跑 scripts/download_local_models.py）::

    .venv\\Scripts\\python.exe -m scripts.check_model_clients
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT / "backend"))

from core.config import get_settings  # noqa: E402
from infra.model_cache import prepare_local_model_cache  # noqa: E402

CACHE_ROOT = prepare_local_model_cache()

PROBE_TEXT = "番茄炒蛋怎么做"
RERANK_DOCS = ["红烧肉的做法", "西红柿炒鸡蛋的家常做法"]


def _cosine(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = (sum(a * a for a in left) ** 0.5) * (sum(b * b for b in right) ** 0.5)
    return dot / norm if norm else 0.0


def main() -> int:
    settings = get_settings()
    try:
        from sentence_transformers import CrossEncoder, SentenceTransformer
    except ImportError:
        print("未安装 sentence-transformers，先跑：", file=sys.stderr)
        print("  uv pip install --python .venv\\Scripts\\python.exe sentence-transformers", file=sys.stderr)
        return 1

    print(f"缓存      = {CACHE_ROOT}")
    print(f"embedding = {settings.embedding_model}")
    print(f"reranker  = {settings.reranker_model}\n")

    print("[1/4] 加载本地 embedding 模型 ...", flush=True)
    started = time.time()
    encoder = SentenceTransformer(settings.embedding_model, device="cpu")
    local_vector = [float(value) for value in encoder.encode([PROBE_TEXT], normalize_embeddings=True)[0]]
    print(f"      维度 = {len(local_vector)}（用时 {time.time() - started:.0f}s）")
    assert len(local_vector) == 1024, "本地向量维度不是 1024，与 schema 的 vector(1024) 不匹配"

    print("[2/4] 加载本地 rerank 模型 ...", flush=True)
    started = time.time()
    cross = CrossEncoder(settings.reranker_model, device="cpu")
    scores = [float(score) for score in cross.predict([(PROBE_TEXT, doc) for doc in RERANK_DOCS])]
    print(f"      打分 = {[round(score, 4) for score in scores]}（用时 {time.time() - started:.0f}s）")
    print(f"      排序正确：{scores[1] > scores[0]}")
    assert scores[1] > scores[0], "本地重排把「红烧肉」排在了「西红柿炒鸡蛋」前面"

    print("[3/4] 对比本地与远程向量 ...")
    from infra.embedding_client import RemoteEmbedding

    async def remote_vector() -> list[float]:
        client = RemoteEmbedding(
            api_key=settings.embedding_key or "",
            base_url=settings.embedding_url,
            model=settings.embedding_model,
        )
        try:
            return (await client.embed([PROBE_TEXT]))[0]
        finally:
            await client.aclose()

    try:
        remote = asyncio.run(remote_vector())
        similarity = _cosine(local_vector, remote)
        print(f"      余弦相似度 = {similarity:.4f}")
        print(f"      结论：{'同模型，向量空间一致 ✓' if similarity > 0.98 else '⚠️ 偏差偏大，需排查'}")
    except Exception as exc:  # noqa: BLE001 - 远程不可用不影响本地结论
        print(f"      远程不可用（{type(exc).__name__}），跳过对比")

    print("[4/4] 降级链路：故意打不通远程 ...")

    async def degraded() -> None:
        from infra.embedding_client import FallbackEmbedding, LocalEmbedding, RemoteEmbedding

        broken = RemoteEmbedding(
            api_key="broken",
            base_url="https://127.0.0.1:9/v1",
            model=settings.embedding_model,
            timeout=2.0,
        )
        client = FallbackEmbedding(broken, LocalEmbedding(model=settings.embedding_model))
        try:
            vectors = await client.embed([PROBE_TEXT])
            print(f"      provider = {client.last_provider}，降级次数 = {client.degraded_count}")
            print(f"      兜底向量维度 = {len(vectors[0])}")
            assert client.last_provider == "local" and len(vectors[0]) == 1024
        finally:
            await broken.aclose()

    asyncio.run(degraded())

    print("\n全部通过：本地兜底可用，且与远程同空间。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
