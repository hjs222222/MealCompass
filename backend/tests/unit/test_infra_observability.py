"""`infra/observability.py` 的单测：**降级路径**与**启用路径**都要覆盖。

为什么这个文件值得单独测：

1. **可观测性绝不能拖垮主流程**——`configure()` 失败必须降级为 no-op，而不是抛异常。
   这条承诺只有测试能守住。
2. 每条 `if configure():` 都有两个分支，之前只跑了"未配置 key"的那一支（75% 覆盖率）。
3. `_ready` 是模块级缓存，所以每个用例都必须重置，否则用例之间会互相污染——
   这一点本身就是容易写错的地方。

测启用路径时**注入假 langfuse 模块**，不打真网络、不需要 key。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from core.config import Settings
from infra import observability as obs


@pytest.fixture(autouse=True)
def _reset_obs_module_state() -> Iterator[None]:
    """清掉模块级缓存 + `LANGFUSE_*` 环境变量，让 `configure()` 在每个用例里都能重新决策。

    **环境变量这一半是必须的**：`configure()` 启用路径会写 `os.environ`，而
    pydantic-settings 的 `_env_file=None` 只关 `.env` 文件、关不掉真实环境变量。
    不清理就会出现「前面的用例配了 key，后面的用例被当成已配置」这种顺序依赖 bug。
    """
    keys = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST", "LANGFUSE_BASE_URL")
    saved = {key: obs.os.environ.get(key) for key in keys}
    obs._client = None
    obs._module = None
    obs._ready = False
    obs._degraded_reason = None
    for key in keys:
        obs.os.environ.pop(key, None)
    yield
    obs._client = None
    obs._module = None
    obs._ready = False
    obs._degraded_reason = None
    for key, value in saved.items():
        if value is None:
            obs.os.environ.pop(key, None)
        else:
            obs.os.environ[key] = value


def _settings(**overrides: Any) -> Settings:
    """构造不读 `.env` 的 Settings，并把 langfuse 两个 key 显式置空。

    ⚠️ 两个坑叠在一起，必须同时处理：

    1. `_env_file=None` 只关掉 `.env` **文件**，**关不掉真实环境变量**；
    2. `configure()` 启用路径会往 `os.environ` 里写 `LANGFUSE_PUBLIC_KEY` / `_SECRET_KEY`。

    所以只要 "启用路径" 的用例先跑，后面的用例就会**从环境变量里捡到上一个用例留下的 key**，
    变成"配了 key 的人"。这里显式传 `None`（初始化参数优先级最高）来彻底隔离。
    """
    overrides.setdefault("langfuse_public_key", None)
    overrides.setdefault("langfuse_secret_key", None)
    return Settings(_env_file=None, **overrides)


# --------------------------------------------------------------------------- #
# 未配置 key：整体降级为 no-op（这是默认开发态）
# --------------------------------------------------------------------------- #


def test_configure_returns_false_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(obs, "get_settings", lambda: _settings())
    assert obs.configure() is False
    assert obs.degraded_reason() == "LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 未配置"


def test_configure_only_needs_one_key_missing_to_degrade(monkeypatch: pytest.MonkeyPatch) -> None:
    """只配了 public key 也必须降级（半配置比没配更危险：会拿到 401 空 trace）。"""
    monkeypatch.setattr(obs, "get_settings", lambda: _settings(langfuse_public_key="pk"))
    assert obs.configure() is False


def test_configure_caches_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    """`_ready` 命中后必须直接返回缓存结果，不重复读配置。"""
    monkeypatch.setattr(obs, "get_settings", lambda: _settings())
    assert obs.configure() is False
    monkeypatch.setattr(obs, "get_settings", lambda: _settings(langfuse_public_key="pk", langfuse_secret_key="sk"))
    assert obs.configure() is False  # 仍走缓存，不因配置变化而改变


def test_enabled_and_client_and_degraded_reason_are_consistent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(obs, "get_settings", lambda: _settings())
    assert obs.enabled() is False
    assert obs.get_langfuse_client() is None
    assert obs.degraded_reason() is not None


def test_null_observation_is_chainable_and_silent() -> None:
    """no-op 对象必须支持 `.update()` 链式调用与 `.end()` / `.score()`，否则调用点要写分支。"""
    null = obs._NullObservation("x")
    assert null.name == "x"
    assert null.update(output=1) is null
    assert null.end() is null
    assert null.score("faithfulness", 0.9) is None


def test_traced_yields_null_observation_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(obs, "get_settings", lambda: _settings())
    with obs.traced(obs.SpanName.RECOMMEND_REQUEST, input={"query": "x"}) as span:
        assert isinstance(span, obs._NullObservation)
        span.update(output={"recipes": []})


def test_attributes_is_noop_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(obs, "get_settings", lambda: _settings())
    with obs.attributes(user_id="u1", session_id="s1"):
        pass  # 不抛即通过


def test_update_span_and_current_trace_id_and_score_and_flush_are_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(obs, "get_settings", lambda: _settings())
    assert obs.update_span(output={}) is None
    assert obs.current_trace_id() is None
    assert obs.score_current_trace("mrr", 0.74) is None
    assert obs.flush() is None
    assert obs.shutdown() is None


def test_span_name_constants_are_stable_contract() -> None:
    """观察名是**对外契约**（看板/评估器按名字匹配），改名会静默破坏已保存的过滤器。

    这里刻意把字符串写死在测试里：一旦有人"顺手重命名"，测试会立刻红，
    逼迫他去看 `docs/CONVENTIONS.md` 的观察名表。
    """
    assert obs.SpanName.RECOMMEND_REQUEST == "recommend-request"
    assert obs.SpanName.PARSE_INTENT == "parse-intent"
    assert obs.SpanName.RETRIEVE_RECIPES == "retrieve-recipes"
    assert obs.SpanName.GENERATE_RECOMMENDATIONS == "generate-recommendations"
    assert obs.SpanName.REFLECT_VALIDATE == "reflect-validate"
    assert obs.SpanName.EVAL_RETRIEVAL == "eval-retrieval"
    assert obs.SpanName.EVAL_FAITHFULNESS == "eval-faithfulness"
    # LLM 调用必须是 generation，否则 Langfuse 的成本/Token 视图为空
    assert obs.ObservationType.GENERATION == "generation"


# --------------------------------------------------------------------------- #
# 启用路径：注入假 langfuse 模块
# --------------------------------------------------------------------------- #


class _FakeObservation:
    def __init__(self, name: str) -> None:
        self.name = name
        self.updates: list[dict[str, Any]] = []
        self.ended = False

    def update(self, **kwargs: Any) -> _FakeObservation:
        self.updates.append(kwargs)
        return self

    def end(self, **kwargs: Any) -> _FakeObservation:
        self.ended = True
        return self


class _FakeClient:
    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []
        self.trace_id = "trace-abc"

    @contextmanager
    def start_as_current_observation(self, **kwargs: Any) -> Iterator[_FakeObservation]:
        self.started.append(kwargs)
        yield _FakeObservation(str(kwargs.get("name", "")))


class _FakeLangfuseModule:
    """假模块：只提供 observability.py 用到的两个符号。"""

    def __init__(self, client: _FakeClient) -> None:
        self._client = client
        self.propagate_calls: list[dict[str, Any]] = []

    def get_client(self) -> _FakeClient:
        return self._client

    @contextmanager
    def propagate_attributes(self, **kwargs: Any) -> Iterator[None]:
        self.propagate_calls.append(kwargs)
        yield None


@pytest.fixture
def enabled(monkeypatch: pytest.MonkeyPatch) -> tuple[_FakeClient, _FakeLangfuseModule]:
    """把 `configure()` 打到启用态，并返回假 client / 假模块供断言。

    **同时负责还原 `os.environ`**：启用路径会写入真实的 `LANGFUSE_*` 变量，
    不还原就会污染同进程里的其它用例（本项目真实踩过：大全量跑时报 6 个假失败）。
    """
    keys = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST", "LANGFUSE_BASE_URL")
    saved = {key: obs.os.environ.get(key) for key in keys}
    monkeypatch.setattr(
        obs,
        "get_settings",
        lambda: _settings(langfuse_public_key="pk", langfuse_secret_key="sk"),
    )
    client = _FakeClient()
    module = _FakeLangfuseModule(client)
    monkeypatch.setattr(obs.importlib, "import_module", lambda name: module if name == "langfuse" else None)
    assert obs.configure() is True
    yield client, module
    for key, value in saved.items():
        if value is None:
            obs.os.environ.pop(key, None)
        else:
            obs.os.environ[key] = value


def test_configure_sets_env_before_importing_sdk(enabled: tuple[_FakeClient, _FakeLangfuseModule]) -> None:
    """顺序契约：先写环境变量，再 import langfuse（否则 SDK 用空凭证初始化）。"""
    import os

    assert os.environ["LANGFUSE_PUBLIC_KEY"] == "pk"
    assert os.environ["LANGFUSE_SECRET_KEY"] == "sk"


def test_configure_degrades_when_import_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """SDK 缺失 / 初始化炸了也必须降级，不能把主流程带崩。"""
    monkeypatch.setattr(obs, "get_settings", lambda: _settings(langfuse_public_key="pk", langfuse_secret_key="sk"))

    def boom(name: str) -> Any:
        raise ImportError("模拟 langfuse 缺失")

    monkeypatch.setattr(obs.importlib, "import_module", boom)
    assert obs.configure() is False
    assert "初始化失败" in (obs.degraded_reason() or "")
    assert obs.get_langfuse_client() is None


def test_enabled_true_and_client_returned(enabled: tuple[_FakeClient, _FakeLangfuseModule]) -> None:
    client, _ = enabled
    assert obs.enabled() is True
    assert obs.get_langfuse_client() is client


def test_traced_passes_type_and_name_to_sdk(enabled: tuple[_FakeClient, _FakeLangfuseModule]) -> None:
    client, _ = enabled
    with obs.traced(
        obs.SpanName.GENERATE_RECOMMENDATIONS,
        as_type=obs.ObservationType.GENERATION,
        model="deepseek-ai/DeepSeek-V3",
        input={"query": "x"},
    ) as span:
        span.update(output="ok", usage_details={"input_tokens": 1, "output_tokens": 2})
    assert client.started[0]["name"] == "generate-recommendations"
    assert client.started[0]["as_type"] == "generation"
    assert client.started[0]["model"] == "deepseek-ai/DeepSeek-V3"


def test_attributes_propagates_when_enabled(enabled: tuple[_FakeClient, _FakeLangfuseModule]) -> None:
    _, module = enabled
    with obs.attributes(user_id="u1", session_id="s1", metadata={"has_hard_filters": True}):
        pass
    assert module.propagate_calls[0]["user_id"] == "u1"
    assert module.propagate_calls[0]["session_id"] == "s1"


def test_update_span_current_trace_id_flush_shutdown_when_enabled(
    enabled: tuple[_FakeClient, _FakeLangfuseModule], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = enabled
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(client, "update_current_span", lambda **kw: calls.append(kw), raising=False)
    monkeypatch.setattr(client, "get_current_trace_id", lambda: client.trace_id, raising=False)
    monkeypatch.setattr(client, "score_current_trace", lambda **kw: calls.append(kw), raising=False)
    monkeypatch.setattr(client, "flush", lambda: calls.append({"flush": True}), raising=False)
    monkeypatch.setattr(client, "shutdown", lambda: calls.append({"shutdown": True}), raising=False)

    obs.update_span(output={"recipes": ["西红柿炒鸡蛋"]})
    assert obs.current_trace_id() == "trace-abc"
    obs.score_current_trace("retrieval_recall", 0.6375)
    obs.flush()
    obs.shutdown()

    assert {"output": {"recipes": ["西红柿炒鸡蛋"]}} in calls
    assert {"name": "retrieval_recall", "value": 0.6375} in calls
    assert {"flush": True} in calls
    assert {"shutdown": True} in calls
