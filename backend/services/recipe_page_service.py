"""Read one source-backed recipe page without invoking the recommendation agent."""

from domain.models.recipe_details import RecipePage
from domain.ports import RecipePageReader


class RecipePageService:
    def __init__(self, reader: RecipePageReader) -> None:
        self._reader = reader

    async def get_page(self, recipe_id: str) -> RecipePage | None:
        return await self._reader.get_page(recipe_id)
