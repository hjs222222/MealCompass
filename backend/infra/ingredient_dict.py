"""数据词典加载器（IO 层）：从 `data/ingredients/aliases.yaml` 构建归一化词典。

分层说明：领域层的 :mod:`domain.ingredients` 不做 IO，文件读取放在这里。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from domain.ingredients import CanonicalIngredient, IngredientDictionary

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DICTIONARY_PATH = REPO_ROOT / "data" / "ingredients" / "aliases.yaml"


def load_dictionary(path: Path | None = None) -> IngredientDictionary:
    """读取 YAML 词典。缺文件或格式错误时抛异常（宁可失败也不静默降级）。"""
    target = path or DEFAULT_DICTIONARY_PATH
    if not target.exists():
        raise FileNotFoundError(f"食材词典不存在：{target}")

    raw: Any = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    entries = raw.get("canonical")
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"食材词典格式错误（缺少 canonical 列表）：{target}")

    parsed = [
        CanonicalIngredient(
            name=str(item["name"]).strip(),
            category=str(item.get("category") or "其他").strip(),
            aliases=tuple(str(alias).strip() for alias in item.get("aliases") or ()),
        )
        for item in entries
    ]
    return IngredientDictionary(parsed)
