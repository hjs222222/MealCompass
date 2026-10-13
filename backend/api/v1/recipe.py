"""Read-only recipe detail endpoint."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_recipe_page_service
from domain.models.recipe_details import RecipePage
from services.recipe_page_service import RecipePageService

router = APIRouter(tags=["recipes"])
RecipePageServiceDep = Annotated[RecipePageService, Depends(get_recipe_page_service)]


@router.get("/recipes/{recipe_id}", response_model=RecipePage)
async def get_recipe(recipe_id: UUID, service: RecipePageServiceDep) -> RecipePage:
    page = await service.get_page(str(recipe_id))
    if page is None:
        raise HTTPException(status_code=404, detail="菜谱不存在")
    return page
