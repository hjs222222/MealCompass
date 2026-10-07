from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.citations import CitationValidationError, validate_recommendations
from domain.models.recommendation import Recommendation
from domain.models.retrieval import RecipeCandidate


def candidate(recipe_id: str, name: str) -> RecipeCandidate:
    return RecipeCandidate(recipe_id=recipe_id, name=name, score=1.0)


def recommendation(recipe_id: str, name: str) -> Recommendation:
    return Recommendation(recipe_id=recipe_id, name=name, reason="matches the request")


@pytest.mark.parametrize(
    ("field", "value"),
    [("recipe_id", ""), ("recipe_id", "   "), ("name", ""), ("name", "   "), ("reason", ""), ("reason", "   ")],
)
def test_recommendation_rejects_blank_required_text(field: str, value: str) -> None:
    values = {"recipe_id": "r1", "name": "番茄炒蛋", "reason": "matches the request"}
    values[field] = value

    with pytest.raises(ValidationError):
        Recommendation(**values)


def test_valid_recommendation_supports_model_dump() -> None:
    item = recommendation("r1", "番茄炒蛋")

    assert item.model_dump()["recipe_id"] == "r1"


def test_valid_recommendation_is_returned() -> None:
    candidates = [candidate("r1", "番茄炒蛋")]
    recommendations = [recommendation("r1", "番茄炒蛋")]

    assert validate_recommendations(recommendations, candidates, expected_count=1) == recommendations


def test_unknown_recipe_id_is_rejected() -> None:
    with pytest.raises(CitationValidationError, match="unknown recipe_id"):
        validate_recommendations(
            [recommendation("missing", "番茄炒蛋")],
            [candidate("r1", "番茄炒蛋")],
            expected_count=1,
        )


def test_name_must_match_authoritative_candidate_name() -> None:
    with pytest.raises(CitationValidationError, match="name mismatch"):
        validate_recommendations(
            [recommendation("r1", "西红柿炒鸡蛋")],
            [candidate("r1", "番茄炒蛋")],
            expected_count=1,
        )


def test_duplicate_candidate_ids_are_rejected_even_when_names_match() -> None:
    with pytest.raises(CitationValidationError, match="duplicate candidate recipe_id"):
        validate_recommendations(
            [recommendation("r1", "番茄炒蛋")],
            [candidate("r1", "番茄炒蛋"), candidate("r1", "番茄炒蛋")],
            expected_count=1,
        )


def test_duplicate_candidate_ids_with_conflicting_names_are_rejected() -> None:
    with pytest.raises(CitationValidationError, match="conflicting names"):
        validate_recommendations(
            [recommendation("r1", "番茄炒蛋")],
            [candidate("r1", "番茄炒蛋"), candidate("r1", "西红柿炒鸡蛋")],
            expected_count=1,
        )


@pytest.mark.parametrize("expected_count", [0, -1])
def test_non_positive_expected_count_is_rejected(expected_count: int) -> None:
    with pytest.raises(CitationValidationError, match="expected_count must be at least 1"):
        validate_recommendations([], [], expected_count=expected_count)


def test_wrong_recommendation_count_is_rejected() -> None:
    with pytest.raises(CitationValidationError, match="expected 3 recommendations"):
        validate_recommendations(
            [recommendation("r1", "番茄炒蛋")],
            [candidate("r1", "番茄炒蛋"), candidate("r2", "红烧肉")],
        )


def test_duplicate_recipe_ids_are_rejected() -> None:
    with pytest.raises(CitationValidationError, match="duplicate recipe_id"):
        validate_recommendations(
            [recommendation("r1", "番茄炒蛋"), recommendation("r1", "番茄炒蛋")],
            [candidate("r1", "番茄炒蛋")],
            expected_count=2,
        )


def test_blank_recipe_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="must not be blank"):
        recommendation("   ", "番茄炒蛋")


def test_valid_three_recommendations_preserve_order() -> None:
    candidates = [candidate("r1", "番茄炒蛋"), candidate("r2", "红烧肉"), candidate("r3", "清炒西兰花")]
    recommendations = [
        recommendation("r3", "清炒西兰花"),
        recommendation("r1", "番茄炒蛋"),
        recommendation("r2", "红烧肉"),
    ]

    assert validate_recommendations(recommendations, candidates) == recommendations
