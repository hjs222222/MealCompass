"""Agent 状态（LangGraph）与跨节点常量。

**为什么扁平**：CONVENTIONS §4.1 要求状态保持扁平、轻量。本闭环只有「输入约束 → 候选 →
推荐 → 结果」一条链，没有分支并行写同一字段的场景，扁平 TypedDict 让每个节点只需读自己关心的键，
也让 `node_path` 能精确复原 Agent 实际走过的路径（可解释性）。

**为什么只有累积字段需要 reducer**：字段分两类——
- *覆盖型*：``query`` / ``filters`` / ``candidates`` / ``recommendations`` 等，每个节点返回新值时
  都是「完整替换上一版」，谁后写谁生效，不需要 reducer；
- *累积型*：``degradations`` / ``node_path`` 是**只增不减的审计日志**，多个节点各写各的一条，
  必须 ``Annotated[list[str], operator.add]`` 让 LangGraph 把增量拼到已有列表上，否则后一个节点会
  把前一个节点的降级事实覆盖掉（审计丢失）。

注意：返回的 dict 是**增量**，reducer 只作用在标记过的键上；未标记的键按替换语义处理。
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from domain.models.recommendation import Recommendation
from domain.models.retrieval import HardFilters, RecipeCandidate

# 节点名（低基数、不含动态值；同时作为 `node_path` 的可解释性标签）
NODE_PARSE = "parse"
NODE_SEARCH = "search"
NODE_GENERATE = "generate"
NODE_VALIDATE = "validate"
NODE_NO_SOLUTION = "no_solution"

# 无解原因（PRD F-C5：硬约束不可满足时显式说「没有」，绝不编造菜谱）
NO_SOLUTION_NO_CANDIDATES = "no_candidates_under_constraints"

# 降级标签（低基数，进 trace metadata）
DEGRADATION_PARSE_FAILED = "parse_intent_failed"
DEGRADATION_GENERATE_FAILED = "generate_fallback"
DEGRADATION_CITATION_INVALID = "citation_invalid"
# LLM 输出条数不足、由候选按检索顺序补齐（**不是**引用违规，必须与 citation_invalid 区分开）
DEGRADATION_RECOMMENDATION_SHORTFALL = "recommendation_shortfall"

# LLM 调用失败时的兜底标签
DEGRADATION_LLM_UNAVAILABLE = "llm_unavailable"

# 检索层异常 / 检索结果自身带降级标记
DEGRADATION_RETRIEVAL_FAILED = "retrieval_failed"
DEGRADATION_RETRIEVAL_DEGRADED = "retrieval_degraded"


class AgentState(TypedDict, total=False):
    """Agent 闭环的扁平状态。所有键可选（``total=False``），节点只返回自己改动的增量。"""

    query: str
    filters: HardFilters
    top_k: int
    candidates: list[RecipeCandidate]
    recommendations: list[Recommendation]
    no_solution_reason: str | None
    degradations: Annotated[list[str], operator.add]
    node_path: Annotated[list[str], operator.add]
    llm_usage: dict[str, int]
