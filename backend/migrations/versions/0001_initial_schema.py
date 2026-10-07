"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-06

对应 `docs/ARCHITECTURE.md` §3.1 与 `backend/infra/tables.py`。
两者的漂移由 `tests/unit/test_schema_metadata.py::test_migration_tables_match_metadata` 拦截。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

EMBEDDING_DIM = 1024
EMPTY_ARRAY = sa.text("'[]'::jsonb")
EMPTY_OBJECT = sa.text("'{}'::jsonb")
NOW = sa.text("now()")


def _pk() -> sa.Column:
    return sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=NOW)


def _updated_at() -> sa.Column:
    return sa.Column(
        "updated_at",
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=NOW,
        onupdate=sa.text("now()"),
    )


def _jsonb_array(name: str) -> sa.Column:
    return sa.Column(name, JSONB, nullable=False, server_default=EMPTY_ARRAY)


def upgrade() -> None:
    # pgvector：镜像里已带扩展，这里只是确保装上
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------- 用户
    op.create_table(
        "users",
        _pk(),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        _created_at(),
    )

    op.create_table(
        "user_profiles",
        _pk(),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        _jsonb_array("taste_preferences"),
        _jsonb_array("hard_constraints"),
        _jsonb_array("soft_preferences"),
        _jsonb_array("tools_available"),
        sa.Column("skill_level", sa.String(20)),
        sa.Column("servings", sa.SmallInteger),
        _updated_at(),
    )

    # ------------------------------------------------------------- 食材
    op.create_table(
        "ingredients",
        _pk(),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("category", sa.String(32)),
    )

    op.create_table(
        "ingredient_aliases",
        _pk(),
        sa.Column(
            "ingredient_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ingredients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias", sa.String(64), nullable=False, unique=True),
    )

    # ------------------------------------------------------------- 菜谱
    op.create_table(
        "recipes",
        _pk(),
        sa.Column("slug", sa.String(160), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("category", sa.String(40), nullable=False, server_default=sa.text("''")),
        sa.Column("description", sa.Text),
        sa.Column("difficulty", sa.SmallInteger),
        sa.Column("time_minutes", sa.Integer),
        sa.Column("nutrition", JSONB, nullable=False, server_default=EMPTY_OBJECT),
        _jsonb_array("tools"),
        _jsonb_array("tags"),
        _jsonb_array("aliases"),
        _jsonb_array("images"),
        _jsonb_array("external_images"),
        sa.Column("extra", sa.Text),
        sa.Column("servings_text", sa.String(160)),
        sa.Column("source", sa.String(40), nullable=False, server_default=sa.text("'HowToCook'")),
        sa.Column("source_path", sa.String(300), nullable=False, unique=True),
        sa.Column("source_url", sa.String(400)),
        sa.Column("license", sa.String(40)),
        _created_at(),
        sa.CheckConstraint("difficulty IS NULL OR difficulty BETWEEN 1 AND 5", name="ck_recipes_difficulty"),
    )
    op.create_index("ix_recipes_category", "recipes", ["category"])
    op.create_index("ix_recipes_time_minutes", "recipes", ["time_minutes"])
    op.create_index("ix_recipes_difficulty", "recipes", ["difficulty"])
    op.create_index("ix_recipes_tags", "recipes", ["tags"], postgresql_using="gin")

    op.create_table(
        "recipe_steps",
        _pk(),
        sa.Column(
            "recipe_id",
            UUID(as_uuid=True),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_no", sa.Integer, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
        sa.UniqueConstraint("recipe_id", "step_no", name="uq_recipe_steps_recipe_step"),
    )
    op.create_index("ix_recipe_steps_recipe_id", "recipe_steps", ["recipe_id"])

    op.create_table(
        "recipe_ingredients",
        _pk(),
        sa.Column(
            "recipe_id",
            UUID(as_uuid=True),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # 词表未收录的食材没有标准实体，这里必须可空
        sa.Column(
            "ingredient_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ingredients.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name_raw", sa.String(120), nullable=False),
        sa.Column("amount_text", sa.String(80)),
        sa.Column("amount_min", sa.Float),
        sa.Column("amount_max", sa.Float),
        sa.Column("unit", sa.String(20)),
        sa.Column("note", sa.String(200)),
        sa.Column("optional", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("per_serving", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_recipe_ingredients_recipe_id", "recipe_ingredients", ["recipe_id"])
    op.create_index("ix_recipe_ingredients_ingredient_id", "recipe_ingredients", ["ingredient_id"])

    op.create_table(
        "recipe_embeddings",
        sa.Column(
            "recipe_id",
            UUID(as_uuid=True),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
        sa.Column("tsv", TSVECTOR),
    )
    op.create_index("ix_recipe_embeddings_tsv", "recipe_embeddings", ["tsv"], postgresql_using="gin")

    # 向量索引：HNSW（m=16, ef_construction=64），规范 §5.2 明确不用 IVFFlat
    hsnw_options = {"m": 16, "ef_construction": 64}
    op.create_index(
        "ix_recipe_embeddings_embedding_hnsw",
        "recipe_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with=hsnw_options,
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_recipe_steps_embedding_hnsw",
        "recipe_steps",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with=hsnw_options,
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    # ------------------------------------------------------------- 对话
    op.create_table(
        "conversations",
        _pk(),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", JSONB, nullable=False, server_default=EMPTY_OBJECT),
        _created_at(),
        _updated_at(),
    )

    op.create_table(
        "messages",
        _pk(),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("metadata", JSONB, nullable=False, server_default=EMPTY_OBJECT),
        _created_at(),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])

    # -------------------------------------------------------- 反馈 / 清单
    op.create_table(
        "feedbacks",
        _pk(),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recipe_id",
            UUID(as_uuid=True),
            sa.ForeignKey("recipes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(16), nullable=False),
        _created_at(),
    )
    op.create_index("ix_feedbacks_user_id", "feedbacks", ["user_id"])

    op.create_table(
        "shopping_lists",
        _pk(),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        _jsonb_array("recipe_ids"),
        _jsonb_array("items"),
        _created_at(),
    )
    op.create_index("ix_shopping_lists_user_id", "shopping_lists", ["user_id"])


def downgrade() -> None:
    """可回滚（规范 §5.3 要求）。"""
    op.drop_table("shopping_lists")
    op.drop_table("feedbacks")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("recipe_embeddings")
    op.drop_table("recipe_ingredients")
    op.drop_table("recipe_steps")
    op.drop_table("recipes")
    op.drop_table("ingredient_aliases")
    op.drop_table("ingredients")
    op.drop_table("user_profiles")
    op.drop_table("users")
