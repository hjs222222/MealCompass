"""Agent 节点（纯函数式）：parse → search → generate → validate（+ no_solution 出口）。

约定与设计取舍：

1. **节点是纯函数** ``async def node_xxx(state, deps) -> dict``，返回**增量** dict，不做 IO 之外的副作用；
   LangGraph 只按 reducer 拼装 ``degradations`` / ``node_path``，其余键整值替换。
2. **绝不抛异常中断**：LLM 不可用、JSON 脏、引用非法，全部转成「降级 + 标签」，接口层永远拿到结构化结果
   （任何 LLM/网络异常都不能让 /recommend 变 500）。
3. **硬约束由规则决定，LLM 只做抽取**（AGENTS.md §3：不让 LLM 参与硬约束判定）。``node_parse`` 只把
   LLM 抽出的字段映射成 ``HardFilters``，查找/过滤仍由检索层 SQL 下推完成。
4. **引用必须真实**：``node_generate`` 允许 LLM 输出任意 id（含幻觉），``node_validate`` 用
   ``domain.citations.validate_recommendations`` 兜住，幻觉 id 一律进不了最终结果。
5. **可观测**：只取 ``SpanName`` 常量。调用 LLM 的节点把观察类型记为
   ``ObservationType.GENERATION`` 并写 ``model`` + ``usage_details``——CONVENTIONS §4.5 明确要求
   「LLM 调用必须记为 generation 并带 model + usage_details，否则成本 / Token 视图为空」，
   因此 ``node_parse`` 的观察类型优先服从这条硬规则（而不是 §4.5 观察名表里写的 ``span``）。
6. **LangGraph 1.x 不含依赖注入**：``add_node`` 只支持 ``(state)`` 或 ``(state, runtime)`` 两种签名，
   所以 ``graph.py`` 用 ``functools.partial`` 把 ``deps`` 绑上；节点本身仍是可直接调用、可单测的纯函数。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from agents.jsonx import coerce_positive_int, coerce_str_list, extract_json_object, extract_json_payload
from agents.state import (
    DEGRADATION_CITATION_INVALID,
    DEGRADATION_GENERATE_FAILED,
    DEGRADATION_LLM_UNAVAILABLE,
    DEGRADATION_PARSE_FAILED,
    DEGRADATION_RECOMMENDATION_SHORTFALL,
    DEGRADATION_RETRIEVAL_DEGRADED,
    DEGRADATION_RETRIEVAL_FAILED,
    NO_SOLUTION_NO_CANDIDATES,
    NODE_GENERATE,
    NODE_NO_SOLUTION,
    NODE_PARSE,
    NODE_SEARCH,
    NODE_VALIDATE,
    AgentState,
)
from domain.citations import CitationValidationError, validate_recommendations
from domain.models.recommendation import Recommendation
from domain.models.retrieval import HardFilters, RecipeCandidate
from infra.observability import ObservationType, SpanName, traced

if TYPE_CHECKING:  # 只为类型注解；运行时不 import，避免 nodes <-> graph 循环依赖
    from agents.graph import AgentDeps

logger = logging.getLogger(__name__)

MAX_TIME_MINUTES_CEILING = 600
UNKNOWN_RECIPE_NAME = "未知菜谱"

PARSE_SYSTEM_PROMPT = """\
你是菜谱推荐系统的查询解析器。把用户的中文需求抽取成 JSON 对象，只输出 JSON，不要解释。
字段：
- max_time_minutes: 整数或 null。用户明确说出的最长烹饪分钟数（"半小时"=30，"二十分钟"=20）；没提到就 null。
- tools_available: 字符串数组。用户明确说自己**拥有**的厨具（如 ["炒锅","空气炸锅"]）；没提到就 []。
- excluded_ingredients: 字符串数组。用户明确说**不吃 / 过敏 / 忌口**的食材；没提到就 []。
- keywords: 字符串数组。与检索相关的核心食材或菜名。
规则：只抽取用户原文里明确表达的信息，**绝不猜测**；拿不准就留空。"""

GENERATE_SYSTEM_PROMPT = """\
你是菜谱推荐助手。只能从给定的候选菜谱里挑选，禁止虚构候选之外的菜谱。
输出 JSON 对象，格式为：
{"recommendations": [{"recipe_id": "...", "reason": "...",
                      "missing_ingredients": [...], "substitutions": [...]}]}
- recipe_id 必须原样复制候选里的 id，不得改动、不得编造。
- reason 用一句简短的中文（不超过 30 字）说明这道菜的亮点或为什么适合用户；
  不要复述用户的原话（例如不要写"用户想吃X，这道菜以Y为主要食材"），
  不要提"混合检索""第N名""候选"这类系统内部术语。
- missing_ingredients 列出用户还需自备的食材（用户未声明的都算缺料）；无法判断就留空数组。
- substitutions 给出 1-2 条替代建议；没有就留空数组。
- 必须输出 user 消息里指定的条数，一条都不能少；只输出 JSON，不要解释。"""


def _merge_usage(current: dict[str, int] | None, added: dict[str, int] | None) -> dict[str, int]:
    """把本次 LLM usage 累加到状态里已有的 usage 上（``llm_usage`` 是覆盖语义，必须手动合并）。"""
    merged = dict(current or {})
    for key, value in (added or {}).items():
        merged[key] = merged.get(key, 0) + value
    return merged


def _dedupe(labels: list[str]) -> list[str]:
    """降级标签去重且保序（低基数，避免同一原因重复刷屏）。"""
    return list(dict.fromkeys(labels))


async def _complete_json(
    deps: AgentDeps,
    messages: list[dict[str, str]],
    *,
    span: Any,
) -> tuple[str, dict[str, int]]:
    """调一次 LLM（带 usage 记账），把 usage 写进当前 generation 观察。"""
    text, usage = await deps.llm.complete_with_usage(messages, temperature=0.1, response_format="json_object")
    span.update(usage_details=usage)
    return text, usage


# --------------------------------------------------------------------------- parse


def _to_hard_filters(payload: dict[str, Any]) -> HardFilters:
    """把 LLM 抽出的字段映射成 ``HardFilters``；不合法的一律留空，绝不猜数字。"""
    return HardFilters(
        max_time_minutes=coerce_positive_int(
            payload.get("max_time_minutes"), minimum=1, maximum=MAX_TIME_MINUTES_CEILING
        ),
        tools_available=coerce_str_list(payload.get("tools_available")),
        excluded_ingredients=coerce_str_list(payload.get("excluded_ingredients")),
    )


def _merge_filters(explicit: HardFilters | None, parsed: HardFilters) -> HardFilters:
    """请求里显式给的硬约束优先，LLM 只是补空缺；忌口取并集。"""
    base = explicit or HardFilters()
    return HardFilters(
        max_time_minutes=(base.max_time_minutes if base.max_time_minutes is not None else parsed.max_time_minutes),
        tools_available=base.tools_available or parsed.tools_available,
        excluded_ingredients=list(dict.fromkeys([*base.excluded_ingredients, *parsed.excluded_ingredients])),
    )


async def node_parse(state: AgentState, deps: AgentDeps) -> dict:
    """解析自然语言需求 → 硬约束。失败降级为「不加约束」，只留标签，绝不中断。"""
    query = state.get("query", "")
    explicit = state.get("filters")
    degradations: list[str] = []
    usage = _merge_usage(state.get("llm_usage"), None)
    parsed_filters = HardFilters()

    with traced(
        SpanName.PARSE_INTENT,
        as_type=ObservationType.GENERATION,
        model=getattr(deps.llm, "model", None) or "unknown",
        input={"query": query},
    ) as span:
        messages = [
            {"role": "system", "content": PARSE_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]
        for _attempt in range(2):  # 首次 + 重试 1 次（PRD F-C1：解析失败自动重试）
            try:
                text, used = await _complete_json(deps, messages, span=span)
            except Exception as exc:  # noqa: BLE001 - LLM 不可用必须降级，不能 500
                logger.warning("解析意图时 LLM 调用失败，将降级：%s", type(exc).__name__)
                degradations.append(DEGRADATION_LLM_UNAVAILABLE)
                continue
            usage = _merge_usage(usage, used)
            payload = extract_json_object(text)
            if payload is not None:
                parsed_filters = _to_hard_filters(payload)
                span.update(
                    output={
                        "max_time_minutes": parsed_filters.max_time_minutes,
                        "tools_available": parsed_filters.tools_available,
                        "excluded_ingredients": parsed_filters.excluded_ingredients,
                    },
                    metadata={"degraded": False},
                )
                filters = _merge_filters(explicit, parsed_filters)
                return {
                    "filters": filters,
                    "llm_usage": usage,
                    "degradations": _dedupe(degradations),
                    "node_path": [NODE_PARSE],
                }

        degradations.append(DEGRADATION_PARSE_FAILED)
        span.update(output={"degraded": True}, metadata={"degraded": True})

    # 降级：直接用原 query、只保留请求里显式给出的约束
    return {
        "filters": _merge_filters(explicit, HardFilters()),
        "llm_usage": usage,
        "degradations": _dedupe(degradations),
        "node_path": [NODE_PARSE],
    }


# -------------------------------------------------------------------------- search


async def node_search(state: AgentState, deps: AgentDeps) -> dict:
    """混合检索（硬约束已在 ``filters`` 里，由检索层 SQL 下推）。检索异常 → 视为无候选。"""
    query = state.get("query", "")
    filters = state.get("filters")
    top_k = int(state.get("top_k") or 3)
    degradations: list[str] = []

    with traced(
        SpanName.RETRIEVE_RECIPES,
        as_type=ObservationType.SPAN,
        input={"query": query, "has_hard_filters": filters is not None and not filters.is_empty()},
    ) as span:
        try:
            candidates = list(await deps.retriever.search(query, filters, top_k))
        except Exception as exc:  # noqa: BLE001 - 检索挂掉按「无解」处理，不能 500
            logger.warning("检索失败，按无候选降级：%s", type(exc).__name__)
            candidates = []
            degradations.append(DEGRADATION_RETRIEVAL_FAILED)
        else:
            if any(candidate.degraded for candidate in candidates):
                degradations.append(DEGRADATION_RETRIEVAL_DEGRADED)
        span.update(output={"candidate_ids": [candidate.recipe_id for candidate in candidates]})

    return {
        "candidates": candidates,
        "degradations": degradations,
        "node_path": [NODE_SEARCH],
    }


# ------------------------------------------------------------------------ generate


def _candidate_prompt_block(candidates: list[RecipeCandidate]) -> str:
    """候选清单：只放真实字段（id / 菜名 / 命中通道），不含任何编造字段。"""
    lines = []
    for candidate in candidates:
        channels = "/".join(candidate.sources) or "unknown"
        lines.append(f"- id={candidate.recipe_id} 菜名={candidate.name} 召回通道={channels}")
    return "\n".join(lines)


def _constraints_block(filters: HardFilters | None) -> str:
    filters = filters or HardFilters()
    parts = []
    if filters.max_time_minutes is not None:
        parts.append(f"最长 {filters.max_time_minutes} 分钟")
    if filters.tools_available:
        parts.append(f"可用厨具：{'、'.join(filters.tools_available)}")
    if filters.excluded_ingredients:
        parts.append(f"忌口：{'、'.join(filters.excluded_ingredients)}")
    return "；".join(parts) if parts else "无显式硬约束"


def _rule_recommendation(candidate: RecipeCandidate, query: str) -> Recommendation:
    """规则兜底：只用候选自身的真实数据拼一条可展示推荐（不编造 id、不编造耗时）。

    reason 不暴露"混合检索第 N 名"这类系统内部术语，也不复述用户原 query；
    LLM 不可用或输出不足时，这是用户直接看到的文案，必须像人话。
    """
    del query  # 不再把用户原话塞进 reason，避免"命中你的需求「xxx」的第 N 名"这种机械感
    return Recommendation(
        recipe_id=candidate.recipe_id,
        name=candidate.name,
        reason="根据你的需求检索到这道菜",
        time_minutes=None,
    )


def _rule_recommendations(candidates: list[RecipeCandidate], count: int, query: str) -> list[Recommendation]:
    return [_rule_recommendation(candidate, query) for candidate in candidates[:count]]


def _parse_generated_items(text: str) -> list[dict[str, Any]] | None:
    """解析生成结果：既接受 ``{"recommendations": [...]}``，也接受裸数组。"""
    payload = extract_json_payload(text)
    if isinstance(payload, dict):
        for key in ("recommendations", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return None
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return None


def _to_recommendation(item: dict[str, Any], by_id: dict[str, RecipeCandidate]) -> Recommendation | None:
    """把 LLM 的一条输出映射成 ``Recommendation``；菜名以候选为准（引用安全）。"""
    raw_id = item.get("recipe_id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        return None
    recipe_id = raw_id.strip()
    candidate = by_id.get(recipe_id)
    name = candidate.name if candidate is not None else str(item.get("name") or UNKNOWN_RECIPE_NAME).strip()
    reason = item.get("reason")
    reason = reason.strip() if isinstance(reason, str) and reason.strip() else f"匹配需求：{name}"
    return Recommendation(
        recipe_id=recipe_id,
        name=name or UNKNOWN_RECIPE_NAME,
        reason=reason,
        missing_ingredients=coerce_str_list(item.get("missing_ingredients")),
        substitutions=coerce_str_list(item.get("substitutions")),
        time_minutes=None,  # 当前候选不携带可靠的结构化总时长
    )


async def node_generate(state: AgentState, deps: AgentDeps) -> dict:
    """候选 → 推荐（理由 / 缺料 / 替代）。LLM 失败或 JSON 脏 → 规则生成兜底。"""
    query = state.get("query", "")
    candidates = list(state.get("candidates") or [])
    top_k = int(state.get("top_k") or 3)
    expected = min(top_k, len(candidates))
    degradations: list[str] = []
    usage = _merge_usage(state.get("llm_usage"), None)
    recommendations: list[Recommendation] = []

    with traced(
        SpanName.GENERATE_RECOMMENDATIONS,
        as_type=ObservationType.GENERATION,
        model=getattr(deps.llm, "model", None) or "unknown",
        input={"query": query, "candidate_count": len(candidates), "expected_count": expected},
    ) as span:
        messages = [
            {"role": "system", "content": GENERATE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"用户需求：{query}\n"
                    f"硬约束：{_constraints_block(state.get('filters'))}\n"
                    f"候选菜谱（只能从中挑选）：\n{_candidate_prompt_block(candidates)}\n"
                    f"必须输出恰好 {expected} 条推荐，按推荐优先级排序，一条都不能少。"
                ),
            },
        ]
        try:
            text, used = await _complete_json(deps, messages, span=span)
        except Exception as exc:  # noqa: BLE001 - 生成失败必须降级
            logger.warning("生成推荐时 LLM 调用失败，走规则兜底：%s", type(exc).__name__)
            degradations.extend([DEGRADATION_LLM_UNAVAILABLE, DEGRADATION_GENERATE_FAILED])
        else:
            usage = _merge_usage(usage, used)
            items = _parse_generated_items(text)
            if items is None:
                degradations.append(DEGRADATION_GENERATE_FAILED)
            else:
                by_id = {candidate.recipe_id: candidate for candidate in candidates}
                for item in items[:expected]:
                    recommendation = _to_recommendation(item, by_id)
                    if recommendation is not None:
                        recommendations.append(recommendation)
                if not recommendations:
                    degradations.append(DEGRADATION_GENERATE_FAILED)

        if not recommendations:
            # 兜底只借候选的真实数据；理由模板明确说明「未经过 LLM 润色」
            recommendations = [
                recommendation.model_copy(
                    update={"reason": f"{recommendation.reason}（未启用 LLM 润色，由规则兜底生成）"}
                )
                for recommendation in _rule_recommendations(candidates, expected, query)
            ]

        span.update(output={"recommendation_ids": [item.recipe_id for item in recommendations]})

    return {
        "recommendations": recommendations,
        "llm_usage": usage,
        "degradations": _dedupe(degradations),
        "node_path": [NODE_GENERATE],
    }


# ------------------------------------------------------------------------ validate


def _sanitize(
    recommendations: list[Recommendation],
    by_id: dict[str, RecipeCandidate],
    target: int,
) -> tuple[list[Recommendation], bool]:
    """丢弃幻觉 / 重复 / 空 id，并把菜名与耗时校正为候选的权威值。

    Returns:
        ``(保留的推荐, 是否发生过「引用不可信」的丢弃)``。**只**在真的丢东西时才置 True：
        数量不足导致的补齐走 ``recommendation_shortfall``，不能混进 ``citation_invalid``，
        否则「LLM 只给了 2 条」会被误报成「引用了不存在的菜谱」。
    """
    kept: list[Recommendation] = []
    seen: set[str] = set()
    invalid_dropped = False
    for recommendation in recommendations:
        recipe_id = recommendation.recipe_id.strip()
        candidate = by_id.get(recipe_id)
        if candidate is None or recipe_id in seen:
            invalid_dropped = True
            continue
        seen.add(recipe_id)
        if recommendation.name != candidate.name or recommendation.time_minutes is not None:
            # 菜名以候选为准（引用安全）；耗时库内全 NULL，不编造。
            # 模型给的名字对不上知识库 = 引用不可信，同样记 citation_invalid。
            recommendation = recommendation.model_copy(update={"name": candidate.name, "time_minutes": None})
            invalid_dropped = True
        kept.append(recommendation)
        if len(kept) >= target:
            break
    return kept, invalid_dropped


async def node_validate(state: AgentState, deps: AgentDeps) -> dict:
    """引用校验：只留能对上候选的推荐，绝不返回不存在的 recipe_id（PRD F-C4）。"""
    query = state.get("query", "")
    candidates = list(state.get("candidates") or [])
    top_k = int(state.get("top_k") or 3)
    target = min(top_k, len(candidates))
    raw = list(state.get("recommendations") or [])
    degradations: list[str] = []

    with traced(
        SpanName.REFLECT_VALIDATE,
        as_type=ObservationType.SPAN,
        input={"recommendation_count": len(raw), "candidate_count": len(candidates), "expected_count": target},
    ) as span:
        by_id: dict[str, RecipeCandidate] = {}
        for candidate in candidates:
            by_id.setdefault(candidate.recipe_id, candidate)

        sanitized, invalid_dropped = _sanitize(raw, by_id, target)
        if len(sanitized) < target:
            # 数量不够：用剩余候选按检索顺序补齐（规则生成，数据全部来自候选）
            filled_ids = {item.recipe_id for item in sanitized}
            for candidate in candidates:
                if len(sanitized) >= target:
                    break
                if candidate.recipe_id in filled_ids:
                    continue
                sanitized.append(_rule_recommendation(candidate, query))
                filled_ids.add(candidate.recipe_id)
            degradations.append(DEGRADATION_RECOMMENDATION_SHORTFALL)

        if invalid_dropped:
            degradations.append(DEGRADATION_CITATION_INVALID)

        validated: list[Recommendation] = []
        try:
            validated = validate_recommendations(sanitized, candidates, expected_count=target)
        except CitationValidationError as exc:
            logger.warning("引用校验失败，回退到纯规则候选：%s", exc)
            degradations.append(DEGRADATION_CITATION_INVALID)
            validated = _rule_recommendations(candidates, target, query)
            validated = validate_recommendations(validated, candidates, expected_count=target)

        span.update(
            output={
                "validated_ids": [item.recipe_id for item in validated],
                "invalid_dropped": invalid_dropped,
                "shortfall_filled": DEGRADATION_RECOMMENDATION_SHORTFALL in degradations,
                "valid_count": len(validated),
            },
            metadata={"degradation_tags": _dedupe(degradations)},
        )

    return {
        "recommendations": validated,
        "degradations": _dedupe(degradations),
        "node_path": [NODE_VALIDATE],
    }


# --------------------------------------------------------------------- no_solution


async def node_no_solution(state: AgentState, deps: AgentDeps) -> dict:
    """硬约束下候选为空：显式给出无解原因，绝不编造菜谱（PRD F-C5 语义）。"""
    del deps  # 无解路径不需要任何依赖
    with traced(
        SpanName.FILTER_HARD_CONSTRAINTS,
        as_type=ObservationType.SPAN,
        input={"reason": NO_SOLUTION_NO_CANDIDATES, "candidate_count": 0},
    ) as span:
        span.update(output={"no_solution_reason": NO_SOLUTION_NO_CANDIDATES})
    return {
        "recommendations": [],
        "no_solution_reason": NO_SOLUTION_NO_CANDIDATES,
        "node_path": [NODE_NO_SOLUTION],
    }
