"""T1.1b 数据入库：先写测试。

两部分：
- 纯映射函数（离线可测）
- 集成测试：真跑一遍 seed，验证**幂等**（跑两次结果一致）
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import asyncpg
import pytest

from core.config import get_settings
from scripts.seed_recipes import (
    ingredient_rows,
    nutrition_of,
    recipe_row,
    seed_all,
    step_rows,
)

BACKEND = Path(__file__).resolve().parents[2]

SAMPLE = {
    "id": "09a38e13-2a8a-5cb6-b9da-2bef65f9d14f",
    "slug": "aquatic-咖喱炒蟹",
    "name": "咖喱炒蟹",
    "category": "aquatic",
    "description": "融合泰式风味的家常海鲜菜。",
    "difficulty": 4,
    "calories_kcal": 815,
    "calories_source": "HowToCook 预估",
    "time_minutes": None,
    "servings_text": "一份够 2 个人吃。",
    "ingredients": [
        {
            "name": "肉蟹",
            "kind": "ingredient",
            "amount_text": "1 只",
            "amount_min": 1.0,
            "amount_max": None,
            "unit": "只",
            "note": "大约 300g",
            "optional": False,
            "per_serving": True,
            "canonical": "螃蟹",
            "category": "水产",
        },
        {
            "name": "黑松露酱",
            "kind": "ingredient",
            "amount_text": None,
            "amount_min": None,
            "amount_max": None,
            "unit": None,
            "note": None,
            "optional": False,
            "per_serving": False,
            "canonical": None,
            "category": None,
        },
        {"name": "炒锅", "kind": "tool", "canonical": None, "category": None},
    ],
    "tools": ["炒锅"],
    "steps": ["刷洗肉蟹。", "拆蟹斩块。", "炒咖喱。"],
    "images": ["aquatic/咖喱炒蟹/成品.jpg"],
    "external_images": [],
    "extra": None,
    "source": "HowToCook",
    "source_path": "aquatic/咖喱炒蟹/咖喱炒蟹.md",
    "source_url": "https://github.com/Anduin2017/HowToCook/blob/x/aquatic/咖喱炒蟹/咖喱炒蟹.md",
    "license": "Unlicense",
}


# ---------------------------------------------------------------- 纯映射


def test_recipe_row_maps_all_columns() -> None:
    row = recipe_row(SAMPLE)
    assert row["id"] == SAMPLE["id"]
    assert row["slug"] == "aquatic-咖喱炒蟹"
    assert row["difficulty"] == 4
    assert row["time_minutes"] is None
    assert row["images"] == ["aquatic/咖喱炒蟹/成品.jpg"]
    assert json.loads(json.dumps(row["nutrition"])) == {"calories_kcal": 815, "source": "HowToCook 预估"}


def test_nutrition_keeps_unknown_as_none() -> None:
    """上游没标热量就留 null，不编造。"""
    assert nutrition_of({"calories_kcal": None, "calories_source": None}) == {
        "calories_kcal": None,
        "source": None,
    }


def test_ingredient_rows_skip_tools_and_map_canonical() -> None:
    rows = ingredient_rows(SAMPLE, {"螃蟹": "11111111-1111-1111-1111-111111111111"})
    assert len(rows) == 2  # 炒锅不算食材
    by_name = {r["name_raw"]: r for r in rows}
    assert by_name["肉蟹"]["ingredient_id"] == "11111111-1111-1111-1111-111111111111"
    assert by_name["肉蟹"]["amount_min"] == 1.0
    # 词表未收录 -> ingredient_id 为 None，但原始写法必须留档
    assert by_name["黑松露酱"]["ingredient_id"] is None


def test_step_rows_are_numbered_from_one() -> None:
    rows = step_rows(SAMPLE)
    assert [r["step_no"] for r in rows] == [1, 2, 3]
    assert rows[0]["content"] == "刷洗肉蟹。"


# ---------------------------------------------------------------- 集成


def _dsn() -> str:
    return get_settings().database_url.replace("postgresql+asyncpg://", "postgresql://")


async def _db_available() -> bool:
    try:
        connection = await asyncio.wait_for(asyncpg.connect(_dsn()), timeout=3)
    except Exception:
        return False
    await connection.close()
    return True


DB_UP = asyncio.run(_db_available())
requires_db = pytest.mark.skipif(not DB_UP, reason="Postgres 未启动（docker compose up -d）")

RECIPES_JSON = BACKEND.parent / "data" / "recipes" / "howtocook.json"


@requires_db
def test_seed_is_idempotent_and_loads_everything() -> None:
    """跑两遍，行数必须完全一致 —— 这是 seed 脚本最核心的验收点。"""
    if not RECIPES_JSON.exists():
        pytest.skip("先跑 scripts/import_howtocook.py 生成 howtocook.json")

    async def scenario() -> tuple[dict[str, int], dict[str, int]]:
        first = await seed_all(RECIPES_JSON)
        second = await seed_all(RECIPES_JSON)
        return first, second

    first, second = asyncio.run(scenario())

    assert first["recipes"] == 372
    assert first["recipe_ingredients"] > 3000
    assert first == second

    async def counts() -> dict[str, int]:
        connection = await asyncpg.connect(_dsn())
        try:
            tables = ("recipes", "recipe_ingredients", "recipe_steps", "ingredients", "ingredient_aliases")
            result = {}
            for table in tables:
                result[table] = await connection.fetchval(f"select count(*) from {table}")
            return result
        finally:
            await connection.close()

    actual = asyncio.run(counts())
    assert actual["recipes"] == 372
    assert actual["recipe_steps"] == first["recipe_steps"]
    assert actual["ingredients"] >= 100
    assert actual["ingredient_aliases"] >= 100
