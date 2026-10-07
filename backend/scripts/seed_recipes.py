"""把 HowToCook 解析产物与食材词典灌进数据库（T1.1b）。

## 幂等设计（可以反复跑）

| 表 | 冲突键 | 策略 |
| --- | --- | --- |
| `ingredients` | `name` | `ON CONFLICT DO UPDATE`（更新分类） |
| `ingredient_aliases` | `alias` | `ON CONFLICT DO UPDATE`（重指向标准食材） |
| `recipes` | `id`（由 source_path 派生的确定性 UUID） | `ON CONFLICT DO UPDATE` |
| `recipe_ingredients` / `recipe_steps` | 无天然唯一键 | 先按 `recipe_id` 删干净再插入 |

## 用法（在 `backend/` 下）

```powershell
docker compose up -d                              # 起 postgres + redis
.venv\\Scripts\\python.exe -m alembic upgrade head  # 建表
.venv\\Scripts\\python.exe -m scripts.seed_recipes   # 灌数据（可重复跑）
```
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

# 允许 `python scripts/seed_recipes.py` 直接运行
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncConnection  # noqa: E402

from domain.ingredients import IngredientDictionary  # noqa: E402
from infra.db import get_engine  # noqa: E402
from infra.ingredient_dict import load_dictionary  # noqa: E402
from infra.tables import (  # noqa: E402
    ingredient_aliases,
    ingredients,
    recipe_ingredients,
    recipe_steps,
    recipes,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECIPES_JSON = REPO_ROOT / "data" / "recipes" / "howtocook.json"

CHUNK_SIZE = 500


# --------------------------------------------------------------------- 纯映射


def nutrition_of(recipe: dict[str, Any]) -> dict[str, Any]:
    """上游没有热量就留 ``None``，绝不编造。"""
    return {"calories_kcal": recipe.get("calories_kcal"), "source": recipe.get("calories_source")}


def recipe_row(recipe: dict[str, Any]) -> dict[str, Any]:
    """菜谱 JSON → `recipes` 一行（保持 JSON 原生类型，UUID 转换在入库层做）。"""
    return {
        "id": recipe["id"],
        "slug": recipe["slug"],
        "name": recipe["name"],
        "category": recipe.get("category") or "",
        "description": recipe.get("description"),
        "difficulty": recipe.get("difficulty"),
        "time_minutes": recipe.get("time_minutes"),
        "nutrition": nutrition_of(recipe),
        "tools": recipe.get("tools") or [],
        "tags": recipe.get("tags") or [],
        "aliases": recipe.get("aliases") or [],
        "images": recipe.get("images") or [],
        "external_images": recipe.get("external_images") or [],
        "extra": recipe.get("extra"),
        "servings_text": recipe.get("servings_text"),
        "source": recipe.get("source") or "HowToCook",
        "source_path": recipe.get("source_path") or "",
        "source_url": recipe.get("source_url"),
        "license": recipe.get("license"),
    }


def ingredient_rows(recipe: dict[str, Any], ingredient_ids: dict[str, str]) -> list[dict[str, Any]]:
    """菜谱的食材 → `recipe_ingredients` 行。厨具不算食材；词表未收录的 ``ingredient_id`` 为 None。"""
    rows: list[dict[str, Any]] = []
    for item in recipe.get("ingredients") or []:
        if item.get("kind") != "ingredient":
            continue
        canonical = item.get("canonical")
        rows.append(
            {
                "recipe_id": recipe["id"],
                "ingredient_id": ingredient_ids.get(canonical) if canonical else None,
                "name_raw": item["name"],
                "amount_text": item.get("amount_text"),
                "amount_min": item.get("amount_min"),
                "amount_max": item.get("amount_max"),
                "unit": item.get("unit"),
                "note": item.get("note"),
                "optional": bool(item.get("optional")),
                "per_serving": bool(item.get("per_serving")),
            }
        )
    return rows


def step_rows(recipe: dict[str, Any]) -> list[dict[str, Any]]:
    """操作步骤 → `recipe_steps` 行，``step_no`` 从 1 开始。"""
    return [
        {"recipe_id": recipe["id"], "step_no": index, "content": content}
        for index, content in enumerate(recipe.get("steps") or [], start=1)
    ]


# --------------------------------------------------------------------- 入库


def _as_uuid(value: str | None) -> uuid.UUID | None:
    return uuid.UUID(str(value)) if value else None


async def _upsert_ingredients(conn: AsyncConnection, dictionary: IngredientDictionary) -> dict[str, str]:
    rows = [{"name": entry.name, "category": entry.category} for entry in dictionary.entries()]
    statement = pg_insert(ingredients).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["name"],
        set_={"category": statement.excluded.category},
    ).returning(ingredients.c.name, ingredients.c.id)
    result = await conn.execute(statement)
    return {name: str(identifier) for name, identifier in result.all()}


async def _upsert_aliases(
    conn: AsyncConnection,
    dictionary: IngredientDictionary,
    ingredient_ids: dict[str, str],
) -> int:
    rows = [
        {"alias": alias, "ingredient_id": _as_uuid(ingredient_ids[entry.name])}
        for entry in dictionary.entries()
        for alias in entry.aliases
        if entry.name in ingredient_ids
    ]
    if not rows:
        return 0
    statement = pg_insert(ingredient_aliases).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["alias"],
        set_={"ingredient_id": statement.excluded.ingredient_id},
    )
    await conn.execute(statement)
    return len(rows)


async def _upsert_recipes(conn: AsyncConnection, rows: list[dict[str, Any]]) -> int:
    payload = [{**row, "id": _as_uuid(row["id"])} for row in rows]
    for start in range(0, len(payload), CHUNK_SIZE):
        chunk = payload[start : start + CHUNK_SIZE]
        statement = pg_insert(recipes).values(chunk)
        statement = statement.on_conflict_do_update(
            index_elements=["id"],
            set_={
                column: statement.excluded[column]
                for column in (
                    "slug",
                    "name",
                    "category",
                    "description",
                    "difficulty",
                    "time_minutes",
                    "nutrition",
                    "tools",
                    "tags",
                    "aliases",
                    "images",
                    "external_images",
                    "extra",
                    "servings_text",
                    "source",
                    "source_path",
                    "source_url",
                    "license",
                )
            },
        )
        await conn.execute(statement)
    return len(payload)


async def _insert_chunked(conn: AsyncConnection, table: sa.Table, rows: list[dict[str, Any]]) -> None:
    for start in range(0, len(rows), CHUNK_SIZE):
        await conn.execute(table.insert(), rows[start : start + CHUNK_SIZE])


async def seed_all(
    recipes_path: Path | None = None,
    dictionary_path: Path | None = None,
) -> dict[str, int]:
    """把菜谱 JSON 与食材词典灌进库，返回各表写入行数。可重复执行。"""
    source = Path(recipes_path or DEFAULT_RECIPES_JSON)
    payload: list[dict[str, Any]] = json.loads(source.read_text(encoding="utf-8"))
    dictionary = load_dictionary(dictionary_path)

    recipe_rows = [recipe_row(item) for item in payload]
    recipe_ids = [_as_uuid(row["id"]) for row in recipe_rows]

    all_ingredient_rows: list[dict[str, Any]] = []
    all_step_rows: list[dict[str, Any]] = []

    async with get_engine().begin() as conn:
        ingredient_ids = await _upsert_ingredients(conn, dictionary)
        alias_count = await _upsert_aliases(conn, dictionary, ingredient_ids)
        recipe_count = await _upsert_recipes(conn, recipe_rows)

        # 没有天然唯一键，先清后插保证幂等（删的是本批次菜谱的从属行）
        await conn.execute(sa.delete(recipe_ingredients).where(recipe_ingredients.c.recipe_id.in_(recipe_ids)))
        await conn.execute(sa.delete(recipe_steps).where(recipe_steps.c.recipe_id.in_(recipe_ids)))

        for item in payload:
            all_ingredient_rows.extend(
                {
                    **row,
                    "recipe_id": _as_uuid(row["recipe_id"]),
                    "ingredient_id": _as_uuid(row["ingredient_id"]),
                }
                for row in ingredient_rows(item, ingredient_ids)
            )
            all_step_rows.extend({**row, "recipe_id": _as_uuid(row["recipe_id"])} for row in step_rows(item))

        await _insert_chunked(conn, recipe_ingredients, all_ingredient_rows)
        await _insert_chunked(conn, recipe_steps, all_step_rows)

    return {
        "recipes": recipe_count,
        "recipe_ingredients": len(all_ingredient_rows),
        "recipe_steps": len(all_step_rows),
        "ingredients": len(ingredient_ids),
        "ingredient_aliases": alias_count,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把菜谱 JSON + 食材词典灌进 PostgreSQL")
    parser.add_argument("--recipes", type=Path, default=DEFAULT_RECIPES_JSON, help="菜谱 JSON 路径")
    parser.add_argument("--dictionary", type=Path, default=None, help="食材词典 YAML 路径")
    args = parser.parse_args(argv)

    if not args.recipes.exists():
        print(f"菜谱 JSON 不存在：{args.recipes}", file=sys.stderr)
        print("先跑：python -m scripts.import_howtocook", file=sys.stderr)
        return 1

    counts = asyncio.run(seed_all(args.recipes, args.dictionary))
    print("入库完成（幂等，可重复执行）：")
    for table, count in counts.items():
        print(f"  {table:<20} {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
