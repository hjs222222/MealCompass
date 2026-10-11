"""`api/deps.py` 的单测：装配、惰性单例、关闭路径。

`api/deps.py` 是**唯一允许 new 出具体实现**的地方（分层规则里的装配点），
所以它一旦写错，错的是整个进程的装配方式，而不是某个请求。三处值得测：

1. `get_app_settings` / `tracing_degraded` —— 纯函数，但被 `AppSettings` 依赖注入引用；
2. `_build_service` —— 真装配链条（engine → CardCorpus → HybridRetriever → RecommendService）。
   这里**把三个 build_* 与 load_card_documents 全部替换成假对象**，所以不连库、不连网，
   但**真实执行 dpes 自己的装配顺序与参数传递**（如果它漏传 reranker，测试会红）；
3. `close_recommend_service` —— 关闭失败**只能记日志**，不能让进程退出失败（except 分支）。
"""

from __future__ import annotations

from typing import Any

import pytest

import api.deps as deps
from core.config import Settings

SETTINGS = Settings(_env_file=None, llm_model="fake-model")


@pytest.fixture(autouse=True)
def _clean_singletons() -> Any:
    deps.reset_recommend_service()
    deps._build_lock = None
    yield
    deps.reset_recommend_service()
    deps._build_lock = None


# ------------------------------------------------------------------ 纯函数


def test_get_app_settings_returns_process_settings() -> None:
    assert deps.get_app_settings() is deps.get_settings()


def test_tracing_degraded_mirrors_settings() -> None:
    """未配 key → 视为降级；配齐两个 key → 不降级。

    ⚠️ 必须显式传 `langfuse_public_key=None`：`infra/observability.py` 的启用路径会往
    `os.environ` 写这两个变量，而 pydantic-settings 的 `_env_file=None` **只关掉 .env 文件**，
    关不掉真实环境变量。不显式置空的话，本用例会在大全量跑时被前一个用例"污染成已配置"。
    """
    assert deps.tracing_degraded(Settings(_env_file=None, langfuse_public_key=None, langfuse_secret_key=None)) is True
    assert deps.tracing_degraded(Settings(_env_file=None, langfuse_public_key="pk", langfuse_secret_key="sk")) is False


def test_lock_is_lazy_and_reused() -> None:
    """`asyncio.Lock` 必须在事件循环内创建（模块 import 时 new 会绑到错误的 loop），所以要惰性。"""
    first = deps._lock()
    assert first is deps._lock()


# ------------------------------------------------------------------ _build_service 真实装配


class _FakeConn:
    async def __aenter__(self) -> _FakeConn:
        return self

    async def __aexit__(self, *_: Any) -> bool:
        return False


class _FakeEngine:
    def __init__(self) -> None:
        self.connects = 0

    def connect(self) -> _FakeConn:
        self.connects += 1
        return _FakeConn()


class _FakeCorpus:
    def __init__(self, documents: list[str]) -> None:
        self.documents = documents


class _FakeRetriever:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


class _FakeLLM:
    model = "fake-model"

    def __init__(self) -> None:
        self.closed = 0

    async def aclose(self) -> None:
        self.closed += 1


async def test_build_service_wires_every_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    """真装配链：engine 建连接 → 载 corpus → 造 retriever（embedder/corpus/reranker/engine）→ service。"""
    engine = _FakeEngine()
    embedder = object()
    reranker = object()
    llm = _FakeLLM()
    seen: dict[str, Any] = {}

    async def fake_load(conn: Any) -> list[str]:
        seen["conn"] = conn
        return ["card-a", "card-b"]

    def fake_retriever(**kwargs: Any) -> _FakeRetriever:
        seen["retriever_kwargs"] = kwargs
        return _FakeRetriever(**kwargs)

    monkeypatch.setattr(deps, "get_engine", lambda: engine)
    monkeypatch.setattr(deps, "load_card_documents", fake_load)
    monkeypatch.setattr(deps, "CardCorpus", _FakeCorpus)
    monkeypatch.setattr(deps, "HybridRetriever", fake_retriever)
    monkeypatch.setattr(deps, "build_embedding_client", lambda settings: embedder)
    monkeypatch.setattr(deps, "build_rerank_client", lambda settings: reranker)
    monkeypatch.setattr(deps, "build_llm_client", lambda settings: llm)

    service = await deps._build_service(SETTINGS)

    assert engine.connects == 1
    assert isinstance(seen["conn"], _FakeConn)
    kwargs = seen["retriever_kwargs"]
    assert kwargs["embedder"] is embedder
    assert kwargs["reranker"] is reranker  # 漏传 reranker 会静默退化成"无重排"
    assert kwargs["engine"] is engine
    assert isinstance(kwargs["corpus"], _FakeCorpus)
    assert kwargs["corpus"].documents == ["card-a", "card-b"]
    assert service.settings is SETTINGS


async def test_build_service_does_not_connect_when_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    """第二次调用直接命中缓存：**不得再次建连接、再次载 corpus**（这是进程级重活）。"""
    engine = _FakeEngine()
    builds = 0

    async def fake_load(conn: Any) -> list[str]:
        del conn
        return []

    def fake_retriever(**kwargs: Any) -> _FakeRetriever:
        nonlocal builds
        builds += 1
        return _FakeRetriever(**kwargs)

    monkeypatch.setattr(deps, "get_engine", lambda: engine)
    monkeypatch.setattr(deps, "load_card_documents", fake_load)
    monkeypatch.setattr(deps, "CardCorpus", _FakeCorpus)
    monkeypatch.setattr(deps, "HybridRetriever", fake_retriever)
    monkeypatch.setattr(deps, "build_embedding_client", lambda settings: object())
    monkeypatch.setattr(deps, "build_rerank_client", lambda settings: object())
    monkeypatch.setattr(deps, "build_llm_client", lambda settings: _FakeLLM())

    first = await deps.get_recommend_service(SETTINGS)
    second = await deps.get_recommend_service(SETTINGS)

    assert first is second
    assert engine.connects == 1
    assert builds == 1


# ------------------------------------------------------------------ 关闭路径


async def test_close_recommend_service_closes_retriever_and_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    retriever = _FakeRetriever()
    llm = _FakeLLM()

    async def fake_build(settings: Settings) -> Any:
        del settings
        return deps.RecommendService(retriever=retriever, llm=llm, settings=SETTINGS)

    monkeypatch.setattr(deps, "_build_service", fake_build)
    await deps.get_recommend_service(SETTINGS)

    await deps.close_recommend_service()

    assert retriever.closed == 1
    assert llm.closed == 1
    assert deps._services == {}  # 缓存必须清空，否则下次复用到已关闭的连接池


async def test_close_recommend_service_swallows_closer_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """关闭失败只记日志：**应用退出不能因为一个 HTTP 池关不掉而失败**。"""

    class _ExplodingRetriever:
        async def aclose(self) -> None:
            raise RuntimeError("池已经坏了")

    service = deps.RecommendService(retriever=_ExplodingRetriever(), llm=_FakeLLM(), settings=SETTINGS)
    deps._services[id(SETTINGS)] = service

    await deps.close_recommend_service()  # 不抛即通过
    assert deps._services == {}


async def test_close_recommend_service_skips_objects_without_aclose() -> None:
    """依赖可能没有 `aclose`（例如注入的假对象），必须跳过而不是 AttributeError。"""

    class _NoClose:
        pass

    service = deps.RecommendService(retriever=_NoClose(), llm=_NoClose(), settings=SETTINGS)
    deps._services[id(SETTINGS)] = service

    await deps.close_recommend_service()
    assert deps._services == {}


def test_reset_recommend_service_clears_cache() -> None:
    deps._services[id(SETTINGS)] = None  # type: ignore[assignment]
    deps.reset_recommend_service()
    assert deps._services == {}
