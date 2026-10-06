"""领域层：纯逻辑，无 IO。"""

from domain.models.recipe import Ingredient, Recipe

__all__ = ["Ingredient", "Recipe"]
