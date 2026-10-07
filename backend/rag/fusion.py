"""RRF（Reciprocal Rank Fusion）融合：把多路召回的排名合成一个排名（T1.8）。

纯函数、零 IO。公式（标准 RRF，Cormack et al. 2009）::

    score(d) = Σ 1 / (k + rank_channel(d))

- 各通道只贡献**排名**，不直接用原始分（向量余弦与 BM25 分数量纲不同，无法相加）。
- ``k=60`` 是论文默认值：越大，头部优势越小、多路共识越重要。
- 同分按「首次被哪一路先召回」稳定排序，避免结果抖动。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

DEFAULT_RRF_K = 60


def reciprocal_rank_fusion(
    ranked_lists: Mapping[str, Sequence[str]],
    *,
    k: int = DEFAULT_RRF_K,
    top_n: int | None = None,
) -> list[tuple[str, float, list[str]]]:
    """把 ``{通道名: [recipe_id, ...按相关度降序]}`` 融合成 ``[(id, rrf分, 命中通道)]``。

    - 同一路内的重复 id 只计第一次（防御性，正常召回不该有重复）。
    - 分数降序；同分按 id 在各路中的**最早出现位置**升序，保证确定性。
    """
    scores: dict[str, float] = {}
    channels: dict[str, list[str]] = {}
    first_seen: dict[str, tuple[int, int]] = {}

    for channel_index, (channel_name, ranked_ids) in enumerate(ranked_lists.items()):
        seen_in_channel: set[str] = set()
        for rank, recipe_id in enumerate(ranked_ids, start=1):
            if recipe_id in seen_in_channel:
                continue
            seen_in_channel.add(recipe_id)
            scores[recipe_id] = scores.get(recipe_id, 0.0) + 1.0 / (k + rank)
            channels.setdefault(recipe_id, []).append(channel_name)
            first_seen.setdefault(recipe_id, (channel_index, rank))

    ordered_ids = sorted(
        scores,
        key=lambda recipe_id: (-scores[recipe_id], first_seen[recipe_id]),
    )
    if top_n is not None:
        ordered_ids = ordered_ids[:top_n]
    return [(recipe_id, scores[recipe_id], channels[recipe_id]) for recipe_id in ordered_ids]
