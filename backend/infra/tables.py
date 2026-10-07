"""SQLAlchemy 表定义：数据库 schema 的**唯一事实源**。

与 `docs/ARCHITECTURE.md` §3.1 一一对应；字段以「导入器实际产出的数据」为准
（v0.6 起同步：`difficulty` 改 SMALLINT 并加 1-5 约束、补 `slug` / `images` /
`external_images` / `source_path` / `license` / `extra` 等列，见 ARCHITECTURE 迭代日志）。

Alembic 的 ``target_metadata`` 指向这里的 ``metadata``；迁移与它的漂移由
``tests/unit/test_schema_metadata.py`` 自动拦截。
"""

from __future__ import annotations

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID

EMBEDDING_DIM = 1024  # BGE-M3

metadata = sa.MetaData()

_EMPTY_ARRAY = sa.text("'[]'::jsonb")
_EMPTY_OBJECT = sa.text("'{}'::jsonb")
_NOW = sa.text("now()")


def _pk() -> sa.Column:
    """UUID 主键；``gen_random_uuid()`` 是 PostgreSQL 13+ 内置函数，无需扩展。"""
    return sa.Column(
        "id",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=_NOW)


def _updated_at() -> sa.Column:
    return sa.Column(
        "updated_at",
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=_NOW,
        onupdate=sa.text("now()"),
    )


def _jsonb_array(name: str) -> sa.Column:
    return sa.Column(name, JSONB, nullable=False, server_default=_EMPTY_ARRAY)


# --------------------------------------------------------------------- 用户

users = sa.Table(
    "users",
    metadata,
    _pk(),
    sa.Column("email", sa.String(320), nullable=False, unique=True),
    sa.Column("password_hash", sa.String(255), nullable=False),
    _created_at(),
)

user_profiles = sa.Table(
    "user_profiles",
    metadata,
    _pk(),
    sa.Column(
        "user_id",
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    ),
    _jsonb_array("taste_preferences"),  # ["微辣","清淡","川菜"]
    _jsonb_array("hard_constraints"),  # 规则 ID 列表（忌口/过敏、时间、厨具）
    _jsonb_array("soft_preferences"),  # 软偏好（少油少盐、菜系等）
    _jsonb_array("tools_available"),  # ["炒锅","空气炸锅"]
    sa.Column("skill_level", sa.String(20)),
    sa.Column("servings", sa.SmallInteger),
    _updated_at(),
)

# --------------------------------------------------------------------- 食材

ingredients = sa.Table(
    "ingredients",
    metadata,
    _pk(),
    sa.Column("name", sa.String(64), nullable=False, unique=True),  # 标准名
    sa.Column("category", sa.String(32)),  # 蔬果 / 肉类 / 调料 …
)

ingredient_aliases = sa.Table(
    "ingredient_aliases",
    metadata,
    _pk(),
    sa.Column(
        "ingredient_id",
        UUID(as_uuid=True),
        sa.ForeignKey("ingredients.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("alias", sa.String(64), nullable=False, unique=True),
)

# --------------------------------------------------------------------- 菜谱

recipes = sa.Table(
    "recipes",
    metadata,
    _pk(),
    sa.Column("slug", sa.String(160), nullable=False, unique=True),
    sa.Column("name", sa.String(160), nullable=False),
    sa.Column("category", sa.String(40), nullable=False, server_default=sa.text("''")),
    sa.Column("description", sa.Text),
    sa.Column("difficulty", sa.SmallInteger),  # ★ 1-5
    sa.Column("time_minutes", sa.Integer),  # 上游不提供，恒为 NULL
    sa.Column("nutrition", JSONB, nullable=False, server_default=_EMPTY_OBJECT),
    _jsonb_array("tools"),
    _jsonb_array("tags"),
    _jsonb_array("aliases"),
    _jsonb_array("images"),
    _jsonb_array("external_images"),
    sa.Column("extra", sa.Text),
    sa.Column("servings_text", sa.Text),  # 上游原文可能很长（实测 257 字）
    sa.Column("source", sa.String(40), nullable=False, server_default=sa.text("'HowToCook'")),
    sa.Column("source_path", sa.String(300), nullable=False, unique=True),
    sa.Column("source_url", sa.String(400)),
    sa.Column("license", sa.String(40)),
    _created_at(),
    sa.CheckConstraint("difficulty IS NULL OR difficulty BETWEEN 1 AND 5", name="ck_recipes_difficulty"),
)

sa.Index("ix_recipes_category", recipes.c.category)
sa.Index("ix_recipes_time_minutes", recipes.c.time_minutes)
sa.Index("ix_recipes_difficulty", recipes.c.difficulty)
sa.Index("ix_recipes_tags", recipes.c.tags, postgresql_using="gin")

recipe_steps = sa.Table(
    "recipe_steps",
    metadata,
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

recipe_ingredients = sa.Table(
    "recipe_ingredients",
    metadata,
    _pk(),
    sa.Column(
        "recipe_id",
        UUID(as_uuid=True),
        sa.ForeignKey("recipes.id", ondelete="CASCADE"),
        nullable=False,
    ),
    # 允许为空：词表未收录的食材没有标准实体，但原始写法必须留住
    sa.Column(
        "ingredient_id",
        UUID(as_uuid=True),
        sa.ForeignKey("ingredients.id", ondelete="SET NULL"),
        nullable=True,
    ),
    sa.Column("name_raw", sa.String(120), nullable=False),
    sa.Column("amount_text", sa.Text),  # 上游原文，长度不由我们拍板
    sa.Column("amount_min", sa.Float),
    sa.Column("amount_max", sa.Float),
    sa.Column("unit", sa.String(20)),
    sa.Column("note", sa.String(200)),
    sa.Column("optional", sa.Boolean, nullable=False, server_default=sa.text("false")),
    sa.Column("per_serving", sa.Boolean, nullable=False, server_default=sa.text("false")),
)

sa.Index("ix_recipe_ingredients_recipe_id", recipe_ingredients.c.recipe_id)
sa.Index("ix_recipe_ingredients_ingredient_id", recipe_ingredients.c.ingredient_id)

recipe_embeddings = sa.Table(
    "recipe_embeddings",
    metadata,
    sa.Column(
        "recipe_id",
        UUID(as_uuid=True),
        sa.ForeignKey("recipes.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column("embedding", Vector(EMBEDDING_DIM)),
    sa.Column("tsv", TSVECTOR),
)

# 向量索引：HNSW（m=16, ef_construction=64），不用 IVFFlat —— 规范 §5.2
for _table, _name in ((recipe_embeddings, "recipe_embeddings"), (recipe_steps, "recipe_steps")):
    sa.Index(
        f"ix_{_name}_embedding_hnsw",
        _table.c.embedding,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

sa.Index("ix_recipe_embeddings_tsv", recipe_embeddings.c.tsv, postgresql_using="gin")
sa.Index("ix_recipe_steps_recipe_id", recipe_steps.c.recipe_id)

# --------------------------------------------------------------------- 对话

conversations = sa.Table(
    "conversations",
    metadata,
    _pk(),
    sa.Column(
        "user_id",
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("state", JSONB, nullable=False, server_default=_EMPTY_OBJECT),  # LangGraph 快照
    _created_at(),
    _updated_at(),
)

messages = sa.Table(
    "messages",
    metadata,
    _pk(),
    sa.Column(
        "conversation_id",
        UUID(as_uuid=True),
        sa.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("role", sa.String(16), nullable=False),  # user / assistant
    sa.Column("content", sa.Text, nullable=False),
    sa.Column("metadata", JSONB, nullable=False, server_default=_EMPTY_OBJECT),
    _created_at(),
)

sa.Index("ix_messages_conversation_id", messages.c.conversation_id)

# --------------------------------------------------------------- 反馈 / 清单

feedbacks = sa.Table(
    "feedbacks",
    metadata,
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
    sa.Column("type", sa.String(16), nullable=False),  # like / dislike / favorite / cooked
    _created_at(),
)

sa.Index("ix_feedbacks_user_id", feedbacks.c.user_id)

shopping_lists = sa.Table(
    "shopping_lists",
    metadata,
    _pk(),
    sa.Column(
        "user_id",
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ),
    _jsonb_array("recipe_ids"),
    _jsonb_array("items"),  # [{"name":"番茄","amount":4,"unit":"个","checked":false}]
    _created_at(),
)

sa.Index("ix_shopping_lists_user_id", shopping_lists.c.user_id)
