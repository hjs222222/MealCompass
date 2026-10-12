"""Authoritative recipe content for display; never produced by the LLM."""

from pydantic import BaseModel, Field

from domain.models.recipe import Ingredient


class RecipeDetails(BaseModel):
    description: str | None = None
    time_text: str | None = None
    difficulty: int | None = None
    calories_kcal: int | None = None
    calories_source: str | None = None
    servings_text: str | None = None
    ingredients: list[Ingredient] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    external_images: list[str] = Field(default_factory=list)
    extra: str | None = None
    source_url: str | None = None
