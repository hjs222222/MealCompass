"""T0.9 数据库 schema：先写测试。

本机没有 Docker，所以全部走**离线验证**：
1. SQLAlchemy metadata 结构断言（不连库）
2. ``alembic upgrade head --sql`` 渲染出的 DDL 断言（不连库）
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

from alembic import command
from alembic.config import Config
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CheckConstraint

from infra.tables import metadata

BACKEND = Path(__file__).resolve().parents[2]

EXPECTED_TABLES = {
    "users",
    "user_profiles",
    "ingredients",
    "ingredient_aliases",
    "recipes",
    "recipe_steps",
    "recipe_ingredients",
    "recipe_embeddings",
    "conversations",
    "messages",
    "feedbacks",
    "shopping_lists",
}


# ---------------------------------------------------------------- 表结构


def test_metadata_contains_all_expected_tables() -> None:
    assert set(metadata.tables) >= EXPECTED_TABLES


def test_recipes_has_importer_columns() -> None:
    """表结构必须能装下导入器产出的字段，否则 seed 会丢数据。"""
    columns = metadata.tables["recipes"].columns
    for name in (
        "id",
        "slug",
        "name",
        "category",
        "description",
        "difficulty",
        "time_minutes",
        "nutrition",
        "images",
        "external_images",
        "source",
        "source_path",
        "source_url",
        "license",
        "created_at",
    ):
        assert name in columns, f"recipes 缺列：{name}"


def test_recipe_ingredients_allows_unmapped_ingredient() -> None:
    """856 种食材没进词表，ingredient_id 必须可空，否则导入直接失败。"""
    assert metadata.tables["recipe_ingredients"].columns["ingredient_id"].nullable is True


def test_recipe_ingredients_keeps_raw_name() -> None:
    """归一化不改变原始写法：原文要留档，便于回溯与人工补词表。"""
    assert "name_raw" in metadata.tables["recipe_ingredients"].columns


def test_embedding_column_is_1024_dim_vector() -> None:
    column = metadata.tables["recipe_embeddings"].columns["embedding"]
    assert isinstance(column.type, Vector)
    assert column.type.dim == 1024


def test_recipe_steps_embedding_is_vector_too() -> None:
    column = metadata.tables["recipe_steps"].columns["embedding"]
    assert isinstance(column.type, Vector)
    assert column.type.dim == 1024


def test_alias_is_globally_unique() -> None:
    assert metadata.tables["ingredient_aliases"].columns["alias"].unique is True


def test_ingredient_name_is_unique() -> None:
    assert metadata.tables["ingredients"].columns["name"].unique is True


def test_json_columns_use_jsonb() -> None:
    for table, column in (
        ("recipes", "images"),
        ("recipes", "nutrition"),
        ("user_profiles", "hard_constraints"),
        ("shopping_lists", "items"),
        ("messages", "metadata"),
        ("conversations", "state"),
    ):
        assert isinstance(metadata.tables[table].columns[column].type, JSONB), f"{table}.{column}"


def test_difficulty_has_range_check() -> None:
    constraints = [item for item in metadata.tables["recipes"].constraints if isinstance(item, CheckConstraint)]
    assert any("difficulty" in str(item.sqltext) for item in constraints)


def test_all_timestamps_are_timezone_aware() -> None:
    """规范要求时间字段统一 TIMESTAMP WITH TIME ZONE。"""
    for table in metadata.tables.values():
        for column in table.columns:
            if column.name.endswith("_at"):
                assert column.type.timezone is True, f"{table.name}.{column.name} 不是 timestamptz"


def test_raw_upstream_text_columns_are_unbounded() -> None:
    """上游原文可能很长（实测 `servings_text` 有 257 字），必须用 Text 而不是 VARCHAR(n)。

    这类字段承载的是「不编造」原则下必须留档的原文，长度不该由我们拍板。
    """
    from sqlalchemy import Text

    assert isinstance(metadata.tables["recipes"].columns["servings_text"].type, Text)
    assert isinstance(metadata.tables["recipe_ingredients"].columns["amount_text"].type, Text)


# ---------------------------------------------------------------- 迁移渲染


def _render_migration() -> str:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+asyncpg://mealcompass:mealcompass@localhost:5432/mealcompass",
    )
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        command.upgrade(config, "head", sql=True)
    return buffer.getvalue()


def test_migration_renders_expected_ddl() -> None:
    sql = _render_migration()
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    for table in ("recipes", "recipe_embeddings", "ingredient_aliases", "shopping_lists"):
        assert f"CREATE TABLE {table}" in sql, f"迁移里没有建表：{table}"


def test_migration_creates_vector_and_fulltext_indexes() -> None:
    sql = _render_migration().lower()
    assert "using hnsw" in sql
    assert "vector_cosine_ops" in sql
    assert "using gin" in sql
    assert "tsvector" in sql


def test_migration_tables_match_metadata() -> None:
    """防止迁移与 `infra/tables.py` 漂移：两边建的表必须完全一致。

    （`alembic_version` 是 alembic 自己的版本表，不算业务表。）
    """
    import re

    created = set(re.findall(r"CREATE TABLE (\w+)", _render_migration())) - {"alembic_version"}
    assert created == set(metadata.tables), f"迁移与 metadata 不一致：{created ^ set(metadata.tables)}"


# ---------------------------------------------------------------- 连接配置


def test_engine_is_built_from_settings_dsn() -> None:
    """DSN 只从配置来（.env → Settings），不散落在代码里。创建 engine 不会真连库。"""
    from core.config import get_settings
    from infra.db import get_engine

    engine = get_engine()

    assert str(engine.url).startswith("postgresql+asyncpg://")
    assert engine.url.database == get_settings().database_url.rsplit("/", 1)[-1]
