"""Embedding 客户端：**远程优先、本地兜底**（D17 决议）。

| 实现 | 依赖 | 说明 |
| --- | --- | --- |
| `RemoteEmbedding` | httpx | OpenAI 兼容的 `/embeddings`（SiliconFlow `BAAI/bge-m3`，1024 维）；分批、截断、重试 |
| `LocalEmbedding` | sentence-transformers | 惰性加载；没装就抛清晰错误，由 `build_embedding_client` 决定是否挂上 |
| `FallbackEmbedding` | — | 远程失败切本地，并记录 `last_provider` / `degraded_count` / `last_error` 供 trace 使用 |

不变量：**返回的向量与入参顺序严格对应**，长度不等就是 bug（上层靠下标对齐菜谱）。
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import logging
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from core.config import Settings, get_settings
from infra.model_cache import prepare_local_model_cache

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 16
DEFAULT_MAX_CHARS = 4000  # 防御性截断；bge-m3 上限 8192 token，菜谱文本远小于此
DEFAULT_TIMEOUT = 30.0
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
REMOTE_ERROR_HINT = "远程 embedding 失败，降级到本地"


@dataclass(frozen=True)
class ProviderEvent:
    """一次调用实际走了哪条路，供 trace 记录。"""

    provider: str  # "remote" | "local"
    degraded: bool
    error: str | None = None


def _chunked(items: Sequence[str], size: int) -> Iterator[list[str]]:
    for start in range(0, len(items), size):
        yield list(items[start : start + size])


def _local_available() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


def _load_sentence_transformer(model: str, device: str | None) -> Any:
    if not _local_available():
        raise RuntimeError(
            "本地 embedding 不可用：未安装 sentence-transformers。需要本地兜底时执行：pip install sentence-transformers"
        )
    prepare_local_model_cache()  # 缓存固定到仓库内，避免「下到 A、加载去 B 找」
    from sentence_transformers import SentenceTransformer  # 惰性导入，没装也不会拖慢启动

    return SentenceTransformer(model, device=device)


class RemoteEmbedding:
    """OpenAI 兼容的 `/embeddings` 客户端（SiliconFlow / 其它同协议服务）。"""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = DEFAULT_TIMEOUT,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_chars: int = DEFAULT_MAX_CHARS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._batch_size = max(1, batch_size)
        self._max_chars = max(1, max_chars)
        self._client = client
        self._owns_client = client is None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        """只关自己创建的连接池；外部注入的由调用方负责。"""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        prepared = [text[: self._max_chars] for text in texts]
        vectors: list[list[float]] = []
        for batch in _chunked(prepared, self._batch_size):
            vectors.extend(await self._embed_batch(batch))
        return vectors

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        payload = {"model": self.model, "input": batch}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        client = self._get_client()

        response = await client.post(f"{self._base_url}/embeddings", json=payload, headers=headers)
        if response.status_code in RETRY_STATUS:
            response = await client.post(f"{self._base_url}/embeddings", json=payload, headers=headers)
        response.raise_for_status()

        data = response.json()["data"]
        # 有的服务商不保证返回顺序，按 index 还原
        return [item["embedding"] for item in sorted(data, key=lambda item: item.get("index", 0))]


class LocalEmbedding:
    """sentence-transformers 本地推理（兜底路径）。"""

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
                self._encoder = _load_sentence_transformer(self.model, self._device)
            elif inspect.isclass(self._loader) or inspect.isroutine(self._loader):
                # 只有类/函数才算工厂；已实例化的模型对象（SentenceTransformer 是 nn.Module）不能调用
                self._encoder = self._loader()
            else:
                self._encoder = self._loader
        return self._encoder

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        encoder = self._resolve_encoder()
        matrix = await asyncio.to_thread(encoder.encode, list(texts), normalize_embeddings=True)
        return [[float(value) for value in row] for row in matrix]


class FallbackEmbedding:
    """远程优先、本地兜底，并把「走了哪条路」记下来。"""

    def __init__(
        self,
        primary: Any,
        secondary: Any | None = None,
        *,
        on_event: Callable[[ProviderEvent], None] | None = None,
    ) -> None:
        self.model = getattr(primary, "model", "")
        self._primary = primary
        self._secondary = secondary
        self._on_event = on_event
        self.remote_count = 0
        self.degraded_count = 0
        self.last_provider: str | None = None
        self.last_error: str | None = None

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        try:
            vectors = await self._primary.embed(texts)
        except Exception as exc:  # noqa: BLE001 - 任何远程异常都应该触发兜底
            if self._secondary is None:
                raise
            self.degraded_count += 1
            self.last_provider = "local"
            self.last_error = str(exc)
            logger.warning("%s：%s", REMOTE_ERROR_HINT, exc)
            self._emit(ProviderEvent(provider="local", degraded=True, error=str(exc)))
            return list(await self._secondary.embed(texts))

        self.remote_count += 1
        self.last_provider = "remote"
        self._emit(ProviderEvent(provider="remote", degraded=False))
        return vectors

    def _emit(self, event: ProviderEvent) -> None:
        if self._on_event is not None:
            self._on_event(event)

    async def aclose(self) -> None:
        for client in (self._primary, self._secondary):
            closer = getattr(client, "aclose", None)
            if closer is not None:
                await closer()


def build_embedding_client(settings: Settings | None = None) -> FallbackEmbedding:
    """按配置装配：远程必有；本地只有装了 sentence-transformers 才挂上。"""
    settings = settings or get_settings()
    primary = RemoteEmbedding(
        api_key=settings.embedding_key or "",
        base_url=settings.embedding_url,
        model=settings.embedding_model,
    )
    secondary = (
        LocalEmbedding(model=settings.embedding_model)
        if settings.enable_local_fallback and _local_available()
        else None
    )
    return FallbackEmbedding(primary, secondary)
