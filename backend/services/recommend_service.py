"""推荐 / 检索业务编排（PRD F-C3 / F-C4 的对外用例）。

职责边界：
- ``RecommendService`` 只依赖 **Protocol**（``domain.ports.Retriever`` / ``LLMClient``），
  不依赖 ``HybridRetriever`` / ``RemoteLLM`` 具体实现——API 层负责装配。
- 根观察固定为 ``SpanName.RECOMMEND_REQUEST``（请求级 trace），推荐与纯检索共用同一个根观察名：
  观察名必须来自 ``SpanName``（禁止手写字符串），而常量表里没有独立的 "search-request"，与其编一个
  不存在的名字，不如复用请求级根观察并把「这是什么请求」放进 metadata。
- 根观察的 input 只放 ``{"query": ..., "has_hard_filters": ...}``，output 只放菜名列表：
  CONVENTIONS §4.5 要求「不要把整个函数参数塞进 input」，用户忌口等敏感信息不进 trace。
- 任何 LLM / 网络异常都已在 ``agents`` 节点内降级；这里再兜一层检索异常，保证接口不返回 5xx。
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from agents.graph import AgentDeps, run_agent
from agents.state import DEGRADATION_RETRIEVAL_DEGRADED, DEGRADATION_RETRIEVAL_FAILED
from core.config import Settings, get_settings
from core.exceptions import request_id_context
from domain.models.recommend import RecommendRequest, RecommendResponse, SearchRequest, SearchResponse
from domain.models.retrieval import HardFilters
from domain.ports import RecipeDetailsReader, RecipeStepsReader
from infra.observability import SpanName, attributes, traced

logger = logging.getLogger(__name__)

#: 纯检索也记请求级根观察（见模块 docstring 的取舍说明）
ROOT_OBSERVATION = SpanName.RECOMMEND_REQUEST

#: 推荐场景沿用 PRD F-C3 的固定条数上限（模型层已把 top_k 约束在 1..5）
DEFAULT_RECOMMEND_TOP_K = 3


def _filters_from(
    *,
    max_time_minutes: int | None,
    tools_available: Sequence[str],
    excluded_ingredients: Sequence[str],
    category: str | None = None,
) -> HardFilters:
    """请求字段 → 硬约束模型（硬约束只由规则决定，LLM 不参与判定）。"""
    return HardFilters(
        max_time_minutes=max_time_minutes,
        tools_available=list(tools_available),
        excluded_ingredients=list(excluded_ingredients),
        category=category,
    )


def _recipe_names(items: Sequence[Any]) -> list[str]:
    """根观察 output 只用菜名（用户看得懂、低基数、不含 recipe_id 之外的动态值）。"""
    return [getattr(item, "name", "") for item in items]


class RecommendService:
    """一次推荐 / 检索请求的编排入口。"""

    def __init__(
        self,
        *,
        retriever: Any,
        llm: Any,
        settings: Settings | None = None,
        steps_reader: RecipeStepsReader | None = None,
        details_reader: RecipeDetailsReader | None = None,
    ) -> None:
        self._retriever = retriever
        self._llm = llm
        self._settings = settings or get_settings()
        self._steps_reader = steps_reader
        self._details_reader = details_reader

    @property
    def settings(self) -> Settings:
        """当前配置（只读，便于测试与调试）。"""
        return self._settings

    def _session_id(self, session_id: str | None) -> str:
        """trace 的 session：优先调用方给的会话 id，其次 HTTP request id，最后新生成。"""
        return session_id or request_id_context.get() or str(uuid4())

    async def recommend(self, request: RecommendRequest, *, session_id: str | None = None) -> RecommendResponse:
        """跑完整 Agent 闭环：解析意图 → 混合检索 → 生成 → 引用校验。"""
        filters = _filters_from(
            max_time_minutes=request.max_time_minutes,
            tools_available=request.tools_available,
            excluded_ingredients=request.excluded_ingredients,
            category=request.category,
        )
        deps = AgentDeps(retriever=self._retriever, llm=self._llm, settings=self._settings)

        with traced(
            ROOT_OBSERVATION,
            input={"query": request.query, "has_hard_filters": not filters.is_empty()},
        ) as root:
            with attributes(session_id=self._session_id(session_id)):
                response = await run_agent(
                    request.query,
                    filters,
                    deps=deps,
                    top_k=min(request.top_k, DEFAULT_RECOMMEND_TOP_K + 2),
                )
            root.update(
                output={
                    "recipes": _recipe_names(response.recommendations),
                    "no_solution_reason": response.no_solution_reason,
                    "degraded": response.degraded,
                },
                metadata={"node_path": response.node_path},
            )
        if response.recommendations and self._details_reader is not None:
            try:
                recipe_ids = [item.recipe_id for item in response.recommendations]
                detail_map = await self._details_reader.get_details(recipe_ids)
            except Exception as exc:  # noqa: BLE001 - source details must not invalidate safe recommendations
                logger.warning("读取菜谱详情失败：%s", type(exc).__name__)
                response = response.model_copy(
                    update={
                        "degraded": True,
                        "degradations": [*response.degradations, "recipe_details_unavailable"],
                    }
                )
            else:
                response = response.model_copy(
                    update={
                        "recommendations": [
                            item.model_copy(
                                update={
                                    "details": detail_map.get(item.recipe_id),
                                    "steps": detail_map[item.recipe_id].steps if item.recipe_id in detail_map else [],
                                }
                            )
                            for item in response.recommendations
                        ]
                    }
                )
        elif response.recommendations and self._steps_reader is not None:
            try:
                step_map = await self._steps_reader.get_steps([item.recipe_id for item in response.recommendations])
            except Exception as exc:  # noqa: BLE001 - details must not turn a valid recommendation into 500
                logger.warning("读取菜谱步骤失败：%s", type(exc).__name__)
                response = response.model_copy(
                    update={
                        "degraded": True,
                        "degradations": [*response.degradations, "recipe_steps_unavailable"],
                    }
                )
            else:
                response = response.model_copy(
                    update={
                        "recommendations": [
                            item.model_copy(update={"steps": step_map.get(item.recipe_id, [])})
                            for item in response.recommendations
                        ]
                    }
                )
        return response

    async def search(self, request: SearchRequest, *, session_id: str | None = None) -> SearchResponse:
        """纯检索：返回带真实 ``recipe_id`` 的候选，便于前端「先看候选」与评估复用。"""
        filters = _filters_from(
            max_time_minutes=request.max_time_minutes,
            tools_available=request.tools_available,
            excluded_ingredients=request.excluded_ingredients,
            category=request.category,
        )
        degradations: list[str] = []

        with traced(
            ROOT_OBSERVATION,
            input={"query": request.query, "has_hard_filters": not filters.is_empty()},
        ) as root:
            with attributes(session_id=self._session_id(session_id)):
                try:
                    candidates = list(await self._retriever.search(request.query, filters, request.top_k))
                except Exception as exc:  # noqa: BLE001 - 检索异常不能把 500 抛给用户
                    logger.warning("纯检索失败，返回空候选：%s", type(exc).__name__)
                    candidates = []
                    degradations.append(DEGRADATION_RETRIEVAL_FAILED)
                else:
                    if any(candidate.degraded for candidate in candidates):
                        degradations.append(DEGRADATION_RETRIEVAL_DEGRADED)
            root.update(output={"recipes": _recipe_names(candidates)})

        return SearchResponse(
            query=request.query,
            candidates=candidates,
            degraded=bool(degradations),
            degradations=degradations,
        )
