"""Rerank 客户端：**远程优先、本地兜底**（D17 决议）。

与 embedding 同构：

| 实现 | 依赖 | 说明 |
| --- | --- | --- |
| `RemoteRerank` | httpx | OpenAI 兼容之外的 `/rerank` 端点（SiliconFlow `BAAI/bge-reranker-v2-m3`） |
| `LocalRerank` | sentence-transformers（可选） | `CrossEncoder.predict`，惰性加载 |
| `FallbackRerank` | — | 远程失败切本地，记录 provider / 降级次数 |

不变量：返回的是**原始下标**，且按分数降序；调用方据此取回原文，不做二次排序。
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import logging
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from core.config import Settings, get_settings
from infra.model_cache import prepare_local_model_cache

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0
REMOTE_ERROR_HINT = "远程重排失败，降级到本地"


def _local_available() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


def _load_cross_encoder(model: str, device: str | None) -> Any:
    if not _local_available():
        raise RuntimeError(
            "本地重排不可用：未安装 sentence-transformers。需要本地兜底时执行：pip install sentence-transformers"
        )
    prepare_local_model_cache()  # 缓存固定到仓库内，避免「下到 A、加载去 B 找」
    from sentence_transformers import CrossEncoder  # 惰性导入

    return CrossEncoder(model, device=device)


class RemoteRerank:
    """SiliconFlow `/rerank` 客户端。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = client
        self._owns_client = client is None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def rerank(
        self,
        query: str,
        documents: Sequence[str],
        top_k: int = 10,
    ) -> list[tuple[int, float]]:
        if not documents:
            return []
        response = await self._get_client().post(
            f"{self._base_url}/rerank",
            json={
                "model": self.model,
                "query": query,
                "documents": list(documents),
                "top_n": top_k,
            },
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        response.raise_for_status()

        results = response.json()["results"]
        hits = [(int(item["index"]), float(item["relevance_score"])) for item in results]
        hits.sort(key=lambda hit: hit[1], reverse=True)
        return hits[:top_k]


class LocalRerank:
    """sentence-transformers CrossEncoder 本地重排（兜底路径）。"""

    def __init__(
        self,
        *,
        model: str,
        device: str | None = None,
        encoder_loader: Callable[[], Any] | Any | None = None,
    ) -> None:
        self.model = model
        self._device = device
        self._loader = encoder_loader
        self._encoder: Any = None

    def _resolve_encoder(self) -> Any:
        if self._encoder is None:
            if self._loader is None:
                self._encoder = _load_cross_encoder(self.model, self._device)
            elif inspect.isclass(self._loader) or inspect.isroutine(self._loader):
                # 只有类/函数才算工厂；已实例化的模型对象（CrossEncoder 是 nn.Module）不能调用
                self._encoder = self._loader()
            else:
                self._encoder = self._loader
        return self._encoder

    async def rerank(
        self,
        query: str,
        documents: Sequence[str],
        top_k: int = 10,
    ) -> list[tuple[int, float]]:
        if not documents:
            return []
        encoder = self._resolve_encoder()
        pairs = [(query, document) for document in documents]
        scores = await asyncio.to_thread(encoder.predict, pairs)
        hits = [(index, float(score)) for index, score in enumerate(scores)]
        hits.sort(key=lambda hit: hit[1], reverse=True)
        return hits[:top_k]


class FallbackRerank:
    """远程优先、本地兜底，并记录走了哪条路。"""

    def __init__(
        self,
        primary: Any,
        secondary: Any | None = None,
        *,
        on_event: Callable[[str, bool, str | None], None] | None = None,
    ) -> None:
        self.model = getattr(primary, "model", "")
        self._primary = primary
        self._secondary = secondary
        self._on_event = on_event
        self.remote_count = 0
        self.degraded_count = 0
        self.last_provider: str | None = None
        self.last_error: str | None = None

    async def rerank(
        self,
        query: str,
        documents: Sequence[str],
        top_k: int = 10,
    ) -> list[tuple[int, float]]:
        try:
            hits = await self._primary.rerank(query, documents, top_k)
        except Exception as exc:  # noqa: BLE001 - 任何远程异常都触发兜底
            if self._secondary is None:
                raise
            self.degraded_count += 1
            self.last_provider = "local"
            self.last_error = str(exc)
            logger.warning("%s：%s", REMOTE_ERROR_HINT, exc)
            self._emit("local", True, str(exc))
            return list(await self._secondary.rerank(query, documents, top_k))

        self.remote_count += 1
        self.last_provider = "remote"
        self._emit("remote", False, None)
        return hits

    def _emit(self, provider: str, degraded: bool, error: str | None) -> None:
        if self._on_event is not None:
            self._on_event(provider, degraded, error)

    async def aclose(self) -> None:
        for client in (self._primary, self._secondary):
            closer = getattr(client, "aclose", None)
            if closer is not None:
                await closer()


def build_rerank_client(settings: Settings | None = None) -> FallbackRerank:
    """按配置装配：远程必有；本地只有装了 sentence-transformers 才挂上。"""
    settings = settings or get_settings()
    primary = RemoteRerank(
        api_key=settings.embedding_key or "",
        base_url=settings.embedding_url,
        model=settings.reranker_model,
    )
    secondary = (
        LocalRerank(model=settings.reranker_model) if settings.enable_local_fallback and _local_available() else None
    )
    return FallbackRerank(primary, secondary)
