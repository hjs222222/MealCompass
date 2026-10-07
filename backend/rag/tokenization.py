"""中文分词：PG ``tsv`` 全文索引与 rank-bm25 的**唯一**分词入口。

为什么不用 PG 自带中文分词：官方 ``pgvector/pgvector:pg16`` 镜像没有 zhparser，
而 BM25（T1.8）本来就要在应用层用 jieba。两边共用同一个分词函数，保证
``recipe_embeddings.tsv`` 与 BM25 语料的词项一致，避免「库里切一套、检索切一套」。

- 写入 tsv：``to_tsvector('simple', ' '.join(tokenize(doc)))``（词之间用空格喂给 simple 配置）。
- BM25：``BM25Okapi([tokenize(doc) for doc in docs])``。
"""

from __future__ import annotations

import functools
import re
import warnings

# Python3 里中文算 \w，所以这里只剔除标点 / 空白 / emoji / 下划线。
_PUNCT_RE = re.compile(r"[\W_]+", re.UNICODE)


@functools.lru_cache(maxsize=1)
def _jieba():
    """惰性导入：不检索的进程（如纯 API 单测）不需要加载 jieba 词典。

    jieba 0.42 包内 regex 会触发 SyntaxWarning（stderr 噪声，不影响功能），
    在 import 时静默掉，避免脚本在 PowerShell 下被误判为失败。
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        import jieba

    jieba.setLogLevel(60)  # 抑制「Building prefix dict ...」的 stderr 噪声
    return jieba


def tokenize(text: str) -> list[str]:
    """中文文本 → 词项列表（保留单字实词，如「虾」「蟹」，剔除标点与空白）。"""
    if not text:
        return []
    tokens: list[str] = []
    for piece in _jieba().lcut(text):
        token = _PUNCT_RE.sub("", piece)
        if token:
            tokens.append(token)
    return tokens


def tokenize_joined(text: str) -> str:
    """词项空格拼接，直接喂给 ``to_tsvector('simple', ...)``。"""
    return " ".join(tokenize(text))
