"""推荐 / 检索的对外请求与响应模型（纯 Pydantic v2，无 IO）。

这里是 **C1 冻结的共享契约**：`api` 层用它收发、`services` 用它编排、`agents` 用它表达
推荐结果、`eval` 用 `RecipeCandidate` / `Recommendation` 做指标计算。改字段 = 改对外契约，
必须同步 `docs/ARCHITECTURE.md`。

分层约束：本模块只依赖 `domain.models.retrieval` 与 `domain.models.recommendation`，
不 import 任何 `infra` / `services` / `agents` / `api`。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from domain.models.recommendation import Recommendation
from domain.models.retrieval import RecipeCandidate


class RecommendRequest(BaseModel):
    """一次推荐请求（用户自然语言 + 可选硬约束）。"""

    query: str = Field(min_length=1, max_length=200, description="用户自然语言需求，如「20 分钟内能做的家常菜」")
    max_time_minutes: int | None = Field(
        default=None, ge=1, le=600, description="可接受的最长烹饪耗时（分钟）；None 表示不限"
    )
    tools_available: list[str] = Field(
        default_factory=list, description="用户拥有的厨具名；菜谱 `tools` 必须是它的子集（下推到检索层）"
    )
    excluded_ingredients: list[str] = Field(
        default_factory=list, description="忌口 / 过敏食材（标准名或别名均可，检索层负责同义展开）"
    )
    top_k: int = Field(default=3, ge=1, le=5, description="最终推荐条数；推荐场景上限 5，避免一次塞太多选择")


class SearchRequest(BaseModel):
    """一次纯检索请求（不生成推荐理由，供前端「先看候选」与评估脚本复用）。"""

    query: str = Field(min_length=1, max_length=200, description="用户自然语言查询，与 `RecommendRequest.query` 同义")
    max_time_minutes: int | None = Field(
        default=None, ge=1, le=600, description="可接受的最长烹饪耗时（分钟）；None 表示不限"
    )
    tools_available: list[str] = Field(
        default_factory=list, description="用户拥有的厨具名；菜谱 `tools` 必须是它的子集"
    )
    excluded_ingredients: list[str] = Field(default_factory=list, description="忌口 / 过敏食材（标准名或别名均可）")
    top_k: int = Field(default=10, ge=1, le=50, description="返回候选条数；检索场景可放宽到 50，便于人工核对召回")


class SearchResponse(BaseModel):
    """检索结果：候选 + 是否降级。"""

    query: str = Field(description="回显请求里的原始查询，便于前端 / trace 对齐")
    candidates: list[RecipeCandidate] = Field(
        default_factory=list, description="按相关度降序的候选，每个都带真实 `recipe_id`（禁止编造）"
    )
    degraded: bool = Field(description="本次检索是否走了降级路径（如重排失败回退 RRF、远程 embedding 切本地）")
    degradations: list[str] = Field(
        default_factory=list, description="降级原因列表（低基数标签，进 trace metadata，不放用户原文）"
    )


class RecommendResponse(BaseModel):
    """推荐结果：最终推荐 + 可解释性信息 + 降级事实。"""

    query: str = Field(description="回显请求里的原始查询")
    recommendations: list[Recommendation] = Field(
        default_factory=list, description="最终可展示的推荐，`recipe_id` 必须来自真实检索候选"
    )
    candidates_considered: int = Field(description="本次实际参与决策的候选数（反思重试时按最后一轮计）")
    no_solution_reason: str | None = Field(
        default=None, description="无解时的用户可读原因；有推荐时为 None（硬约束不可满足时由规则引擎给出）"
    )
    degraded: bool = Field(default=False, description="是否走了降级路径（LLM 不可用、重排失败等）")
    degradations: list[str] = Field(default_factory=list, description="降级原因列表（低基数标签，进 trace metadata）")
    node_path: list[str] = Field(
        default_factory=list, description="Agent 实际走过的节点名，用于可解释性（按执行顺序，不含动态值）"
    )
    trace_id: str | None = Field(
        default=None, description="Langfuse trace id，供前端「查看执行详情」跳转；未启用时 None"
    )
