"""Batch-read original cooking steps for validated recommendation IDs."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncEngine

from infra.tables import recipe_steps


class SqlRecipeStepsReader:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def get_steps(self, recipe_ids: Sequence[str]) -> dict[str, list[str]]:
        if not recipe_ids:
            return {}
        statement = (
            sa.select(recipe_steps.c.recipe_id, recipe_steps.c.content)
            .where(recipe_steps.c.recipe_id.in_(recipe_ids))
            .order_by(recipe_steps.c.recipe_id, recipe_steps.c.step_no)
        )
        async with self._engine.connect() as conn:
            rows = (await conn.execute(statement)).all()
        result: dict[str, list[str]] = {}
        for recipe_id, content in rows:
            result.setdefault(str(recipe_id), []).append(content)
        return result
