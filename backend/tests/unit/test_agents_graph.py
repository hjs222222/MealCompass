"""C3 Agent 闭环单元测试（假 retriever + 假 LLM，不连网络、不连库）。

覆盖 PRD 模块 C 的关键语义：
- 正常路径 3 条推荐 + ``node_path`` 可解释；
- LLM 脏输出（````` ```json ```` 围栏 + 前后说明文字）依然能解析——这是 SiliconFlow 的真实返回形态；
- LLM 完全不可用 / 非法 JSON → 降级但仍有输出；
- 检索为空 → 显式无解，绝不编造菜谱；
- LLM 编造不存在的 ``recipe_id`` → 被引用校验拦掉。
"""

from __future__ import annotations

import operator
from typing import get_type_hints

import pytest
from langgraph.graph import END, START, StateGraph

from agents.graph import AgentDeps, build_graph, run_agent
from agents.jsonx import extract_json_array, extract_json_object, extract_json_payload
from agents.nodes import node_generate, node_no_solution, node_parse, node_search, node_validate
from agents.state import (
    DEGRADATION_CITATION_INVALID,
    DEGRADATION_GENERATE_FAILED,
    DEGRADATION_LLM_UNAVAILABLE,
    DEGRADATION_PARSE_FAILED,
    DEGRADATION_RECOMMENDATION_SHORTFALL,
    NO_SOLUTION_NO_CANDIDATES,
    NODE_GENERATE,
    NODE_NO_SOLUTION,
    NODE_PARSE,
    NODE_SEARCH,
    NODE_VALIDATE,
    AgentState,
)
from core.config import Settings
from domain.models.retrieval import HardFilters, RecipeCandidate

SETTINGS = Settings(_env_file=None, llm_model="fake-model")


class FakeRetriever:
    """假检索器：记录调用参数，返回可控候选。"""

    def __init__(self, candidates: list[RecipeCandidate] | None = None, *, boom: bool = False) -> None:
        self._candidates = candidates if candidates is not None else []
        self._boom = boom
        self.calls: list[tuple[str, HardFilters | None, int]] = []

    async def search(self, query: str, filters: HardFilters | None = None, top_k: int = 10) -> list[RecipeCandidate]:
        self.calls.append((query, filters, top_k))
        if self._boom:
            raise RuntimeError("retriever down")
        return list(self._candidates[:top_k])


class FakeLLM:
    """假 LLM：按顺序吐出预设文本；``boom`` 时模拟网络异常。"""

    model = "fake-model"

    def __init__(self, replies: list[str] | None = None, *, boom: bool = False) -> None:
        self._replies = list(replies or [])
        self._boom = boom
        self.calls: list[list[dict[str, str]]] = []

    async def complete(self, messages, *, temperature: float = 0.1, response_format: str | None = None) -> str:
        text, _ = await self.complete_with_usage(messages, temperature=temperature, response_format=response_format)
        return text

    async def complete_with_usage(self, messages, *, temperature: float = 0.1, response_format: str | None = None):
        self.calls.append(list(messages))
        if self._boom:
            raise RuntimeError("llm down")
        if not self._replies:
            raise AssertionError("FakeLLM 没有更多预设回复")
        return self._replies.pop(0), {"input_tokens": 10, "output_tokens": 5}


def candidate(recipe_id: str, name: str, rank: int = 1) -> RecipeCandidate:
    return RecipeCandidate(recipe_id=recipe_id, name=name, score=1.0 - rank / 100, rank=rank, sources=["vector"])


CANDIDATES = [
    candidate("r1", "西红柿炒鸡蛋", 1),
    candidate("r2", "番茄牛腩", 2),
    candidate("r3", "凉拌黄瓜", 3),
]

PARSE_JSON = '{"max_time_minutes": 20, "tools_available": ["炒锅"], "excluded_ingredients": []}'

GENERATE_JSON = """```json
{
  "recommendations": [
    {"recipe_id": "r1", "reason": "20 分钟能做好，用炒锅即可",
     "missing_ingredients": ["鸡蛋"], "substitutions": ["鸭蛋"]},
    {"recipe_id": "r2", "reason": "番茄口味接近你的需求", "missing_ingredients": [], "substitutions": []},
    {"recipe_id": "r3", "reason": "清爽配菜，补足蔬菜", "missing_ingredients": [], "substitutions": []}
  ]
}
```"""


def deps(retriever: FakeRetriever, llm: FakeLLM) -> AgentDeps:
    return AgentDeps(retriever=retriever, llm=llm, settings=SETTINGS)


# ------------------------------------------------------------------ json 提取（围栏容错）


@pytest.mark.parametrize(
    "text",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        '```\n{"a": 1}\n```',
        '好的，解析结果如下：\n```json\n{"a": 1}\n```\n希望有帮助。',
        '前面说明 {"a": 1} 后面说明',
        '  \n```JSON\n{"a": 1}\n```  \n',
    ],
)
def test_extract_json_object_tolerates_fences_and_prose(text: str) -> None:
    assert extract_json_object(text) == {"a": 1}


@pytest.mark.parametrize(
    "text",
    [
        '[{"a": 1}]',
        '```json\n[{"a": 1}]\n```',
        '结果如下：\n```json\n[{"a": 1}]\n``` 完毕',
    ],
)
def test_extract_json_array_tolerates_fences_and_prose(text: str) -> None:
    assert extract_json_array(text) == [{"a": 1}]


@pytest.mark.parametrize("text", ["", "   ", "完全不是 JSON", "```json\n{不是 json}\n```", None, 123])
def test_extract_json_payload_returns_none_for_garbage(text: object) -> None:
    assert extract_json_payload(text) is None  # type: ignore[arg-type]


def test_extract_json_object_prefers_object_over_array_noise() -> None:
    text = '说明 [1, 2] 然后是真正的对象 {"recipes": [{"name": "x"}]} 结束'
    assert extract_json_object(text) == {"recipes": [{"name": "x"}]}


def test_extract_json_handles_nested_braces() -> None:
    text = '```json\n{"text": "带 } 的字符串", "nested": {"b": [1, {"c": 2}]}}\n```'
    assert extract_json_object(text) == {"text": "带 } 的字符串", "nested": {"b": [1, {"c": 2}]}}


# ---------------------------------------------------------------------------- node_parse


async def test_node_parse_maps_llm_json_to_hard_filters() -> None:
    llm = FakeLLM([PARSE_JSON])
    state: AgentState = {"query": "20 分钟用炒锅做个菜", "filters": HardFilters()}

    delta = await node_parse(state, deps(FakeRetriever(), llm))

    assert delta["filters"] == HardFilters(max_time_minutes=20, tools_available=["炒锅"])
    assert delta["node_path"] == [NODE_PARSE]
    assert delta["degradations"] == []
    assert delta["llm_usage"] == {"input_tokens": 10, "output_tokens": 5}


async def test_node_parse_explicit_filters_win_over_llm() -> None:
    llm = FakeLLM([PARSE_JSON])
    explicit = HardFilters(max_time_minutes=45, excluded_ingredients=["花生"])
    delta = await node_parse({"query": "随便", "filters": explicit}, deps(FakeRetriever(), llm))

    assert delta["filters"].max_time_minutes == 45
    assert delta["filters"].tools_available == ["炒锅"]  # 显式没给，用 LLM 补
    assert delta["filters"].excluded_ingredients == ["花生"]


async def test_node_parse_retries_then_degrades_on_garbage() -> None:
    llm = FakeLLM(["不是 JSON", "仍然不是 JSON"])
    delta = await node_parse({"query": "想吃的清淡点", "filters": HardFilters()}, deps(FakeRetriever(), llm))

    assert len(llm.calls) == 2  # 首次 + 重试 1 次
    assert delta["degradations"] == [DEGRADATION_PARSE_FAILED]
    assert delta["filters"] == HardFilters()
    assert delta["node_path"] == [NODE_PARSE]


async def test_node_parse_degrades_when_llm_unavailable() -> None:
    delta = await node_parse({"query": "随便", "filters": HardFilters()}, deps(FakeRetriever(), FakeLLM(boom=True)))

    assert DEGRADATION_LLM_UNAVAILABLE in delta["degradations"]
    assert delta["filters"] == HardFilters()


async def test_node_parse_rejects_out_of_range_time_from_llm() -> None:
    llm = FakeLLM(['{"max_time_minutes": 99999, "tools_available": [], "excluded_ingredients": []}'])
    delta = await node_parse({"query": "很快", "filters": HardFilters()}, deps(FakeRetriever(), llm))

    assert delta["filters"].max_time_minutes is None  # 宁可留空也不猜数字


# --------------------------------------------------------------------------- node_search


async def test_node_search_passes_filters_and_top_k_through() -> None:
    retriever = FakeRetriever(CANDIDATES)
    filters = HardFilters(tools_available=["炒锅"])

    delta = await node_search({"query": "q", "filters": filters, "top_k": 2}, deps(retriever, FakeLLM()))

    assert retriever.calls == [("q", filters, 2)]
    assert [item.recipe_id for item in delta["candidates"]] == ["r1", "r2"]
    assert delta["node_path"] == [NODE_SEARCH]


async def test_node_search_exception_becomes_empty_candidates() -> None:
    delta = await node_search({"query": "q", "top_k": 3}, deps(FakeRetriever(boom=True), FakeLLM()))

    assert delta["candidates"] == []
    assert delta["degradations"] == ["retrieval_failed"]


async def test_node_search_marks_degraded_candidates() -> None:
    degraded = [candidate("r1", "菜一").model_copy(update={"degraded": True})]
    delta = await node_search({"query": "q", "top_k": 3}, deps(FakeRetriever(degraded), FakeLLM()))

    assert "retrieval_degraded" in delta["degradations"]


# ------------------------------------------------------------------------- node_generate


async def test_node_generate_parses_fenced_json_with_prose() -> None:
    llm = FakeLLM([f"这是结果：\n{GENERATE_JSON}\n请查收。"])
    delta = await node_generate(
        {"query": "西红柿炒鸡蛋", "candidates": CANDIDATES, "top_k": 3, "filters": HardFilters()},
        deps(FakeRetriever(), llm),
    )

    assert [item.recipe_id for item in delta["recommendations"]] == ["r1", "r2", "r3"]
    assert delta["recommendations"][0].name == "西红柿炒鸡蛋"  # 菜名以候选为准
    assert delta["recommendations"][0].missing_ingredients == ["鸡蛋"]
    assert delta["recommendations"][0].time_minutes is None  # 库内耗时全 NULL：不编造
    assert delta["degradations"] == []
    assert delta["llm_usage"] == {"input_tokens": 10, "output_tokens": 5}


async def test_node_generate_falls_back_to_rules_on_invalid_json() -> None:
    llm = FakeLLM(["对不起我做不到"])
    delta = await node_generate(
        {"query": "随便来点", "candidates": CANDIDATES, "top_k": 3, "filters": HardFilters()},
        deps(FakeRetriever(), llm),
    )

    assert DEGRADATION_GENERATE_FAILED in delta["degradations"]
    assert [item.recipe_id for item in delta["recommendations"]] == ["r1", "r2", "r3"]
    assert all(item.reason for item in delta["recommendations"])


async def test_node_generate_falls_back_when_llm_unavailable() -> None:
    delta = await node_generate(
        {"query": "随便", "candidates": CANDIDATES, "top_k": 2, "filters": HardFilters()},
        deps(FakeRetriever(), FakeLLM(boom=True)),
    )

    assert set(delta["degradations"]) == {DEGRADATION_LLM_UNAVAILABLE, DEGRADATION_GENERATE_FAILED}
    assert len(delta["recommendations"]) == 2


async def test_node_generate_accepts_bare_array_payload() -> None:
    llm = FakeLLM(['[{"recipe_id": "r2", "reason": "就它", "missing_ingredients": [], "substitutions": []}]'])
    delta = await node_generate(
        {"query": "q", "candidates": CANDIDATES, "top_k": 3, "filters": HardFilters()},
        deps(FakeRetriever(), llm),
    )

    assert [item.recipe_id for item in delta["recommendations"]] == ["r2"]


async def test_node_generate_ignores_surplus_items_beyond_expected() -> None:
    payload = (
        "{"
        + '"recommendations": ['
        + ",".join(
            f'{{"recipe_id": "r{index}", "reason": "r", "missing_ingredients": [], "substitutions": []}}'
            for index in (1, 2, 3)
        )
        + "]}"
    )
    llm = FakeLLM([payload])
    delta = await node_generate(
        {"query": "q", "candidates": CANDIDATES, "top_k": 2, "filters": HardFilters()},
        deps(FakeRetriever(), llm),
    )

    assert len(delta["recommendations"]) == 2


# ------------------------------------------------------------------------- node_validate


async def test_node_validate_drops_hallucinated_recipe_id() -> None:
    from domain.models.recommendation import Recommendation

    hallucinated = [
        Recommendation(recipe_id="r1", name="西红柿炒鸡蛋", reason="ok"),
        Recommendation(recipe_id="不存在", name="幽灵菜", reason="ok"),
        Recommendation(recipe_id="r2", name="番茄牛腩", reason="ok"),
    ]
    delta = await node_validate(
        {"query": "q", "candidates": CANDIDATES, "top_k": 3, "recommendations": hallucinated},
        deps(FakeRetriever(), FakeLLM()),
    )

    ids = [item.recipe_id for item in delta["recommendations"]]
    assert "不存在" not in ids
    assert DEGRADATION_CITATION_INVALID in delta["degradations"]
    assert len(delta["recommendations"]) == 3  # 第三条由候选按检索顺序补齐


async def test_node_validate_shortfall_is_not_reported_as_citation_invalid() -> None:
    """LLM 只给了 2 条（没有幻觉）时只能标 shortfall：不能误报成引用违规。"""
    from domain.models.recommendation import Recommendation

    delta = await node_validate(
        {
            "query": "q",
            "candidates": CANDIDATES,
            "top_k": 3,
            "recommendations": [
                Recommendation(recipe_id="r1", name="西红柿炒鸡蛋", reason="ok"),
                Recommendation(recipe_id="r2", name="番茄牛腩", reason="ok"),
            ],
        },
        deps(FakeRetriever(), FakeLLM()),
    )

    assert delta["degradations"] == [DEGRADATION_RECOMMENDATION_SHORTFALL]
    assert len(delta["recommendations"]) == 3


async def test_run_agent_records_shortfall_for_two_item_generation() -> None:
    """真机常见形态：LLM 只返回前 2 条 → shortfall（而非 citation_invalid）。"""
    two_item_generate = (
        '{"recommendations": ['
        '{"recipe_id": "r1", "reason": "匹配", "missing_ingredients": [], "substitutions": []},'
        '{"recipe_id": "r2", "reason": "接近", "missing_ingredients": [], "substitutions": []}]}'
    )
    llm = FakeLLM([PARSE_JSON, two_item_generate])
    response = await run_agent("西红柿炒鸡蛋", HardFilters(), deps=deps(FakeRetriever(CANDIDATES), llm))

    assert len(response.recommendations) == 3
    assert response.degradations == [DEGRADATION_RECOMMENDATION_SHORTFALL]
    assert response.degraded is True


async def test_node_validate_corrects_name_mismatch_from_llm() -> None:
    from domain.models.recommendation import Recommendation

    delta = await node_validate(
        {
            "query": "q",
            "candidates": [CANDIDATES[0]],
            "top_k": 1,
            "recommendations": [Recommendation(recipe_id="r1", name="瞎写的名字", reason="ok")],
        },
        deps(FakeRetriever(), FakeLLM()),
    )

    assert delta["recommendations"][0].name == "西红柿炒鸡蛋"
    assert DEGRADATION_CITATION_INVALID in delta["degradations"]


async def test_node_validate_drops_duplicates() -> None:
    from domain.models.recommendation import Recommendation

    delta = await node_validate(
        {
            "query": "q",
            "candidates": [CANDIDATES[0]],
            "top_k": 1,
            "recommendations": [
                Recommendation(recipe_id="r1", name="西红柿炒鸡蛋", reason="a"),
                Recommendation(recipe_id="r1", name="西红柿炒鸡蛋", reason="b"),
            ],
        },
        deps(FakeRetriever(), FakeLLM()),
    )

    assert [item.recipe_id for item in delta["recommendations"]] == ["r1"]


async def test_node_validate_falls_back_to_rules_when_all_invalid() -> None:
    from domain.models.recommendation import Recommendation

    delta = await node_validate(
        {
            "query": "q",
            "candidates": CANDIDATES,
            "top_k": 3,
            "recommendations": [Recommendation(recipe_id="nope", name="幽灵菜", reason="ok")],
        },
        deps(FakeRetriever(), FakeLLM()),
    )

    assert [item.recipe_id for item in delta["recommendations"]] == ["r1", "r2", "r3"]
    assert DEGRADATION_CITATION_INVALID in delta["degradations"]


async def test_node_validate_always_produces_valid_ids() -> None:
    delta = await node_validate(
        {"query": "q", "candidates": CANDIDATES, "top_k": 3, "recommendations": []},
        deps(FakeRetriever(), FakeLLM()),
    )

    known = {item.recipe_id for item in CANDIDATES}
    assert {item.recipe_id for item in delta["recommendations"]} <= known
    assert len(delta["recommendations"]) == 3


# ----------------------------------------------------------------- no_solution / graph


async def test_node_no_solution_is_explicit() -> None:
    delta = await node_no_solution({"query": "q"}, deps(FakeRetriever(), FakeLLM()))

    assert delta["no_solution_reason"] == NO_SOLUTION_NO_CANDIDATES
    assert delta["recommendations"] == []
    assert delta["node_path"] == [NODE_NO_SOLUTION]


async def test_run_agent_happy_path() -> None:
    llm = FakeLLM([PARSE_JSON, GENERATE_JSON])
    response = await run_agent(
        "20 分钟做个西红柿炒鸡蛋",
        HardFilters(),
        deps=deps(FakeRetriever(CANDIDATES), llm),
        top_k=3,
    )

    assert len(response.recommendations) == 3
    assert response.node_path == [NODE_PARSE, NODE_SEARCH, NODE_GENERATE, NODE_VALIDATE]
    assert response.candidates_considered == 3
    assert response.no_solution_reason is None
    assert response.degraded is False
    assert response.degradations == []
    assert response.query == "20 分钟做个西红柿炒鸡蛋"


async def test_run_agent_no_solution_never_invents_recipes() -> None:
    llm = FakeLLM([PARSE_JSON])
    retriever = FakeRetriever([])

    response = await run_agent("空气炸锅能做啥", HardFilters(), deps=deps(retriever, llm), top_k=3)

    assert response.recommendations == []
    assert response.no_solution_reason == NO_SOLUTION_NO_CANDIDATES
    assert response.candidates_considered == 0
    assert response.node_path == [NODE_PARSE, NODE_SEARCH, NODE_NO_SOLUTION]
    assert len(llm.calls) == 1  # 无解时不再调用生成


async def test_run_agent_degrades_but_still_answers_when_llm_is_down() -> None:
    response = await run_agent("随便来点", HardFilters(), deps=deps(FakeRetriever(CANDIDATES), FakeLLM(boom=True)))

    assert len(response.recommendations) == 3
    assert response.degraded is True
    assert DEGRADATION_LLM_UNAVAILABLE in response.degradations
    assert response.node_path == [NODE_PARSE, NODE_SEARCH, NODE_GENERATE, NODE_VALIDATE]


async def test_run_agent_hallucinated_id_never_reaches_response() -> None:
    bad_generate = (
        '{"recommendations": [{"recipe_id": "ghost-1", "reason": "编的",'
        ' "missing_ingredients": [], "substitutions": []}]}'
    )
    llm = FakeLLM([PARSE_JSON, bad_generate])
    response = await run_agent("西红柿炒鸡蛋", HardFilters(), deps=deps(FakeRetriever(CANDIDATES), llm))

    ids = {item.recipe_id for item in response.recommendations}
    assert "ghost-1" not in ids
    assert ids <= {item.recipe_id for item in CANDIDATES}
    assert DEGRADATION_CITATION_INVALID in response.degradations
    assert response.degraded is True


async def test_run_agent_retrieval_failure_is_not_a_crash() -> None:
    response = await run_agent("q", HardFilters(), deps=deps(FakeRetriever(boom=True), FakeLLM(boom=True)))

    assert response.recommendations == []
    assert response.no_solution_reason == NO_SOLUTION_NO_CANDIDATES


async def test_run_agent_with_checkpointer_and_thread_id() -> None:
    from langgraph.checkpoint.memory import InMemorySaver

    llm = FakeLLM([PARSE_JSON, GENERATE_JSON])
    checkpointer = InMemorySaver()
    graph = build_graph(deps(FakeRetriever(CANDIDATES), llm), checkpointer=checkpointer)
    final = await graph.ainvoke(
        {"query": "西红柿炒鸡蛋", "filters": HardFilters(), "top_k": 3},
        {"configurable": {"thread_id": "thread-1"}},
    )

    assert len(final["recommendations"]) == 3
    assert checkpointer.get({"configurable": {"thread_id": "thread-1"}}) is not None


def test_build_graph_without_checkpointer_compiles() -> None:
    graph = build_graph(deps(FakeRetriever(CANDIDATES), FakeLLM()))

    assert graph is not None


async def test_degradations_accumulate_through_reducer() -> None:
    """``degradations`` 用 operator.add：LLM 全挂时 parse + generate 的标签都要留住。"""
    llm = FakeLLM(boom=True)
    response = await run_agent("随便", HardFilters(), deps=deps(FakeRetriever(CANDIDATES), llm))

    assert set(response.degradations) >= {DEGRADATION_LLM_UNAVAILABLE, DEGRADATION_GENERATE_FAILED}


def test_state_reducer_declarations() -> None:
    """状态里只有累积字段带 reducer，且必须是 operator.add。"""
    hints = get_type_hints(AgentState, include_extras=True)

    for field in ("degradations", "node_path"):
        metadata = getattr(hints[field], "__metadata__", ())
        assert operator.add in metadata

    assert not getattr(hints["candidates"], "__metadata__", ())
    assert "llm_usage" in hints and "top_k" in hints


def test_graph_topology_declares_conditional_branch() -> None:
    """条件边存在且映射到 generate / no_solution 两个出口。"""
    builder = StateGraph(AgentState)
    for name in (NODE_PARSE, NODE_SEARCH, NODE_GENERATE, NODE_VALIDATE, NODE_NO_SOLUTION):
        builder.add_node(name, _noop)
    builder.add_edge(START, NODE_PARSE)
    builder.add_edge(NODE_PARSE, NODE_SEARCH)
    builder.add_conditional_edges(
        NODE_SEARCH,
        lambda state: NODE_GENERATE if state.get("candidates") else NODE_NO_SOLUTION,
        {NODE_GENERATE: NODE_GENERATE, NODE_NO_SOLUTION: NODE_NO_SOLUTION},
    )
    builder.add_edge(NODE_GENERATE, NODE_VALIDATE)
    builder.add_edge(NODE_VALIDATE, END)
    builder.add_edge(NODE_NO_SOLUTION, END)

    assert builder.compile() is not None


async def _noop(state: AgentState) -> dict:  # pragma: no cover - 仅用于拓扑断言
    del state
    return {}
