from domain.models.recipe_details import RecipeDetails
from domain.recipe_time import extract_time_text


def test_explicit_total_duration_is_preserved_as_source_text() -> None:
    assert extract_time_text("这是一道家常菜。从备料到完成约需 40 分钟。") == "从备料到完成约需 40 分钟。"


def test_range_and_hour_unit_are_not_reduced_to_one_number() -> None:
    assert extract_time_text("全程含腌制约需 2–2.5 小时。") == "全程含腌制约需 2–2.5 小时。"


def test_no_duration_is_not_estimated() -> None:
    assert extract_time_text("一道家常菜。") is None


def test_chinese_numerals_and_completion_word_are_preserved() -> None:
    source = "制作非常简单，全程只需大约十分钟即可完成。"
    assert extract_time_text(source) == source


def test_total_duration_with_days_and_active_time_qualifier_is_preserved() -> None:
    source = "预计制作总时长约 2 天，其中实际动手时间仅需大约 1 小时。"
    assert extract_time_text(source) == source


def test_step_duration_without_total_context_is_rejected() -> None:
    assert extract_time_text("腌制 5-10 分钟后下锅。") is None


def test_source_duration_phrasings_are_kept_verbatim() -> None:
    cases = [
        "从煮蛋到冷藏入味大约需要一个半小时。",
        "前后仅需大约一 刻钟。",
        "从准备到烘烤完成，算上隔夜冷藏时间大约需要 10-14 小时。",
        "新手也能在 5 分钟里轻松搞定。",
        "整个过程大约只需 5 分钟。",
        "初学者也能在 大约 2 小时完成。",
    ]
    for source in cases:
        assert extract_time_text(source) == source


def test_remaining_source_contexts_and_alternatives_are_preserved() -> None:
    cases = [
        "从备料到享用只需约 20 分钟。",
        "预计全部完成约需 1.5 小时。",
        "炒煮过程约需 30 分钟。",
        "煮好的米饭只要几分钟就能拌出一碗香喷喷的主食。",
        "实际操作约需 30 分钟，另需至少 2 小时冷藏定型。",
        "从备料到出锅，使用高压锅约需 45 分钟，瓦罐慢炖则需 1 小时出头。",
    ]
    for source in cases:
        assert extract_time_text(source) == source


def test_step_totals_and_storage_do_not_become_recipe_totals() -> None:
    for source in [
        "烘烤总时长约 30 分钟。",
        "腌制总共需要 2 小时。",
        "放入冰箱冷藏 4 小时后即可享用。",
        "冷藏可保存 5 天。",
        "1. 小火煮 10 分钟即可完成。",
    ]:
        assert extract_time_text(source) is None


def test_details_default_lists_are_independent() -> None:
    first = RecipeDetails()
    first.steps.append("切菜")
    assert RecipeDetails().steps == []
