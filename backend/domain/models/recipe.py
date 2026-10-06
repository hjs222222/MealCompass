"""菜谱领域模型（纯数据，无 IO）。

字段设计原则（来自 `docs/PRD.md` 与 `docs/DATA_SOURCES.md`）：

- **不编造**：上游没有的字段一律留 ``None``，并保留原文（``amount_text``），绝不猜。
- ``time_minutes`` 上游不提供 → 恒为 ``None``，由规则层按难度兜底并标注不确定。
- 只保留热量，不做蛋白质 / GI / 钠推断（本项目不做医学人群细分）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Ingredient(BaseModel):
    """一条食材 / 厨具。

    ``amount_text`` 永远保留上游原文（如 ``"适量"``、``"400 g"``），
    数值字段解析不出时为 ``None``，供下游区分「没有用量」与「用量是 0」。
    """

    name: str
    kind: Literal["ingredient", "tool"] = "ingredient"
    amount_text: str | None = None
    amount_min: float | None = None
    amount_max: float | None = None
    unit: str | None = None
    note: str | None = None
    optional: bool = False
    per_serving: bool = False


class Recipe(BaseModel):
    """一道结构化菜谱。"""

    id: str = Field(description="确定性 UUID（由 source_path 派生，可重复导入）")
    slug: str
    name: str
    category: str = ""
    description: str | None = None

    difficulty: int | None = Field(default=None, ge=1, le=5)
    calories_kcal: int | None = None
    calories_source: str | None = None
    time_minutes: int | None = Field(default=None, description="上游不提供，恒为 None")

    servings_text: str | None = None
    ingredients: list[Ingredient] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    images: list[str] = Field(
        default_factory=list,
        description="数据集内相对路径（相对 data/raw/howtocook），按文中出现顺序；首张可作封面",
    )
    external_images: list[str] = Field(
        default_factory=list,
        description="上游托管的外链图片（未下载到本地），前端可直接热链",
    )
    extra: str | None = None

    source: str = "HowToCook"
    source_path: str = ""
    source_url: str = ""
    license: str = "Unlicense"
