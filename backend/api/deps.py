"""HTTP 依赖装配（唯一允许 new 出具体实现的地方）。

装配顺序：``api.deps``（具体实现）→ ``services``（只认 Protocol）。
``CardCorpus`` 需要从库加载 372 条卡片文档并构建 BM25 索引，属于**进程级**重活：
这里做一个惰性单例（同一份 settings 只建一次），避免每个请求重建。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

from fastapi import Depends

from core.config import Settings, get_settings
from infra.db import get_engine
from infra.embedding_client import build_embedding_client
from infra.llm_client import build_llm_client
from infra.recipe_details import SqlRecipeDetailsReader
from infra.rerank_client import build_rerank_client
from rag.corpus import CardCorpus, load_card_documents
from rag.retriever import HybridRetriever
from services.recipe_page_service import RecipePageService
from services.recommend_service import RecommendService

logger = logging.getLogger(__name__)

_services: dict[int, RecommendService] = {}
_build_lock: asyncio.Lock | None = None


def get_app_settings() -> Settings:
    """Return the process application settings."""
    return get_settings()


AppSettings = Annotated[Settings, Depends(get_app_settings)]


def tracing_degraded(settings: Settings) -> bool:
    """Return whether optional tracing is unavailable for the current settings."""
    return not settings.tracing_enabled


def _lock() -> asyncio.Lock:
    """惰性创建进程级锁（Lock 必须在事件循环内创建，不能在模块 import 时 new）。"""
    global _build_lock
    if _build_lock is None:
        _build_lock = asyncio.Lock()
    return _build_lock


async def _build_service(settings: Settings) -> RecommendService:
    """真实装配：真库 corpus + 远程优先 embedding/rerank + OpenAI 兼容 LLM。"""
    engine = get_engine()
    async with engine.connect() as conn:
        corpus = CardCorpus(await load_card_documents(conn))
    retriever = HybridRetriever(
        embedder=build_embedding_client(settings),
        corpus=corpus,
        reranker=build_rerank_client(settings),
        engine=engine,
    )
    return RecommendService(
        retriever=retriever,
        llm=build_llm_client(settings),
        settings=settings,
        details_reader=SqlRecipeDetailsReader(engine),
    )


async def get_recommend_service(settings: AppSettings) -> RecommendService:
    """进程内复用的 ``RecommendService``（惰性单例，按 settings 实例缓存）。"""
    key = id(settings)
    cached = _services.get(key)
    if cached is not None:
        return cached
    async with _lock():
        cached = _services.get(key)
        if cached is None:
            cached = await _build_service(settings)
            _services[key] = cached
    return cached


def get_recipe_page_service() -> RecipePageService:
    return RecipePageService(SqlRecipeDetailsReader(get_engine()))


async def close_recommend_service() -> None:
    """应用关闭时释放装配出来的 HTTP 连接池（失败只记日志，不影响退出）。"""
    services = list(_services.values())
    _services.clear()
    for service in services:
        for attr in ("_retriever", "_llm"):
            closer = getattr(getattr(service, attr, None), "aclose", None)
            if closer is None:
                continue
            try:
                await closer()
            except Exception as exc:  # noqa: BLE001 - 关闭失败不能阻塞进程退出
                logger.warning("释放 %s 连接池失败：%s", attr, type(exc).__name__)


def reset_recommend_service() -> None:
    """清空单例缓存（测试用，避免用例之间互相污染）。"""
    _services.clear()
