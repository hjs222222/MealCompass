"""Langfuse 可观测层：全项目唯一的 tracing 出口。

设计约束（来自 Langfuse 官方 best practices + `langfuse` skill）：

1. **先加载 `.env`，再 import `langfuse`** —— import 早于环境变量加载，SDK 会用空凭证初始化。
2. 未配置 key 时整体降级为 no-op，本地开发不被可观测性阻塞（远程优先、本地兜底）。
3. **观察名是稳定 API**：动词开头、低基数、不含动态值；动态信息一律进 metadata。
   改名会让评估器、看板、过滤器静默失效。
4. 每个 trace 必须有可读的 input / output；不要把整个函数参数塞进 input。
5. 短生命周期进程（脚本、serverless）结束前必须 ``flush()``，否则 trace 不会发送。
6. 敏感数据（API key、密码、完整用户身份）绝不进 trace。

用法::

    from infra.observability import SpanName, ObservationType, attributes, flush, traced

    with traced(SpanName.RECOMMEND_REQUEST, input={"query": user_input}) as root:
        with attributes(user_id=user_id, session_id=conv_id):
            with traced(SpanName.GENERATE_RECOMMENDATIONS,
                        as_type=ObservationType.GENERATION, model=settings.llm_model) as gen:
                gen.update(output=..., usage_details={"input_tokens": 12, "output_tokens": 88})
        root.update(output={"recipes": [...]})
    flush()
"""

from __future__ import annotations

import importlib
import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

from core.config import Settings, get_settings

logger = logging.getLogger(__name__)

_client: Any = None
_module: Any = None
_ready = False
_degraded_reason: str | None = None


class ObservationType:
    """Langfuse observation 类型；类型选错会让模型/成本/Agent Graph 视图失效。"""

    SPAN = "span"
    GENERATION = "generation"
    RETRIEVER = "retriever"
    TOOL = "tool"
    AGENT = "agent"
    CHAIN = "chain"
    EMBEDDING = "embedding"
    EVALUATOR = "evaluator"
    GUARDRAIL = "guardrail"


class SpanName:
    """观察名常量表。

    ⚠️ 这些字符串是**对外契约**（评估器、看板、保存的过滤器都按名字匹配）。
    改名 = 破坏性变更，必须同步更新 `docs/CONVENTIONS.md` 的观察名表。
    """

    # 根观察：一次推荐请求 = 一个 trace
    RECOMMEND_REQUEST = "recommend-request"

    # 与 LangGraph 节点一一对应
    PARSE_INTENT = "parse-intent"
    CLARIFY_REQUEST = "clarify-request"
    RETRIEVE_RECIPES = "retrieve-recipes"
    RERANK_RECIPES = "rerank-recipes"
    FILTER_HARD_CONSTRAINTS = "apply-hard-constraints"
    GENERATE_RECOMMENDATIONS = "generate-recommendations"
    REFLECT_VALIDATE = "reflect-validate"

    # 工具调用
    TOOL_SEARCH_RECIPES = "tool-search-recipes"
    TOOL_GET_RECIPE = "tool-get-recipe"
    TOOL_SUBSTITUTE_INGREDIENT = "tool-substitute-ingredient"
    TOOL_SCALE_RECIPE = "tool-scale-recipe"
    TOOL_BUILD_SHOPPING_LIST = "tool-build-shopping-list"

    # 离线评估
    EVAL_RETRIEVAL = "eval-retrieval"
    EVAL_FAITHFULNESS = "eval-faithfulness"


class _NullObservation:
    """未启用 tracing 时的占位对象，保证调用方代码不需要任何分支。"""

    def __init__(self, name: str) -> None:
        self.name = name

    def update(self, **_: Any) -> "_NullObservation":
        return self

    def end(self, **_: Any) -> "_NullObservation":
        return self

    def score(self, *_: Any, **__: Any) -> None:
        return None


def configure(settings: Settings | None = None) -> bool:
    """写环境变量并初始化 Langfuse 客户端；返回是否真正启用了 tracing。"""
    global _client, _module, _ready, _degraded_reason

    if _ready:
        return _client is not None
    _ready = True

    settings = settings or get_settings()
    if not settings.tracing_enabled:
        _degraded_reason = "LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 未配置"
        logger.info("Langfuse tracing 未启用（%s），降级为 no-op", _degraded_reason)
        return False

    # ⚠️ 必须在 import langfuse 之前写好：SDK 在 import / get_client 时读取这些变量
    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key or ""
    os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key or ""
    os.environ["LANGFUSE_HOST"] = settings.langfuse_base_url
    os.environ["LANGFUSE_BASE_URL"] = settings.langfuse_base_url
    os.environ.setdefault("LANGFUSE_TRACING_ENVIRONMENT", settings.langfuse_tracing_environment)

    try:
        _module = importlib.import_module("langfuse")
        _client = _module.get_client()
    except Exception as exc:  # noqa: BLE001 - 可观测性绝不能让主流程挂掉
        _degraded_reason = f"初始化失败：{exc}"
        logger.warning("Langfuse 初始化失败（%s），降级为 no-op", exc)
        _client = None
        return False

    logger.info(
        "Langfuse tracing 已启用：host=%s env=%s",
        settings.langfuse_base_url,
        settings.langfuse_tracing_environment,
    )
    return True


def enabled() -> bool:
    """当前是否真的会发送 trace。"""
    return configure()


def get_langfuse_client() -> Any:
    """返回 Langfuse 客户端；未启用时返回 None。

    业务代码要读 trace 数据时用它，不要自己 new 客户端。
    注意：新组织必须走 **Observations API v2**（``client.api.observations``），
    旧的 ``/api/public/traces`` 对 2026-09-16 之后创建的组织已返回 410。
    """
    return _client if configure() else None


def degraded_reason() -> str | None:
    """返回降级原因，便于启动日志与健康检查说明。"""
    configure()
    return _degraded_reason


@contextmanager
def traced(
    name: str,
    as_type: str = ObservationType.SPAN,
    **kwargs: Any,
) -> Iterator[Any]:
    """创建一个 observation 并设为当前上下文；未启用时返回 no-op 对象。"""
    if configure():
        with _client.start_as_current_observation(as_type=as_type, name=name, **kwargs) as observation:
            yield observation
    else:
        yield _NullObservation(name)


@contextmanager
def attributes(**kwargs: Any) -> Iterator[None]:
    """给当前 trace / 子观察挂属性：user_id、session_id、metadata、version、environment、trace_name。

    未启用 tracing 时为空操作。
    """
    if configure():
        propagate_attributes = getattr(_module, "propagate_attributes")
        with propagate_attributes(**kwargs):
            yield
    else:
        yield


def update_span(**kwargs: Any) -> None:
    """更新当前活动 observation（无需持有引用）。"""
    if configure():
        _client.update_current_span(**kwargs)


def current_trace_id() -> str | None:
    """当前 trace id，便于把业务日志与 Langfuse 对齐。"""
    if configure():
        return _client.get_current_trace_id()
    return None


def score_current_trace(name: str, value: float, **kwargs: Any) -> None:
    """给当前 trace 打分（用户反馈、离线评估都走这里）。"""
    if configure():
        _client.score_current_trace(name=name, value=value, **kwargs)


def flush() -> None:
    """短生命周期进程结束前必须调用，否则缓冲的 trace 不会发送。"""
    if configure():
        _client.flush()


def shutdown() -> None:
    """优雅关闭：flush + 等待后台线程退出。"""
    if configure():
        _client.shutdown()
