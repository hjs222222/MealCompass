"""食材归一化（纯逻辑，无 IO）。

词表数据在 ``data/ingredients/aliases.yaml``，由 ``infra/ingredient_dict.py`` 加载后注入。

归一化策略（保守、可预测、绝不猜）：

1. **清洗**：NFKC 归一并全角转半角、去掉括号备注、去掉空白与间隔号、去掉首尾「的/儿」。
2. **精确匹配**标准名或别名。
3. **去处理形态后缀**后再匹配（``蒜末`` → ``蒜``、``土豆片`` → ``土豆``）。
4. **前缀匹配**，但仅当剩余部分是「品牌/等级」这类不改变食材身份的后缀（``生抽王`` → ``生抽``）；
   遇到 ``油/酱/汁/粉/醋/酒/糖/盐/米/面/豆/奶/肉/鱼/虾/蛋`` 这类会改变身份的字一律不匹配
   （``花生油`` 不能变成 ``花生``）。
5. 都不中 → 返回 ``None``，交给报告统计、由人来补词表。
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

PAREN_RE = re.compile(r"[（(][^（）()]*[）)]")
SPACE_RE = re.compile(r"[\s·・]+")
TRAILING_NOISE_RE = re.compile(r"[：:，,。.、；;!！?？]+$")
TRIM_CHARS = "的儿"
TRAILING_QUANTITY_SUFFIX = "量"  # 上游「计算」区会写 `盐量` / `油量`

# 处理形态：切完还是同一个食材
FORM_SUFFIXES = (
    "末",
    "碎",
    "丝",
    "片",
    "丁",
    "块",
    "段",
    "粒",
    "瓣",
    "泥",
    "蓉",
    "条",
    "圈",
    "颗",
    "根",
    "个",
    "把",
    "颗",
)

# 这些字改变食材身份，前缀匹配时必须拒绝
IDENTITY_SUFFIXES = (
    "油",
    "酱",
    "汁",
    "粉",
    "醋",
    "酒",
    "糖",
    "盐",
    "米",
    "面",
    "豆",
    "奶",
    "肉",
    "鱼",
    "虾",
    "蛋",
    "菜",
    "果",
)


@dataclass(frozen=True)
class CanonicalIngredient:
    """一个标准食材及其别名。"""

    name: str
    category: str = "其他"
    aliases: tuple[str, ...] = ()


def clean_name(text: str) -> str:
    """把任意写法洗成可比较的键。

    处理：全角转半角 → 去括号备注 → 去空白 → 去尾部标点 → 去尾部「的/儿」 → 去尾部「量」。
    """
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = PAREN_RE.sub("", normalized)
    normalized = SPACE_RE.sub("", normalized)
    normalized = TRAILING_NOISE_RE.sub("", normalized)
    normalized = normalized.strip(TRIM_CHARS)
    if normalized.endswith(TRAILING_QUANTITY_SUFFIX) and len(normalized) > 1:
        normalized = normalized[: -len(TRAILING_QUANTITY_SUFFIX)]
    return normalized


class IngredientDictionary:
    """别名 → 标准食材 的反向索引。"""

    def __init__(self, entries: Iterable[CanonicalIngredient]) -> None:
        self._entries: list[CanonicalIngredient] = []
        self._by_key: dict[str, CanonicalIngredient] = {}
        for entry in entries:
            name = clean_name(entry.name)
            if not name:
                continue
            canonical = CanonicalIngredient(
                name=name,
                category=entry.category or "其他",
                aliases=tuple(alias for alias in entry.aliases if clean_name(alias)),
            )
            self._entries.append(canonical)
            for key in (name, *(clean_name(alias) for alias in canonical.aliases)):
                existing = self._by_key.get(key)
                if existing is not None and existing.name != canonical.name:
                    raise ValueError(f"同义词冲突：{key} 同时指向 {existing.name} 与 {canonical.name}")
                self._by_key[key] = canonical

    def __len__(self) -> int:
        return len(self._entries)

    def entries(self) -> tuple[CanonicalIngredient, ...]:
        """全部标准食材（种子数据导入用）。"""
        return tuple(self._entries)

    def aliases_of(self, canonical_name: str) -> tuple[str, ...]:
        entry = self._by_key.get(clean_name(canonical_name))
        return (entry.name, *entry.aliases) if entry else ()

    def resolve(self, raw_name: str) -> CanonicalIngredient | None:
        """把任意写法解析成标准食材；未收录返回 ``None``。"""
        key = clean_name(raw_name)
        if not key:
            return None

        entry = self._by_key.get(key)
        if entry is not None:
            return entry

        for suffix in FORM_SUFFIXES:
            if key.endswith(suffix) and len(key) > len(suffix):
                entry = self._by_key.get(key[: -len(suffix)])
                if entry is not None:
                    return entry

        return self._prefix_match(key)

    def _prefix_match(self, key: str) -> CanonicalIngredient | None:
        """``生抽王`` → ``生抽``；``花生油`` 不允许匹配到 ``花生``。

        两道保险：
        - 别名至少 2 个字（否则 ``蛋`` 会把 ``蛋糕`` 也吸过来、``水`` 会吸 ``水果``）
        - 剩余部分的首字若属于 :data:`IDENTITY_SUFFIXES`，说明换了食材，拒绝匹配
        """
        best: CanonicalIngredient | None = None
        for alias, entry in self._by_key.items():
            if len(alias) < 2 or len(alias) >= len(key) or not key.startswith(alias):
                continue
            remainder = key[len(alias) :]
            if remainder[0] in IDENTITY_SUFFIXES:
                continue
            if best is None or len(alias) > len(best.name):
                best = entry
        return best
