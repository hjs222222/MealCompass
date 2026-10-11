"""LangGraph 组装与对外入口（PRD F-C6：状态机编排）。

拓扑::

    START → parse → search ─┬─ 无候选 → no_solution → END
                            └─ 有候选 → generate → validate → END

设计说明：

- **LangGraph 1.x 不含依赖注入**：``add_node`` 只接受 ``(state)`` / ``(state, runtime)`` 签名，节点自身
  需要 ``deps``，因此这里用 ``functools.partial`` 绑定。节点仍是可直接调用、可单测的纯函数。
- **checkpointer 可选且不默认**：CONVENTIONS §4.2 禁止 ``MemorySaver``，所以 ``None`` 时**不传**
  ``checkpointer`` 参数给 ``compile``（也不附带 thread_id 配置），调用方显式传入实现时原样透传。
- **降级不靠图**：每个节点内部已经「绝不抛异常」，条件边只负责「有候选 / 无候选」这一个业务分支。
- ``node_parse`` 的查询解析与硬约束来源：请求里显式给的 ``filters`` 优先，LLM 只补空缺。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Any

from langgraph.graph import END, START, StateGraph

from agents.nodes import node_generate, node_no_solution, node_parse, node_search, node_validate
from agents.state import NODE_GENERATE, NODE_NO_SOLUTION, NODE_PARSE, NODE_SEARCH, NODE_VALIDATE, AgentState
from core.config import Settings, get_settings
from domain.models.recommend import RecommendResponse
from domain.models.retrieval import HardFilters
from infra.observability import current_trace_id

DEFAULT_TOP_K = 3


@dataclass
class AgentDeps:
    """Agent 节点依赖（构造期注入，便于用假实现单测）。

    - ``retriever``：任何满足 ``domain.ports.Retriever`` 的实现（生产是 ``HybridRetriever``）。
    - ``llm``：任何满足 ``domain.ports.LLMClient`` 的实现（生产是 ``RemoteLLM``）。
    - ``settings``：仅用于读取配置，不参与业务判断。
    """

    retriever: Any
    llm: Any
    settings: Settings


def _route_after_search(state: AgentState) -> str:
    """条件边：有候选去生成，无候选走无解出口（绝不编造菜谱）。"""
    return NODE_GENERATE if state.get("candidates") else NODE_NO_SOLUTION


def build_graph(deps: AgentDeps, *, checkpointer: Any = None) -> Any:
    """组装并编译 Agent 图；``checkpointer`` 为 ``None`` 时不使用任何 checkpointer。"""
    builder = StateGraph(AgentState)
    builder.add_node(NODE_PARSE, partial(node_parse, deps=deps))
    builder.add_node(NODE_SEARCH, partial(node_search, deps=deps))
    builder.add_node(NODE_GENERATE, partial(node_generate, deps=deps))
    builder.add_node(NODE_VALIDATE, partial(node_validate, deps=deps))
    builder.add_node(NODE_NO_SOLUTION, partial(node_no_solution, deps=deps))

    builder.add_edge(START, NODE_PARSE)
    builder.add_edge(NODE_PARSE, NODE_SEARCH)
    builder.add_conditional_edges(
        NODE_SEARCH,
        _route_after_search,
        {NODE_GENERATE: NODE_GENERATE, NODE_NO_SOLUTION: NODE_NO_SOLUTION},
    )
    builder.add_edge(NODE_GENERATE, NODE_VALIDATE)
    builder.add_edge(NODE_VALIDATE, END)
    builder.add_edge(NODE_NO_SOLUTION, END)

    if checkpointer is None:
        return builder.compile()
    return builder.compile(checkpointer=checkpointer)


async def run_agent(
    query: str,
    filters: HardFilters | None = None,
    *,
    deps: AgentDeps,
    top_k: int = DEFAULT_TOP_K,
    thread_id: str | None = None,
) -> RecommendResponse:
    """跑一次 Agent 闭环，返回可被 API 层直接序列化的 ``RecommendResponse``。

    ``thread_id`` 只在调用方传了 checkpointer 时生效（无 checkpointer 时传 thread_id 会被 LangGraph 拒绝）。
    """
    graph = build_graph(deps)
    initial: AgentState = {"query": query, "filters": filters or HardFilters(), "top_k": top_k}
    config = {"configurable": {"thread_id": thread_id}} if thread_id else None
    final = await graph.ainvoke(initial, config)

    recommendations = list(final.get("recommendations") or [])
    candidates = list(final.get("candidates") or [])
    degradations = list(final.get("degradations") or [])

    return RecommendResponse(
        query=query,
        recommendations=recommendations,
        candidates_considered=len(candidates),
        no_solution_reason=final.get("no_solution_reason"),
        degraded=bool(degradations),
        degradations=degradations,
        node_path=list(final.get("node_path") or []),
        trace_id=current_trace_id(),
    )


def default_settings() -> Settings:
    """进程级默认配置（避免各调用点重复读 ``.env``）。"""
    return get_settings()
