"""Display source duration prose without estimating a numeric cooking time."""

import re

# Qualitative numbers (几/十几/半/一刻钟) deliberately remain qualitative.
_DURATION = re.compile(
    r"(?:\d+(?:[.．]\d+)?|[零〇一二两三四五六七八九十百几数半]+|一刻钟)"
    r"(?:\s*个)?(?:\s*半)?\s*(?:分钟|小时|天|秒钟|刻钟)"
)
_SENTENCE = re.compile(r"[^。！？\n]+[。！？]?")
_START_TO_FINISH = re.compile(
    r"从(?:备料|准备|备菜|配料|和面|揉面|煮蛋|泡茶|刷洗|处理|预热|开罐|开火|烧水|煮水|煮饭|煮面|拌馅|切配|洗米|洗菜|切菜|解冻|腌制|泡米|打蛋|搅拌|头)"
    r"[^。！？\n]{0,32}?(?:到|至)(?:完成|出锅|出炉|上桌|成菜|品尝|熬好|粥香满屋|冷藏(?:完成|入味)|烘烤完成|焖好|烙好|煮好|煮熟|炒好|装盘|盛盘|蒸好|拌好|烤好|盛碗|享用|入味)"
)
_TOTAL = re.compile(
    r"全程|总(?:共|计|耗时|时长|时间)|整体(?:制作|耗时)|制作(?:时长|时间|耗时|过程)|"
    r"烹饪(?:时长|时间|过程)|预计(?:制作|耗时|用时|全部完成)|整个(?:制作|烹饪|过程)|正式制作|从头到尾|前后|准备加(?:熬制|调制)"
)
_COMPLETION = re.compile(r"(?:分钟|小时|刻钟)[^。！？]{0,18}(?:完成|搞定|享用|上桌|端上|端出|吃上|喝上|成型|调好|拌好)")
# Keep exclusions and waiting periods visible, even when no single total is stated.
_QUALIFIED = re.compile(
    r"实际(?:操作|动手)|动手操作|不算冷藏|除去.{0,12}(?:准备|浸泡)|另需|再冷冻|再冷藏|提前.{0,12}(?:腌|浸泡|准备)"
)
_STEP = re.compile(r"^(?:\d+[.、]\s*)?(?:腌制|浸泡|冷藏|冷冻|预热|翻炒|炒煮|焖煮|蒸|烘烤|煮|烤|炸|静置|加热|等待)")
_STORAGE = re.compile(r"(?:冷藏|冷冻)(?:可保存|保存)")


def extract_time_text(description: str | None) -> str | None:
    """Return literal introductory duration prose, retaining its limits and alternatives.

    No durations are added or converted. Standalone step timings are not promoted to
    total time; introductions stating active time plus waiting retain both clauses.
    The input is a recipe description, not an entire procedure or Markdown document.
    """
    if not description:
        return None
    candidates: list[str] = []
    for match in _SENTENCE.finditer(description):
        sentence = match.group(0).strip()
        if not _DURATION.search(sentence) or (_STORAGE.search(sentence) and not _COMPLETION.search(sentence)):
            continue
        # The same words can mean a cooking step; never promote a bare step.
        if re.match(r"^(?:\d+[.、]\s*)?(?:烘烤|腌制)总", sentence):
            continue
        span = _START_TO_FINISH.search(sentence)
        if span:
            candidates.append(sentence[span.start() :])
        elif (
            _TOTAL.search(sentence)
            or _QUALIFIED.search(sentence)
            or sentence.startswith("炒煮过程")
            or (sentence.startswith("煮好的米饭") and "拌出" in sentence)
            or (
                _COMPLETION.search(sentence)
                and not _STEP.search(sentence)
                and not re.match(r"^(?:\d+[.、]\s*|放入|小火|大火)", sentence)
            )
        ):
            candidates.append(sentence)
    return " ".join(candidates) if candidates else None
