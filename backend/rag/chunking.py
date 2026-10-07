"""双层切分（T1.6 / PRD F-B2）：菜谱卡片文档与步骤文档的构造。

纯逻辑、零 IO，可离线单测。建索引（`scripts/build_index.py`）与 BM25 语料
（`rag/retriever.py`）都必须走这里的唯一构造点，保证「向量里 embed 的文本」
与「关键词检索的语料」是同一份，检索结果才可解释。

两层的分工：

- **卡片级**（`recipe_embeddings`）：菜名 + 简介 + 食材，粗召回一道菜。
- **步骤级**（`recipe_steps.embedding`）：步骤原文，按技法/细节精取（如「怎么勾芡」）。

单条上下文必须 ≤ 模型窗口的 60%（PRD F-B2）。BGE-M3 窗口 8192 token，
60% ≈ 4900 token；中文一卡实测几百字，这里再用 `MAX_CARD_CHARS` 做防御性截断。
"""

from __future__ import annotations

from collections.abc import Sequence

INGREDIENT_HEADER = "食材："

# 防御性上限：BGE-M3 窗口 8192 token 的 60%，按中文 1 字 ≈ 1 token 保守取 4000 字。
MAX_CARD_CHARS = 4000


def _clean_ingredient(raw: str | None) -> str:
    return (raw or "").strip()


def _dedupe_preserve_order(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def build_card_document(
    *,
    name: str,
    description: str | None = None,
    ingredients: Sequence[str] | None = None,
) -> str:
    """拼一张菜谱卡片的索引文本：菜名 / 简介 / 食材，逐段非空拼接，不留空行。

    食材用上游原文（``recipe_ingredients.name_raw``），按出现顺序去重；
    厨具不在此列（seed 时已只把 ``kind == "ingredient"`` 落进关联表）。
    """
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("卡片文档必须有菜名 name")

    lines = [clean_name]

    clean_description = (description or "").strip()
    if clean_description:
        lines.append(clean_description)

    names = _dedupe_preserve_order([_clean_ingredient(item) for item in (ingredients or [])])
    if names:
        lines.append(INGREDIENT_HEADER + "、".join(names))

    document = "\n".join(lines)
    return document[:MAX_CARD_CHARS]


def build_step_document(content: str) -> str:
    """步骤级索引文本：步骤原文（规范化空白即可）。

    故意**不加菜名前缀**：步骤向量的用途是按技法精取（「怎么调糖醋汁」），
    菜名会让该菜的所有步骤都强匹配菜名查询，污染步骤级排序。
    菜名上下文由检索方按 ``recipe_id`` 关联回 `recipes` 表补齐。
    """
    text = (content or "").strip()
    if not text:
        raise ValueError("步骤文档内容不能为空")
    return text
