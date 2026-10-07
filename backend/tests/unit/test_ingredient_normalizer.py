"""T1.3 食材归一化：先写测试，再写实现。

样例来自 HowToCook 真实数据（1394 种食材的去重结果）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from domain.ingredients import CanonicalIngredient, IngredientDictionary
from infra.ingredient_dict import load_dictionary

DICTIONARY = IngredientDictionary(
    [
        CanonicalIngredient(name="番茄", category="蔬果", aliases=("西红柿", "蕃茄")),
        CanonicalIngredient(name="大蒜", category="蔬果", aliases=("蒜", "蒜瓣", "蒜头")),
        CanonicalIngredient(name="生抽", category="调料", aliases=("酱油",)),
        CanonicalIngredient(name="老抽", category="调料", aliases=()),
        CanonicalIngredient(name="淀粉", category="调料", aliases=("生粉", "玉米淀粉")),
        CanonicalIngredient(name="盐", category="调料", aliases=("食盐", "食用盐")),
    ]
)


# ---------------------------------------------------------------- 精确匹配


def test_resolve_exact_canonical_name() -> None:
    entry = DICTIONARY.resolve("番茄")
    assert entry is not None and entry.name == "番茄"


def test_resolve_alias_to_canonical() -> None:
    entry = DICTIONARY.resolve("西红柿")
    assert entry is not None and entry.name == "番茄"


def test_resolve_returns_category() -> None:
    entry = DICTIONARY.resolve("生粉")
    assert entry is not None and entry.category == "调料"


def test_resolve_tolerates_whitespace_and_fullwidth() -> None:
    assert DICTIONARY.resolve("  西 红 柿  ").name == "番茄"  # type: ignore[union-attr]
    assert DICTIONARY.resolve("食盐").name == "盐"  # type: ignore[union-attr]


def test_resolve_strips_parenthetical_note() -> None:
    entry = DICTIONARY.resolve("生抽（推荐海天金标）")
    assert entry is not None and entry.name == "生抽"


def test_resolve_does_not_cross_match_similar_names() -> None:
    """生抽 / 老抽 是两种东西，不能被模糊匹配串在一起。"""
    assert DICTIONARY.resolve("老抽").name == "老抽"  # type: ignore[union-attr]
    assert DICTIONARY.resolve("生抽王").name == "生抽"  # type: ignore[union-attr]


# ---------------------------------------------------------------- 形态后缀


def test_resolve_strips_preparation_suffix() -> None:
    assert DICTIONARY.resolve("蒜末").name == "大蒜"  # type: ignore[union-attr]
    assert DICTIONARY.resolve("蒜瓣").name == "大蒜"  # type: ignore[union-attr]
    assert DICTIONARY.resolve("食盐末").name == "盐"  # type: ignore[union-attr]


def test_resolve_returns_none_for_unknown_ingredient() -> None:
    assert DICTIONARY.resolve("黑松露酱") is None


def test_resolve_returns_none_for_blank() -> None:
    assert DICTIONARY.resolve("   ") is None


def test_resolve_handles_trailing_colon() -> None:
    """上游「计算」区有 `盐：` 这种带冒号的写法。"""
    assert DICTIONARY.resolve("盐：").name == "盐"  # type: ignore[union-attr]
    assert DICTIONARY.resolve("食盐:").name == "盐"  # type: ignore[union-attr]


def test_resolve_handles_trailing_liang() -> None:
    """`盐量` / `油量` 是「计算」区按份数推算时留下的写法。"""
    assert DICTIONARY.resolve("盐量").name == "盐"  # type: ignore[union-attr]


def test_resolve_keeps_original_name_in_entry() -> None:
    entry = DICTIONARY.resolve("西红柿")
    assert entry is not None and entry.name == "番茄"


# ---------------------------------------------------------------- 词典构造


def test_duplicate_alias_across_entries_raises() -> None:
    with pytest.raises(ValueError, match="同义词冲突"):
        IngredientDictionary(
            [
                CanonicalIngredient(name="番茄", category="蔬果", aliases=("西红柿",)),
                CanonicalIngredient(name="圣女果", category="蔬果", aliases=("西红柿",)),
            ]
        )


def test_aliases_property_lists_every_accepted_name() -> None:
    assert set(DICTIONARY.aliases_of("番茄")) == {"番茄", "西红柿", "蕃茄"}


def test_size_counts_canonical_entries() -> None:
    assert len(DICTIONARY) == 6


def test_entries_exposes_canonical_list() -> None:
    """入库脚本要遍历所有标准食材（种子数据），不能去摸私有属性。"""
    assert {entry.name for entry in DICTIONARY.entries()} == {"番茄", "大蒜", "生抽", "老抽", "淀粉", "盐"}


# ---------------------------------------------------------------- YAML 加载（IO 层）

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_load_dictionary_from_yaml() -> None:
    loaded = load_dictionary(FIXTURES / "aliases_mini.yaml")

    assert len(loaded) == 2
    assert loaded.resolve("西红柿").name == "番茄"  # type: ignore[union-attr]
    assert loaded.resolve("盐").category == "调料"  # type: ignore[union-attr]


def test_load_dictionary_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_dictionary(FIXTURES / "__not_exist__.yaml")


def test_load_dictionary_rejects_empty_canonical() -> None:
    with pytest.raises(ValueError, match="格式错误"):
        load_dictionary(FIXTURES / "aliases_empty.yaml")


def test_load_default_dictionary_has_real_data() -> None:
    """仓库里的 data/ingredients/aliases.yaml 必须存在且能加载（PRD F-B1 的归一化前提）。"""
    loaded = load_dictionary()
    assert len(loaded) >= 50
    assert loaded.resolve("西红柿").name == "番茄"  # type: ignore[union-attr]
