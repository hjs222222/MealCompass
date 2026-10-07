"""T1.6 双层切分：先写测试（纯逻辑，离线可跑）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rag.chunking import INGREDIENT_HEADER, MAX_CARD_CHARS, build_card_document, build_step_document

# ------------------------------------------------------------------ 卡片级


def test_card_document_contains_name_description_and_ingredients() -> None:
    doc = build_card_document(
        name="西红柿炒鸡蛋",
        description="国民下饭菜，酸甜可口。",
        ingredients=["西红柿", "鸡蛋", "食用油", "盐", "糖", "葱花"],
    )
    lines = doc.split("\n")
    assert lines[0] == "西红柿炒鸡蛋"
    assert lines[1] == "国民下饭菜，酸甜可口。"
    assert lines[2] == INGREDIENT_HEADER + "西红柿、鸡蛋、食用油、盐、糖、葱花"


def test_card_document_omits_empty_sections_without_blank_lines() -> None:
    doc = build_card_document(name="白灼虾", description=None, ingredients=["虾"])
    assert doc == "白灼虾\n食材：虾"

    doc_no_ingredients = build_card_document(name="半成品意面", description="加热即可", ingredients=[])
    assert doc_no_ingredients == "半成品意面\n加热即可"
    assert INGREDIENT_HEADER not in doc_no_ingredients


def test_card_document_dedupes_ingredients_keeping_first_order() -> None:
    # 上游「必备原料」和「计算」两段可能重复列同一食材
    doc = build_card_document(name="茶叶蛋", ingredients=["鸡蛋", "鸡蛋", None, "  ", "八角", "八角"])
    assert doc.endswith(INGREDIENT_HEADER + "鸡蛋、八角")


def test_card_document_requires_name() -> None:
    with pytest.raises(ValueError):
        build_card_document(name="   ")


def test_card_document_is_truncated_to_window_limit() -> None:
    doc = build_card_document(name="超长菜名", description="测" * 10_000)
    assert len(doc) <= MAX_CARD_CHARS


def test_real_recipe_cards_all_fit_under_window_limit() -> None:
    """用真实 372 道菜验证 PRD F-B2：单条上下文 ≤ 模型窗口 60%。"""
    source = Path(__file__).resolve().parents[2].parent / "data" / "recipes" / "howtocook.json"
    if not source.exists():
        pytest.skip("先跑 scripts.import_howtocook.py 生成 howtocook.json")

    payload = json.loads(source.read_text(encoding="utf-8"))
    lengths = []
    for recipe in payload:
        ingredients = [item["name"] for item in (recipe.get("ingredients") or []) if item.get("kind") == "ingredient"]
        doc = build_card_document(
            name=recipe["name"],
            description=recipe.get("description"),
            ingredients=ingredients,
        )
        lengths.append(len(doc))
    assert len(payload) == 372
    assert max(lengths) <= MAX_CARD_CHARS


# ------------------------------------------------------------------ 步骤级


def test_step_document_is_stripped_raw_content() -> None:
    assert build_step_document("  热锅冷油，下蛋液翻炒。\n") == "热锅冷油，下蛋液翻炒。"


def test_step_document_rejects_blank() -> None:
    with pytest.raises(ValueError):
        build_step_document("   ")
