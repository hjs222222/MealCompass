"""检索相关的领域模型（纯数据，无 IO）。

被 `domain.ports.Retriever` 与 `rag/` 层共同引用；只放标准库与 domain 自身类型。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HardFilters(BaseModel):
    """硬约束（T1.10）：**下推到检索层**，不允许检索后再过滤。

    - ``max_time_minutes``：可接受的最长烹饪耗时（分钟）。上游 ``time_minutes``
      目前恒为 NULL，该条件以「未知不拦截」为原则（见 `rag.retriever` 的 SQL）。
    - ``tools_available``：用户**拥有**的厨具；菜谱 ``tools`` 必须是它的子集。
    - ``excluded_ingredients``：忌口/过敏食材（标准名或别名都行，检索层负责同义展开）。
    """

    max_time_minutes: int | None = Field(default=None, ge=0)
    tools_available: list[str] = Field(default_factory=list)
    excluded_ingredients: list[str] = Field(default_factory=list)

    def is_empty(self) -> bool:
        return self.max_time_minutes is None and not self.tools_available and not self.excluded_ingredients


class RecipeCandidate(BaseModel):
    """一路检索/融合后产出的菜谱候选。所有候选**必须**携带真实 ``recipe_id``（T1.11）。"""

    recipe_id: str
    name: str
    score: float = Field(description="当前阶段的排序分（RRF 分或重排分）")
    rank: int | None = Field(default=None, description="最终返回给上层的 1 基名次")
    sources: list[str] = Field(default_factory=list, description="命中过哪些召回通道：vector/bm25")
    matched_step_no: int | None = Field(default=None, description="步骤级精取命中的步骤号（仅步骤检索时）")
    matched_step_content: str | None = None
    rerank_score: float | None = None
    degraded: bool = Field(default=False, description="本次排序是否走了降级路径（如重排失败回退 RRF）")
