"""T1.6/T1.8 中文分词：tsv 与 BM25 的共同入口。"""

from __future__ import annotations

from rag.tokenization import tokenize, tokenize_joined


def test_tokenize_splits_chinese_and_drops_punctuation() -> None:
    tokens = tokenize("西红柿炒鸡蛋，放盐3g！")
    assert "西红柿" in tokens
    assert "炒鸡蛋" in tokens  # jieba 词典把「炒鸡蛋」收为整词
    assert "放盐" in tokens
    assert "3g" in tokens
    # 标点不能进词项（否则 tsv / BM25 词项被标点污染）
    assert all(token.strip() and token not in {"，", "！"} for token in tokens)


def test_tokenize_keeps_single_char_food_words() -> None:
    # 「虾」「蟹」这种单字食材必须保留，单字在中文查询里有区分度
    tokens = tokenize("白灼虾")
    assert "虾" in tokens


def test_tokenize_handles_empty() -> None:
    assert tokenize("") == []
    assert tokenize_joined("，！！") == ""


def test_tokenize_joined_is_space_separated() -> None:
    joined = tokenize_joined("麻婆豆腐的家常做法")
    assert joined.split(" ") == tokenize("麻婆豆腐的家常做法")
    assert " " in joined  # 多词句子必须被空格隔开，才能喂 to_tsvector('simple')
