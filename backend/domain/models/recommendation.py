"""推荐领域模型（纯数据，无 IO）。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from domain.models.recipe_details import RecipeDetails


class Recommendation(BaseModel):
    """一条可展示且可追溯到检索候选的菜谱推荐。"""

    recipe_id: str
    name: str
    reason: str
    missing_ingredients: list[str] = Field(default_factory=list)
    substitutions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list, description="原始菜谱步骤，按原序排列；缺失时为空")
    details: RecipeDetails | None = Field(default=None, description="数据库原始菜谱详情；读取失败时为 None")
    time_minutes: int | None = None

    @field_validator("recipe_id", "name", "reason")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value
