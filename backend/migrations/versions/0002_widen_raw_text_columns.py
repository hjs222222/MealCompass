"""widen raw upstream text columns

Revision ID: 0002_widen_raw_text
Revises: 0001_initial
Create Date: 2026-10-06

`servings_text` 与 `amount_text` 承载的是「不编造」原则下必须留档的上游原文，
长度不该由我们拍板：实测 HowToCook 里有 257 字的 `servings_text`，
原来的 VARCHAR(160) 会让入库直接失败（value too long）。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_widen_raw_text"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "recipes",
        "servings_text",
        existing_type=sa.String(160),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.alter_column(
        "recipe_ingredients",
        "amount_text",
        existing_type=sa.String(80),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "recipe_ingredients",
        "amount_text",
        existing_type=sa.Text(),
        type_=sa.String(80),
        existing_nullable=True,
    )
    op.alter_column(
        "recipes",
        "servings_text",
        existing_type=sa.Text(),
        type_=sa.String(160),
        existing_nullable=True,
    )
