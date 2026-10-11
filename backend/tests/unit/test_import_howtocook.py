"""T1.2 HowToCook 导入器：先写测试，再写实现。

样例全部取自 HowToCook 真实数据形态（见 .tmp/survey.py 的调研结论）。
"""

from __future__ import annotations

import textwrap

import pytest

from domain.ingredients import CanonicalIngredient, IngredientDictionary
from scripts.import_howtocook import (
    Ingredient,
    parse_calories,
    parse_difficulty,
    parse_ingredient_line,
    parse_ingredient_lines,
    parse_recipe_markdown,
)

# 一段贴近真实的菜谱（含 4 个标准章节）
FIXTURE = textwrap.dedent(
    """\
    # 葱烧鸡腿的做法

    葱烧鸡腿是一道只靠鸡腿和大葱两种核心食材就能完成的下饭家常菜。

    预估烹饪难度：★★
    预估卡路里：850 大卡

    ## 必备原料和工具

    - 鸡腿 2 个（约 500g）
    - 大葱 1 根
    - 生抽（推荐海天金标）
    - 料酒或花雕酒
    - 盐
    - 炒锅
    - 生姜 3-4 片（可选，主要用于去腥提香）

    ## 计算

    每次制作前需要确定计划做几份。一份正好够 2 个人吃。

    每份：

    - 鸡腿 2 个（去骨后净肉约 350g）
    - 生抽 15ml
    - 白砂糖 5g
    - 盐 2-3g
    - 食用油 15-20ml

    ## 操作

    1. 鸡腿去骨：用剪刀从鸡腿大的那头伸进去。
    2. 去骨后的鸡腿肉切成 2-3cm 的丁。
    3. 热锅，锅内放入 15-20ml 食用油。

    ## 附加内容

    如果您遵循本指南的制作流程而发现有问题或可以改进的流程，请提出 Issue。
    """
)


# ---------------------------------------------------------------- 头部解析


def test_parse_difficulty_counts_stars() -> None:
    assert parse_difficulty("预估烹饪难度：★★★") == 3
    assert parse_difficulty("预估烹饪难度：★") == 1


def test_parse_difficulty_returns_none_when_absent() -> None:
    assert parse_difficulty("没有难度信息") is None


def test_parse_calories_reads_number() -> None:
    assert parse_calories("预估卡路里：850 大卡") == 850


def test_parse_calories_returns_none_when_absent() -> None:
    assert parse_calories("没有热量信息") is None


# ------------------------------------------------------------ 用量行解析


def test_ingredient_no_amount_keeps_name_only() -> None:
    ing = parse_ingredient_line("- 盐")
    assert ing.name == "盐"
    assert ing.amount_min is None
    assert ing.amount_text is None


def test_ingredient_with_compact_unit() -> None:
    ing = parse_ingredient_line("- 生抽 15ml")
    assert (ing.name, ing.amount_min, ing.unit) == ("生抽", 15.0, "ml")


def test_ingredient_with_space_before_unit() -> None:
    ing = parse_ingredient_line("- 鳝丝 400 g")
    assert (ing.name, ing.amount_min, ing.unit) == ("鳝丝", 400.0, "g")


def test_ingredient_with_range_amount() -> None:
    ing = parse_ingredient_line("- 白糖 6-15 g")
    assert (ing.amount_min, ing.amount_max, ing.unit) == (6.0, 15.0, "g")


def test_ingredient_with_equals_separator() -> None:
    ing = parse_ingredient_line("- 小龙虾 = 2 斤")
    assert (ing.name, ing.amount_min, ing.unit) == ("小龙虾", 2.0, "斤")


def test_ingredient_with_chinese_numeral() -> None:
    ing = parse_ingredient_line("- 香叶 = 两片")
    assert (ing.name, ing.amount_min, ing.unit) == ("香叶", 2.0, "片")


def test_ingredient_with_chinese_numeral_and_tail() -> None:
    ing = parse_ingredient_line("- 葱 = 一根大葱")
    assert (ing.name, ing.amount_min, ing.unit) == ("葱", 1.0, "根")
    assert ing.note == "大葱"


def test_ingredient_strips_parenthetical_into_note() -> None:
    ing = parse_ingredient_line("- 青蟹（别称：肉蟹）")
    assert ing.name == "青蟹"
    assert ing.note == "别称：肉蟹"


def test_ingredient_marks_optional() -> None:
    ing = parse_ingredient_line("- 生姜 3-4 片（可选，主要用于去腥提香）")
    assert ing.optional is True
    assert ing.amount_min == 3.0 and ing.amount_max == 4.0 and ing.unit == "片"


def test_ingredient_detects_per_serving_multiplier() -> None:
    ing = parse_ingredient_line("- 椰浆 100ml*份数")
    assert ing.per_serving is True
    assert (ing.amount_min, ing.unit) == (100.0, "ml")


def test_ingredient_keeps_raw_text_when_amount_is_not_numeric() -> None:
    ing = parse_ingredient_line("- 盐 适量")
    assert ing.name == "盐"
    assert ing.amount_min is None
    assert ing.amount_text == "适量"


def test_ingredient_alternatives_stay_in_name() -> None:
    ing = parse_ingredient_line("- 料酒或花雕酒")
    assert ing.name == "料酒或花雕酒"


# -------------------------------------------------------------- 工具识别


def test_tool_lines_are_flagged_as_tools() -> None:
    assert parse_ingredient_line("- 炒锅").kind == "tool"
    assert parse_ingredient_line("- 烤箱").kind == "tool"


def test_tool_name_is_canonicalized() -> None:
    """上游常写「烤箱 大小不限」这类带说明的厨具，名字要收敛到关键词。"""
    assert parse_ingredient_line("- 烤箱 大小不限").name == "烤箱"
    assert parse_ingredient_line("- 不粘锅：油汇聚成滴后要散布在茄子表面").name == "不粘锅"


def test_prose_bullet_is_skipped_not_mistaken_for_ingredient() -> None:
    """「必备原料和工具」里混有整句说明，不能当成食材名。"""
    line = "- 北方大米，米和水放在电饭煲的容器内，食指触及米，水量能刚好没过食指的第一个指节"
    assert parse_ingredient_line(line).name == ""


def test_amount_with_approximate_prefix() -> None:
    ing = parse_ingredient_line("- 鲤鱼 约 3 斤")
    assert (ing.name, ing.amount_min, ing.unit) == ("鲤鱼", 3.0, "斤")


def test_amount_with_size_modifier() -> None:
    ing = parse_ingredient_line("- 桂皮 一小片")
    assert (ing.name, ing.amount_min, ing.unit) == ("桂皮", 1.0, "片")
    assert ing.note == "小"


def test_servings_text_comes_from_calc_prose() -> None:
    recipe = parse_recipe_markdown(FIXTURE, source_path="meat_dish/葱烧鸡腿.md")
    assert recipe.servings_text is not None and "2 个人吃" in recipe.servings_text


def test_food_lines_stay_ingredients() -> None:
    assert parse_ingredient_line("- 大蒜").kind == "ingredient"
    assert parse_ingredient_line("- 食用油 15ml").kind == "ingredient"


# ------------------------------------------------------------ 整篇解析


def test_parse_recipe_header_fields() -> None:
    recipe = parse_recipe_markdown(FIXTURE, source_path="meat_dish/葱烧鸡腿.md")
    assert recipe.name == "葱烧鸡腿"
    assert recipe.category == "meat_dish"
    assert recipe.difficulty == 2
    assert recipe.calories_kcal == 850
    assert recipe.description is not None and recipe.description.startswith("葱烧鸡腿是一道")


def test_parse_recipe_quantities_come_from_calc_section() -> None:
    recipe = parse_recipe_markdown(FIXTURE, source_path="meat_dish/葱烧鸡腿.md")
    by_name = {i.name: i for i in recipe.ingredients}
    # 计算区每份的用量优先于「必备原料和工具」里的粗描述
    assert by_name["生抽"].amount_min == 15.0
    assert by_name["盐"].amount_max == 3.0


def test_parse_recipe_separates_tools_from_ingredients() -> None:
    recipe = parse_recipe_markdown(FIXTURE, source_path="meat_dish/葱烧鸡腿.md")
    assert "炒锅" in recipe.tools
    assert all(i.name != "炒锅" for i in recipe.ingredients)


def test_parse_recipe_steps_are_ordered_and_cleaned() -> None:
    recipe = parse_recipe_markdown(FIXTURE, source_path="meat_dish/葱烧鸡腿.md")
    assert len(recipe.steps) == 3
    assert recipe.steps[0].startswith("鸡腿去骨")


def test_parse_recipe_keeps_extra_section() -> None:
    recipe = parse_recipe_markdown(FIXTURE, source_path="meat_dish/葱烧鸡腿.md")
    assert recipe.extra is not None and "Issue" in recipe.extra


def test_parse_recipe_time_is_unknown_not_invented() -> None:
    recipe = parse_recipe_markdown(FIXTURE, source_path="meat_dish/葱烧鸡腿.md")
    assert recipe.time_minutes is None


def test_parse_recipe_id_is_deterministic_uuid() -> None:
    a = parse_recipe_markdown(FIXTURE, source_path="meat_dish/葱烧鸡腿.md")
    b = parse_recipe_markdown(FIXTURE, source_path="meat_dish/葱烧鸡腿.md")
    assert a.id == b.id
    assert len(a.id) == 36  # uuid 字符串


def test_category_is_top_level_dir_for_nested_layout() -> None:
    """上游部分菜谱是「分类/菜名/菜名.md」的嵌套结构，分类必须取顶层目录。"""
    recipe = parse_recipe_markdown(FIXTURE, source_path="vegetable_dish/上汤娃娃菜/上汤娃娃菜.md")
    assert recipe.category == "vegetable_dish"


def test_category_is_empty_when_file_sits_at_root() -> None:
    recipe = parse_recipe_markdown(FIXTURE, source_path="孤儿菜谱.md")
    assert recipe.category == ""


def test_slug_is_derived_from_source_path_so_it_stays_unique() -> None:
    """上游有两道菜 H1 同名（`鸡蛋羹/鸡蛋羹.md` 与 `鸡蛋羹/蒸箱鸡蛋羹.md`）。

    slug 若由「分类-菜名」拼出来就会撞 `recipes.slug` 的唯一约束，
    所以必须由 source_path 派生（source_path 天然唯一）。
    """
    first = parse_recipe_markdown(FIXTURE, source_path="vegetable_dish/鸡蛋羹/鸡蛋羹.md")
    second = parse_recipe_markdown(FIXTURE, source_path="vegetable_dish/鸡蛋羹/蒸箱鸡蛋羹.md")

    assert first.slug == "vegetable_dish-鸡蛋羹-鸡蛋羹"
    assert second.slug == "vegetable_dish-鸡蛋羹-蒸箱鸡蛋羹"
    assert first.slug != second.slug


def test_parse_recipe_rejects_markdown_without_required_sections() -> None:
    with pytest.raises(ValueError, match="缺少章节"):
        parse_recipe_markdown("# 随便\n\n没有标准章节", source_path="dishes/x/y.md")


def test_ingredient_is_pydantic_model() -> None:
    """schema 要能被 Pydantic 校验，方便后续入库与 JSON 序列化。"""
    ing = Ingredient(name="盐")
    assert ing.model_dump()["name"] == "盐"


# ---------------------------------------------------------------- 配图解析

FIXTURE_WITH_IMAGES = textwrap.dedent(
    """\
    # 上汤娃娃菜的做法

    清爽解腻的一道快手汤菜。

    预估烹饪难度：★★
    预估卡路里：120 大卡

    ![成品图](./上汤娃娃菜.png)

    ## 必备原料和工具

    - 娃娃菜 1 颗
    - 皮蛋 1 个
    - 炒锅

    ## 计算

    一份够 2 个人吃。

    - 娃娃菜 1 颗
    - 皮蛋 1 个

    ## 操作

    1. 娃娃菜洗净切段。
    2. 皮蛋切丁。
    3. 上汤煮开后放入食材。

    ## 附加内容

    ![石凉粉(冰粉)成品1](./石凉粉(冰粉)成品1.jpg)
    ![外链图](https://user-images.githubusercontent.com/1/a.jpg)
    """
)


def test_recipe_images_are_dataset_relative() -> None:
    recipe = parse_recipe_markdown(FIXTURE_WITH_IMAGES, source_path="vegetable_dish/上汤娃娃菜/上汤娃娃菜.md")
    assert recipe.images[0] == "vegetable_dish/上汤娃娃菜/上汤娃娃菜.png"


def test_recipe_images_handle_parentheses_in_filename() -> None:
    """上游有 `石凉粉(冰粉)成品1.jpg` 这类带括号的文件名，不能被截断。"""
    recipe = parse_recipe_markdown(FIXTURE_WITH_IMAGES, source_path="vegetable_dish/上汤娃娃菜/上汤娃娃菜.md")
    assert "vegetable_dish/上汤娃娃菜/石凉粉(冰粉)成品1.jpg" in recipe.images


def test_recipe_external_images_are_separated_from_local_ones() -> None:
    recipe = parse_recipe_markdown(FIXTURE_WITH_IMAGES, source_path="vegetable_dish/上汤娃娃菜/上汤娃娃菜.md")
    assert recipe.external_images == ["https://user-images.githubusercontent.com/1/a.jpg"]
    assert all("http" not in path for path in recipe.images)


def test_recipe_without_images_has_empty_image_lists() -> None:
    recipe = parse_recipe_markdown(FIXTURE, source_path="meat_dish/葱烧鸡腿.md")
    assert recipe.images == []
    assert recipe.external_images == []


# ---------------------------------------------------------- 食材归一化接入


def test_parse_recipe_applies_ingredient_dictionary() -> None:
    """导入时带上词典：每味食材要落标准名与分类；词典里没有的留 None，不猜。"""
    dictionary = IngredientDictionary([CanonicalIngredient(name="生抽", category="调料", aliases=("酱油",))])

    recipe = parse_recipe_markdown(FIXTURE, source_path="meat_dish/葱烧鸡腿.md", dictionary=dictionary)

    by_name = {item.name: item for item in recipe.ingredients}
    assert by_name["生抽"].canonical == "生抽"
    assert by_name["生抽"].category == "调料"
    assert by_name["盐"].canonical is None
    assert by_name["盐"].category is None


def test_parse_recipe_without_dictionary_leaves_canonical_empty() -> None:
    recipe = parse_recipe_markdown(FIXTURE, source_path="meat_dish/葱烧鸡腿.md")
    assert all(item.canonical is None for item in recipe.ingredients)


# ------------------------------------------------ 解析层噪声过滤（T1.2c / C5）

# 「必备原料和工具」里混进来的章节小标题：整行不是食材，也不是厨具
SECTION_HEADING_LINES = [
    "- 工具",
    "* 工具",
    "- 原料",
    "- 原料:",
    "- 原料：",
    "- 食材",
    "- 调料",
    "- 配料",
    "- 调味料",
    "- 厨具",
    "- 主料",
    "- 必备原料和工具",
    "- 原料和工具",
    "  - 工具  ",
]


@pytest.mark.parametrize("line", SECTION_HEADING_LINES)
def test_section_headings_are_not_ingredients(line: str) -> None:
    """章节小标题（工具 / 原料:）被当成食材是 unmapped_top 里的头号噪声。"""
    item = parse_ingredient_line(line)
    assert item.name == ""
    assert item.kind == "ingredient"


# 说明短语 / 整句说明：不是食材名
PROSE_ONLY_LINES = [
    "- 肉量 = 份数 * 200g。",
    "* 肉量 = 份数 * 100g",
    "- 盐的用量为 1 g 每个鸡蛋。",
    "* 盐的用量为 3 g/人",
    "- 一般一个人可以食用 7～10 个水饺",
    "- 一般一个人可以食用 60ml-110ml 的米。",
    "* 一般一个人一顿可以食用",
    "* 一碗容量是 500ml。",
    "- 一个水饺约需要本身体积两倍的水",
    "- 中断大火加热的最晚时间 T",
    "- 冷藏时间 Tc",
    "- 水的体积是米饭的体积的",
    "- 果酱足够涂满一面吐司的量",
    "- 根据口味选择加或者不加糖",
    "- 根据锅的类型决策不同量的油",
    "- 每份原料可制作",
    "- 淀粉可准备每",
    "- 其中青菜体积可忽略",
    "- 原则：万物皆可酿",
    "- 调一个灵魂料汁儿",
    "- 非黑暗料理🍆",
    "- 鸡腿肉用量通常来说为",
]


@pytest.mark.parametrize("line", PROSE_ONLY_LINES)
def test_prose_lines_are_not_ingredients(line: str) -> None:
    """整句说明是「不编造」的反面：它没有名字，也没有用量，不能进库。"""
    assert parse_ingredient_line(line).name == ""


# 「XX用量为」这类把「用量说明」和「食材名」揉在一起的行，命名规则高度统一
AMOUNT_PHRASE_LINES = [
    "- 盐的用量为 3 g/人",
    "- 盐用量为 3 g/人",
    "- 盐的用量为：3g",
    "- 牛肉用量为 250 g",
    "- 鸡蛋用量为 1 个",
    "- 食用油的用量为 9 ml",
    "- 生抽酱油用量为 15ml",
    "- 孜然用量为 2 克",
    "- 十三香的用量为：3g",
    "- 热水的用量为：100ml",
    "- 鸡腿肉用量通常来说为 200 克",
]


@pytest.mark.parametrize("line", AMOUNT_PHRASE_LINES)
def test_amount_phrase_lines_are_not_ingredients(line: str) -> None:
    """「盐的用量为 3g/人」是说明句，不是食材名（食材名里的「量」另有规则，见下）。"""
    assert parse_ingredient_line(line).name == ""


# 厨具 / 耗材：必须归 kind="tool"，而不是当食材
TOOL_LINES = [
    "- 手动压汁器",
    "- 水果刀",
    "- 厨房纸",
    "- 厨房纸（可选）",
    "- 必备：厨房纸",
    "- 小碗（调酱汁用）",
    "- 小碗若干",
    "- 雪克杯",
    "- 雪克瓶",
    "- 量酒器",
    "- 调酒杯",
    "- 吧勺",
    "- 海波杯",
    "- 高球杯",
    "- 利口酒杯",
    "- 隔热手套",
    "- 一次性手套",
    "- 一次性塑料手套",
    "- 锡箔纸",
    "- 铝箔纸",
    "- 压汁器",
    "- 定时器",
    "[可选] 分蛋器",
    "- 捣药罐",
]


@pytest.mark.parametrize("line", TOOL_LINES)
def test_tools_and_consumables_are_classified_as_tool(line: str) -> None:
    """工具/耗材应进 recipe.tools；漏判会同时污染 ingredients 与 unmapped_top。"""
    item = parse_ingredient_line(line)
    assert item.kind == "tool"
    assert item.name != ""


TOOL_NAMES = [
    "手动压汁器",
    "水果刀",
    "厨房纸",
    "小碗",
    "雪克杯",
    "量酒器",
    "隔热手套",
    "锡箔纸",
    "压汁器",
    "定时器",
    "分蛋器",
    "捣药罐",
]


@pytest.mark.parametrize("name", TOOL_NAMES)
def test_tool_names_are_canonicalized(name: str) -> None:
    """「厨房纸（可选）」这类带括号/前缀的写法要收敛到关键词本身。"""
    assert parse_ingredient_line(name).name == name
    assert parse_ingredient_line(f"- 必备：{name}").name == name


def test_consumable_capacity_phrase_is_not_a_tool() -> None:
    """「一碗容量是 500ml。」是容量说明，不是碗这个厨具。"""
    assert parse_ingredient_line("- 一碗容量是 500ml。").name == ""


# 并列写法：拆成多个食材（而不是丢弃，也不是保留成一条假食材）
ENUMERATED_CASES = [
    ("- 葱、姜、蒜", ["葱", "姜", "蒜"]),
    ("* 葱、姜、蒜", ["葱", "姜", "蒜"]),
    ("- 葱、姜、蒜共 15 克", ["葱", "姜", "蒜"]),
    ("- 小葱/大葱/洋葱总量 = 兔肉斤数 * 15 克", ["小葱", "大葱", "洋葱"]),
    ("- 五花肉/瘦肉", ["五花肉", "瘦肉"]),
    ("- 盐、糖", ["盐", "糖"]),
    ("- 葱、姜", ["葱", "姜"]),
    ("- 蒜末、姜末", ["蒜末", "姜末"]),
    ("- 肉丁/肉末", ["肉丁", "肉末"]),
    ("- 白醋/米醋", ["白醋", "米醋"]),
    ("- 八角、干辣椒", ["八角", "干辣椒"]),
    ("- 黄瓜、大蒜、绿豆芽", ["黄瓜", "大蒜", "绿豆芽"]),
    ("- 生抽 / 味极鲜", ["生抽", "味极鲜"]),
    ("- 盐 + 鸡精 +", ["盐", "鸡精"]),
]


@pytest.mark.parametrize(("line", "expected"), ENUMERATED_CASES)
def test_enumerated_lines_are_split_into_separate_ingredients(line: str, expected: list[str]) -> None:
    """上游大量使用「A、B、C」「A/B/C」合并写法。

    选择**拆分**而不是丢弃：这些名字里有真实食材（葱姜蒜），
    丢掉会让菜谱少料（检索/购物清单都会失真）；拆开则每味都能各自归一化。
    """
    items = parse_ingredient_lines(line)
    assert [item.name for item in items] == expected
    assert all(item.kind == "ingredient" for item in items)


def test_single_ingredient_line_still_returns_one_item() -> None:
    items = parse_ingredient_lines("- 鸡腿 2 个（约 500g）")
    assert [item.name for item in items] == ["鸡腿"]
    assert items[0].amount_min == 2.0


def test_prose_line_returns_no_items() -> None:
    assert parse_ingredient_lines("- 一般一个人可以食用 60ml-110ml 的米。") == []


def test_tool_line_is_split_targeted_by_parser_contract() -> None:
    """``parse_ingredient_lines`` 只负责拆分；工具/食材分流由整篇解析器做。"""
    items = parse_ingredient_lines("- 炒锅")
    assert [item.name for item in items] == ["炒锅"]
    assert items[0].kind == "tool"


# 成分用量里的「量」是真实名字，不能被「XX量」规则误伤
INGREDIENT_NAMES_CONTAINING_LIANG = ["盐量", "肉量", "油量", "姜量", "蒜量"]


@pytest.mark.parametrize("name", INGREDIENT_NAMES_CONTAINING_LIANG)
def test_ingredient_names_ending_with_liang_survive(name: str) -> None:
    """「冷吃兔」里 `兔肉斤数 * 2 克` 的写法把「盐量/肉量」当名字。

    名字里有「量」不等于它是用量说明（`盐的用量为` 才是），不能一刀切。
    """
    assert parse_ingredient_line(f"- {name} = 兔肉斤数 * 2 克").name == name


def test_prose_scalars_are_not_ingredients() -> None:
    """「一般」「左右」这类虚词不该单独成行进库（真实 report 里曾出现）。"""
    for line in ("- 一般", "- 左右", "- 适量", "- 少许"):
        assert parse_ingredient_line(line).name == ""


NOISE_FIXTURE = textwrap.dedent(
    """\
    # 噪声样本菜的做法

    用来验证解析层噪声清理。

    预估烹饪难度：★★
    预估卡路里：100 大卡

    ## 必备原料和工具

    - 工具
    - 原料:
    - 五花肉 200g
    - 葱、姜、蒜
    - 厨房纸
    - 手动压汁器
    - 水果刀
    - 小碗若干
    - 盐

    ## 计算

    - 肉量 = 份数 * 200g。
    - 盐的用量为 3 g/人
    - 一般一个人可以食用 60ml-110ml 的米。

    ## 操作

    1. 五花肉切片。
    2. 下锅炒。
    """
)

EXPECTED_NOISE_INGREDIENTS = ["五花肉", "葱", "姜", "蒜", "盐"]
EXPECTED_NOISE_TOOLS = ["厨房纸", "手动压汁器", "水果刀", "小碗"]


def test_recipe_drops_section_headings_and_prose_rows() -> None:
    recipe = parse_recipe_markdown(NOISE_FIXTURE, source_path="meat_dish/噪声样本.md")
    names = [item.name for item in recipe.ingredients]

    for noise in ("工具", "原料:", "原料", "肉量", "盐的用量为", "一般一个人可以食用"):
        assert noise not in names, f"{noise} 仍被当成食材"
    assert names == EXPECTED_NOISE_INGREDIENTS


def test_recipe_routes_tools_and_consumables_to_tools() -> None:
    recipe = parse_recipe_markdown(NOISE_FIXTURE, source_path="meat_dish/噪声样本.md")
    for tool in EXPECTED_NOISE_TOOLS:
        assert tool in recipe.tools, f"{tool} 没被识别成厨具"
        assert tool not in [item.name for item in recipe.ingredients]


def test_recipe_splits_enumerated_ingredient_rows() -> None:
    recipe = parse_recipe_markdown(NOISE_FIXTURE, source_path="meat_dish/噪声样本.md")
    names = [item.name for item in recipe.ingredients]
    assert names.count("葱") == 1 and names.count("姜") == 1 and names.count("蒜") == 1


def test_recipe_keeps_section_heading_from_becoming_a_tool() -> None:
    """「工具」「原料」是标题，不是厨具名：不能因为修 unmapped 就塞进 tools 充数。"""
    recipe = parse_recipe_markdown(NOISE_FIXTURE, source_path="meat_dish/噪声样本.md")
    assert "工具" not in recipe.tools
    assert "原料:" not in recipe.tools
    assert "原料" not in recipe.tools
