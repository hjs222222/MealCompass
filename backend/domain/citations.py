"""推荐引用校验（纯 domain 逻辑，无 IO）。"""

from __future__ import annotations

from collections.abc import Sequence

from domain.models.recommendation import Recommendation
from domain.models.retrieval import RecipeCandidate


class CitationValidationError(ValueError):
    """推荐无法与检索候选建立可信引用时抛出的领域错误。"""


def validate_recommendations(
    recommendations: Sequence[Recommendation],
    candidates: Sequence[RecipeCandidate],
    *,
    expected_count: int = 3,
) -> list[Recommendation]:
    """校验推荐数量及其对候选菜谱的精确引用，并保持输入顺序。"""
    if expected_count < 1:
        raise CitationValidationError("expected_count must be at least 1")
    if len(recommendations) != expected_count:
        raise CitationValidationError(f"expected {expected_count} recommendations, got {len(recommendations)}")

    authoritative_names: dict[str, str] = {}
    for candidate in candidates:
        previous_name = authoritative_names.get(candidate.recipe_id)
        if previous_name is not None:
            if previous_name != candidate.name:
                raise CitationValidationError(f"conflicting names for candidate recipe_id: {candidate.recipe_id}")
            raise CitationValidationError(f"duplicate candidate recipe_id: {candidate.recipe_id}")
        authoritative_names[candidate.recipe_id] = candidate.name

    seen_ids: set[str] = set()
    for recommendation in recommendations:
        recipe_id = recommendation.recipe_id
        if not recipe_id.strip():
            raise CitationValidationError("blank recipe_id")
        if recipe_id in seen_ids:
            raise CitationValidationError(f"duplicate recipe_id: {recipe_id}")
        seen_ids.add(recipe_id)
        if recipe_id not in authoritative_names:
            raise CitationValidationError(f"unknown recipe_id: {recipe_id}")
        if recommendation.name != authoritative_names[recipe_id]:
            raise CitationValidationError(f"name mismatch for recipe_id: {recipe_id}")

    return list(recommendations)
