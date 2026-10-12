"""Read authoritative recipe details for the final recommendation IDs."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.models.recipe import Ingredient
from domain.models.recipe_details import RecipeDetails
from domain.recipe_time import extract_time_text
from infra.tables import recipe_ingredients, recipe_steps, recipes


class SqlRecipeDetailsReader:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get_details(self, recipe_ids: Sequence[str]) -> dict[str, RecipeDetails]:
        if not recipe_ids:
            return {}
        async with self._engine.connect() as conn:
            recipe_rows = (await conn.execute(sa.select(recipes).where(recipes.c.id.in_(recipe_ids)))).mappings().all()
            step_rows = (
                await conn.execute(
                    sa.select(recipe_steps.c.recipe_id, recipe_steps.c.step_no, recipe_steps.c.content)
                    .where(recipe_steps.c.recipe_id.in_(recipe_ids))
                    .order_by(recipe_steps.c.recipe_id, recipe_steps.c.step_no)
                )
            ).all()
            ingredient_rows = (
                (
                    await conn.execute(
                        sa.select(recipe_ingredients)
                        .where(recipe_ingredients.c.recipe_id.in_(recipe_ids))
                        .order_by(recipe_ingredients.c.recipe_id, recipe_ingredients.c.id)
                    )
                )
                .mappings()
                .all()
            )
        steps: dict[str, list[str]] = {}
        for recipe_id, _, content in step_rows:
            steps.setdefault(str(recipe_id), []).append(content)
        ingredients: dict[str, list[Ingredient]] = {}
        for row in ingredient_rows:
            ingredients.setdefault(str(row["recipe_id"]), []).append(
                Ingredient(
                    name=row["name_raw"],
                    amount_text=row["amount_text"],
                    amount_min=row["amount_min"],
                    amount_max=row["amount_max"],
                    unit=row["unit"],
                    note=row["note"],
                    optional=row["optional"],
                    per_serving=row["per_serving"],
                )
            )
        details: dict[str, RecipeDetails] = {}
        for row in recipe_rows:
            recipe_id = str(row["id"])
            nutrition = row["nutrition"] or {}
            details[recipe_id] = RecipeDetails(
                description=row["description"],
                time_text=extract_time_text(row["description"]),
                difficulty=row["difficulty"],
                calories_kcal=nutrition.get("calories_kcal"),
                calories_source=nutrition.get("source"),
                servings_text=row["servings_text"],
                ingredients=ingredients.get(recipe_id, []),
                tools=row["tools"] or [],
                steps=steps.get(recipe_id, []),
                images=row["images"] or [],
                external_images=row["external_images"] or [],
                extra=row["extra"],
                source_url=row["source_url"],
            )
        return details
