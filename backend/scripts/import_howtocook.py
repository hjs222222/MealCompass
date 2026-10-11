"""HowToCook Markdown → 结构化菜谱 JSON（任务 T1.2 / T1.2b）。

输入：``data/raw/howtocook/<category>/<菜名>.md``（见 ``docs/DATA_SOURCES.md``）
输出：``data/recipes/howtocook.json`` + ``data/recipes/import_report.json``

用法（在 ``backend/`` 下）::

    .venv\\Scripts\\python.exe -m scripts.import_howtocook
    .venv\\Scripts\\python.exe -m scripts.import_howtocook --limit 5 --print

解析原则
--------

1. **不编造**：上游没写的字段留 ``None``，原始文本进 ``amount_text``；
   解析不出用量的行进报告等人工确认，绝不猜数字。
2. 用量优先取 ``## 计算``（每份），``## 必备原料和工具`` 只用来补名字与厨具。
3. ``time_minutes`` 上游不提供 → 恒为 ``None``（由规则层按难度兜底并标注不确定）。
4. 厨具识别是启发式关键词表：命中即收敛到关键词本身；整句说明既不算食材也不算厨具，直接丢弃。
5. 上游有两种目录布局：``分类/菜名.md`` 与 ``分类/菜名/菜名.md``，分类一律取**顶层目录**。
6. 配图按原文件名保留，转成**数据集内相对路径**（前端详情页直接取用）；外链图单独存 ``external_images``。
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
import uuid
from collections import Counter
from pathlib import Path

# 允许 `python scripts/import_howtocook.py` 直接运行
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.ingredients import IngredientDictionary  # noqa: E402
from domain.models.recipe import Ingredient, Recipe  # noqa: E402
from infra.ingredient_dict import load_dictionary  # noqa: E402

# --------------------------------------------------------------------------- 常量

UPSTREAM_URL = "https://github.com/Anduin2017/HowToCook"
UPSTREAM_COMMIT = "a2d45c6984dff9ee941da0e7c452f7965965d962"
SOURCE_NAME = "HowToCook"
SOURCE_LICENSE = "Unlicense"
CALORIES_SOURCE = "HowToCook 预估"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_ROOT = REPO_ROOT / "data" / "raw" / "howtocook"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "recipes" / "howtocook.json"
DEFAULT_REPORT = REPO_ROOT / "data" / "recipes" / "import_report.json"

REQUIRED_SECTIONS = ("必备原料和工具", "计算", "操作")

H1_RE = re.compile(r"^#\s+(?P<title>.+?)\s*$", re.M)
H2_SPLIT_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.M)
DIFFICULTY_RE = re.compile(r"预估烹饪难度：\s*(★+)")
CALORIE_RE = re.compile(r"预估卡路里：\s*(\d+)")
BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?P<body>.+?)\s*$")
STEP_START_RE = re.compile(r"^\s*(?:\d+[.)]|[-*+])\s+")
PAREN_RE = re.compile(r"[（(](?P<note>[^（）()]*)[）)]")
SERVING_MULTIPLIER_RE = re.compile(r"\s*[*×xX]\s*份数\s*$")
APPROX_PREFIX_RE = re.compile(r"^(?:约|大约|大概|差不多|近)\s*")
APPROX_SUFFIX_RE = re.compile(r"\s*(?:约|大约|大概|差不多)$")
PROSE_PUNCT_RE = re.compile(r"[，。！？；：]")
# 图片语法：允许文件名里带一层括号（上游有 `石凉粉(冰粉)成品1.jpg`）
IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<url>[^()\s]*(?:\([^()]*\)[^()\s]*)*)\)")

NUM = r"\d+(?:\.\d+)?"
_UNITS = (
    "kg|mg|ml|g|L|l|克|千克|公斤|斤|两|毫升|升|"
    "个|只|根|片|瓣|粒|颗|棵|朵|条|块|段|张|把|勺|汤匙|茶匙|杯|碗|包|袋|罐|听|扎|滴|寸|头"
)
NUM_AMOUNT_RE = re.compile(
    rf"^(?P<min>{NUM})(?:\s*[-~—至]\s*(?P<max>{NUM}))?"
    rf"\s*(?P<size>[大小])?\s*(?P<unit>{_UNITS})?\s*(?P<tail>.*)$"
)
CN_NUM = {
    "一": 1.0,
    "二": 2.0,
    "两": 2.0,
    "三": 3.0,
    "四": 4.0,
    "五": 5.0,
    "六": 6.0,
    "七": 7.0,
    "八": 8.0,
    "九": 9.0,
    "十": 10.0,
    "半": 0.5,
}
CN_AMOUNT_RE = re.compile(
    rf"^(?P<cn>[一二两三四五六七八九十半]+)\s*(?P<size>[大小])?\s*(?P<unit>{_UNITS})?\s*(?P<tail>.*)$"
)
NON_NUMERIC_AMOUNTS = ("适量", "少许", "若干", "随量", "按需", "看情况")

PROSE_MAX_LEN = 20
PROSE_MIN_LEN = 12

#: 列表里混进来的**章节小标题**（清洗掉冒号/空白后精确匹配）。它们既不是食材也不是厨具。
SECTION_HEADINGS = frozenset(
    {
        "工具",
        "原料",
        "食材",
        "调料",
        "配料",
        "调味料",
        "调味品",
        "佐料",
        "辅料",
        "厨具",
        "主料",
        "必备原料和工具",
        "原料和工具",
        "主要原料",
        "所需原料",
        "所需食材",
    }
)

#: 只有虚词、没有实体的行（真实 report 的 unmapped_top 里出现过）
SCALAR_ONLY_NAMES = frozenset(
    {"一般", "左右", "适量", "少许", "若干", "随量", "按需", "看情况", "一些", "少量", "都可", "均可"}
)

#: 名字里含这些词说明它是**说明句**而不是食材名（如「盐的用量为」「一碗容量是」）
PROSE_NAME_MARKERS = (
    "用量",
    "容量",
    "体积",
    "重量",
    "数量",
    "比例",
    "浓度",
    "直径",
    "厚度",
    "长度",
    "宽度",
    "分量",
    "份量",
    "克数",
    "斤数",
    "时间",
)
#: 以这些词开头的行是描述而不是名字（如「根据口味选择加或者不加糖」）
PROSE_NAME_PREFIXES = ("根据", "其中", "原则", "调一个", "一般", "每份", "一碗")
#: 名字里含这些片段说明是整句说明
PROSE_NAME_SUBSTRINGS = (
    "可以食用",
    "可准备",
    "可忽略",
    "可制作",
    "足够",
    "取决于",
    "黑暗料理",
    "需要",
)
#: 用量表达式里引用这些**非食材变量**时，该行是「缩放规则」而不是一份食材清单
PROSE_AMOUNT_VARIABLES = ("份数",)

#: 名字尾部残留的说明后缀：「盐**的用量为**」「鸡腿肉**用量通常来说为**」。
#: 只认**说明量词**（用量/容量/…），不认裸「量」——`盐量` / `肉量` 是真实名字。
NAME_SUFFIX_RE = re.compile(
    r"(?:的)?(?:用量|容量|体积|重量|数量|分量|份量|克数|斤数|比例|浓度|直径|厚度|长度|宽度)"
    r"(?:通常来说|一般来说|一般|大概|大约|通常)?(?:为|是)?$"
)

#: 并列写法分隔符：上游大量使用「A、B、C」「A/B/C」「A + B」。
#: 三种情况**不算**分隔符：
#: 1. 两侧是数字 —— 否则「- 洋葱 1/2 个」会被拆坏；
#: 2. 后面跟「人 / 份 / 位 / 天 / 餐」—— 那是**每人份**标记（`黄瓜 100g/人`），
#:    不是并列；它会被 :func:`_parse_amount` 当作 tail 留在 note 里。
ENUMERATION_SEP_RE = re.compile(r"(?<!\d)(?<!\d[ \t])[、/+](?![ \t]*(?:\d|人|份|位|天|餐))")
#: 拆分前先切掉的「总量说明」尾巴（「葱、姜、蒜共 15 克」「洋葱总量 = …」）
ENUMERATION_TAIL_RE = re.compile(r"(?:总量|总用量|共|合计|以上).*$")
#: markdown 相对链接：`[蔗糖糖浆](../../condiment/蔗糖糖浆.md)` → 取链接文字。
#: 不处理的话，链接 URL 里的 `/` 会被并列拆分规则切出一个叫 `..` 的假食材。
MD_LINK_RE = re.compile(r"\[(?P<text>[^\]]*)\]\([^()]*(?:\([^()]*\)[^()]*)*\)")
#: 行首标签：「[可选]」「必备：」这类前缀要剥掉再识别
OPTIONAL_PREFIX_RE = re.compile(r"^\s*(?:\[可选\]|【可选】)\s*")
REQUIRED_LABEL_RE = re.compile(r"^\s*(?:必备|必需|需要)\s*[:：]\s*")

# 启发式厨具关键词：宁可漏判（归为食材）也不要误伤食材名
TOOL_KEYWORDS = (
    "炒锅",
    "汤锅",
    "平底锅",
    "不粘锅",
    "奶锅",
    "砂锅",
    "铁锅",
    "高压锅",
    "压力锅",
    "电压力锅",
    "蒸锅",
    "蒸屉",
    "蒸笼",
    "蒸架",
    "屉布",
    "电饭煲",
    "电炖锅",
    "空气炸锅",
    "电饼铛",
    "烤箱",
    "烤炉",
    "微波炉",
    "电磁炉",
    "燃气灶",
    "灶台",
    "电水壶",
    "烧水壶",
    "热水壶",
    "料理机",
    "破壁机",
    "豆浆机",
    "搅拌机",
    "绞肉机",
    "厨师机",
    "打蛋器",
    "面包机",
    "咖啡机",
    "温度计",
    "厨房秤",
    "电子秤",
    "量杯",
    "量勺",
    "擀面杖",
    "案板",
    "砧板",
    "菜刀",
    "刀具",
    "剪刀",
    "削皮刀",
    "刨丝器",
    "擦丝器",
    "漏勺",
    "漏网",
    "滤网",
    "筛子",
    "面粉筛",
    "锅铲",
    "汤勺",
    "炒勺",
    "食品夹",
    "夹子",
    "筷子",
    "牙签",
    "竹签",
    "锡纸",
    "油纸",
    "烘焙纸",
    "保鲜膜",
    "保鲜袋",
    "密封袋",
    "烤盘",
    "烤架",
    "烤网",
    "模具",
    "裱花袋",
    "棉线",
    "厨房纸",
    "吸油纸",
    "水果刀",
    "压汁器",
    "手动压汁器",
    "分蛋器",
    "隔热手套",
    "一次性手套",
    "一次性塑料手套",
    "锡箔纸",
    "铝箔纸",
    "捣药罐",
    "定时器",
    "小碗",
    "碗",
    "盆",
    "盘子",
    "蒜臼",
    # 调酒器具（上游饮品分类里成批出现，之前全被当成食材）
    "吧勺",
    "量酒器",
    "调酒杯",
    "雪克杯",
    "雪克瓶",
    "海波杯",
    "高球杯",
    "利口酒杯",
    "冰桶",
    "榨汁机",
)


# --------------------------------------------------------------------------- 头部字段


def parse_difficulty(text: str) -> int | None:
    """``预估烹饪难度：★★★`` → 3；没有则 None。"""
    match = DIFFICULTY_RE.search(text)
    return len(match.group(1)) if match else None


def parse_calories(text: str) -> int | None:
    """``预估卡路里：850 大卡`` → 850；没有则 None（绝不估算）。"""
    match = CALORIE_RE.search(text)
    return int(match.group(1)) if match else None


# --------------------------------------------------------------------------- 配图


def extract_images(text: str, source_path: str) -> tuple[list[str], list[str]]:
    """抽取文中配图。

    本地图转成**数据集内相对路径**（如 ``vegetable_dish/上汤娃娃菜/上汤娃娃菜.png``），
    外链图（GitHub user-images 等）单独返回，保持原样不下载。
    """
    base = posixpath.dirname(source_path)
    local: list[str] = []
    external: list[str] = []

    for match in IMAGE_RE.finditer(text):
        url = match.group("url").strip().strip("<>")
        if not url:
            continue
        if url.startswith(("http://", "https://")):
            if url not in external:
                external.append(url)
            continue
        resolved = posixpath.normpath(posixpath.join(base, url)) if base else posixpath.normpath(url)
        if resolved not in local:
            local.append(resolved)

    return local, external


# --------------------------------------------------------------------------- 用量解析


def _cn_to_number(text: str) -> float:
    if "十" in text:
        left, _, right = text.partition("十")
        tens = CN_NUM.get(left, 1.0) if left else 1.0
        return tens * 10 + sum(CN_NUM[ch] for ch in right)
    return sum(CN_NUM[ch] for ch in text)


def _combine(size: str | None, tail: str | None) -> str | None:
    """把「大/小」这类尺寸修饰与剩余说明合并成一条备注。"""
    parts = [part.strip() for part in (size, tail) if part and part.strip()]
    return "".join(parts) or None


def _parse_amount(rest: str) -> tuple[float | None, float | None, str | None, str | None]:
    """把 ``"400 g"`` / ``"6-15 g"`` / ``"两片"`` / ``"适量"`` 拆成结构化用量。"""
    rest = APPROX_PREFIX_RE.sub("", rest.strip())
    if not rest:
        return None, None, None, None

    match = NUM_AMOUNT_RE.match(rest)
    if match:
        low = float(match.group("min"))
        high = float(match.group("max")) if match.group("max") else None
        return low, high, match.group("unit"), _combine(match.group("size"), match.group("tail"))

    match = CN_AMOUNT_RE.match(rest)
    if match and match.group("unit"):
        return (
            _cn_to_number(match.group("cn")),
            None,
            match.group("unit"),
            _combine(match.group("size"), match.group("tail")),
        )

    # 解析不出数值：原文留档，让下游自己决定怎么处理（例如「适量」「兔肉斤数 * 2 克」）
    return None, None, None, rest


def _split_name_and_amount(core: str) -> tuple[str, str | None]:
    """把 ``"鸡腿 2 个"`` 拆成 ``("鸡腿", "2 个")``；拆不出则整串当名字。"""
    if "=" in core:
        name, _, rhs = core.partition("=")
        return name.strip(), rhs.strip()

    match = re.match(rf"^(?P<name>.*?)\s*(?P<rest>{NUM}.*)$", core)
    if match:
        # 「鲤鱼 约 3 斤」：约 会被吃进名字里，这里剥掉
        name = APPROX_SUFFIX_RE.sub("", match.group("name").strip()).strip()
        return name, match.group("rest").strip()

    # 无阿拉伯数字时，尝试「名称 + 空格 + 中文数词 + 单位」（避免误伤「五花肉」这类名字）
    match = re.match(rf"^(?P<name>.*?)\s+(?P<rest>[一二两三四五六七八九十半]+(?:{_UNITS})?.*)$", core)
    if match:
        return match.group("name").strip(), match.group("rest").strip()

    for token in NON_NUMERIC_AMOUNTS:
        if core.endswith(token) and len(core) > len(token):
            return core[: -len(token)].strip(), token

    return core.strip(), None


def _clean_label(name: str) -> str:
    """剥掉行首标签（``[可选] 分蛋器`` / ``必备：厨房纸``）。"""
    cleaned = OPTIONAL_PREFIX_RE.sub("", name)
    cleaned = REQUIRED_LABEL_RE.sub("", cleaned)
    return cleaned.strip()


def _is_section_heading(name: str) -> bool:
    """章节小标题（``工具`` / ``原料:``）不是食材，也不是厨具。"""
    stripped = re.sub(r"\s+", "", name)
    return stripped.rstrip(":：。").strip() in SECTION_HEADINGS


def _looks_like_prose(name: str, rest: str | None = None) -> bool:
    """判断一行是「整句说明」而不是「食材名」。

    真实 ``unmapped_top`` 里的噪声形态（全部来自 HowToCook 语料）：

    * ``盐的用量为 3 g/人`` —— 「用量说明」被当成了名字；
    * ``一碗容量是 500ml。`` —— 容量说明；
    * ``一般一个人可以食用 60ml-110ml 的米。`` —— 整句；
    * ``肉量 = 份数 * 200g。`` —— **缩放规则**，用 ``份数`` 变量；
    * ``盐量 = 兔肉斤数 * 2 克`` —— 这种**要保留**（``盐量`` 是真实名字），
      区别就在于右侧是 ``份数`` 还是别的变量，见下方 ``PROSE_AMOUNT_VARIABLES``。
    """
    if len(name) > PROSE_MAX_LEN:
        return True
    if len(name) > PROSE_MIN_LEN and PROSE_PUNCT_RE.search(name):
        return True
    if name in SCALAR_ONLY_NAMES:
        return True

    stripped = name.rstrip(":：。.!！?？,，、")
    # 「XX用量为 / XX用量为：」是说明句；「盐量」这类真实名字不含「用量」
    if "用量" in name and stripped.endswith(("为", "是")):
        return True
    # 「盐的用量为」这种把说明词粘在名字上的整串，按后缀模式丢弃
    if NAME_SUFFIX_RE.search(name):
        return True
    # 说明句特征词。**只在名字上判**，不在「名字 = 表达式」的整串上判——
    # 否则 `盐量 = 兔肉斤数 * 2 克` 会因为右侧的「斤数」被误杀（真实数据里有这种写法）。
    if any(marker in name for marker in PROSE_NAME_MARKERS):
        return True
    if name.startswith(PROSE_NAME_PREFIXES):
        return True
    if any(fragment in name for fragment in PROSE_NAME_SUBSTRINGS):
        return True
    # 右侧引用了「份数」这类非食材变量 → 这行是缩放规则，不是一份食材清单。
    # ``_split_name_and_amount`` 已按 ``=`` 拆开，``rest`` 就是右侧表达式本身。
    return any(variable in (rest or "") for variable in PROSE_AMOUNT_VARIABLES)


def _canonical_tool(name: str) -> str | None:
    """命中厨具关键词就收敛到关键词本身（``烤箱 大小不限`` → ``烤箱``）。

    取**最长**命中词：否则 ``手动压汁器`` 会先撞上 ``压汁器`` 收敛成短名，
    丢失「手动」这一区分信息。
    """
    hits = [keyword for keyword in TOOL_KEYWORDS if keyword in name]
    return max(hits, key=len) if hits else None


# --------------------------------------------------------------------------- 单行解析


def parse_ingredient_line(line: str) -> Ingredient:
    """解析一行食材 / 厨具。支持三种真实写法：

    ``- 鳝丝 400 g`` ／ ``- 小龙虾 = 2 斤`` ／ ``- 椰浆 100ml*份数``

    返回 ``name == ""`` 表示这一行**既不是食材也不是厨具**（章节小标题、
    整句说明、虚词）——调用方必须丢弃它，不能塞进 ``ingredients``。
    """
    bullet = BULLET_RE.match(line.strip())
    body = bullet.group("body") if bullet else line.strip()
    body = _clean_label(body)
    if not body:
        return Ingredient(name="")

    # 章节小标题（「工具」「原料:」）必须最先判：否则会被当成厨具混进 recipe.tools
    if _is_section_heading(body):
        return Ingredient(name="")

    notes = [n.strip() for n in PAREN_RE.findall(body) if n.strip()]
    core = re.sub(r"\s{2,}", " ", PAREN_RE.sub(" ", body)).strip()

    per_serving = bool(SERVING_MULTIPLIER_RE.search(core))
    core = SERVING_MULTIPLIER_RE.sub("", core).strip()

    optional = any("可选" in n for n in notes) or "可选" in core

    name, rest = _split_name_and_amount(core)
    if not name:
        return Ingredient(name="")

    # 拆分后名字可能带上「总量」尾巴（「洋葱总量」），再洗一次
    name = re.sub(r"(?:总量|总用量)$", "", name).strip()
    name = _clean_label(name).rstrip(":：。").strip()
    if not name:
        return Ingredient(name="")

    # 收敛前先判一次标题/说明：`不粘锅：油汇聚成滴后…` 这类厨具开头的整句
    # 会被 `_split_name_and_amount` 按 `：` 切开，名字本身已看不出是整句。
    if _is_section_heading(name):
        return Ingredient(name="")

    canonical = _canonical_tool(name)
    # 整句说明：只有**以厨具名开头**时才当厨具（`不粘锅：油汇聚成滴后…`），
    # 否则整行丢弃（既不是食材也不是厨具）。
    prose_without_tool = _looks_like_prose(name, rest) and not (canonical is not None and name.startswith(canonical))
    if prose_without_tool:
        return Ingredient(name="")
    if canonical:
        name = canonical

    low, high, unit, tail = _parse_amount(rest) if rest else (None, None, None, None)
    if tail and tail != rest:
        notes.append(tail)

    return Ingredient(
        name=name,
        kind="tool" if canonical else "ingredient",
        amount_text=rest or None,
        amount_min=low,
        amount_max=high,
        unit=unit,
        note="；".join(notes) if notes else None,
        optional=optional,
        per_serving=per_serving,
    )


def _bullet_body(line: str) -> str:
    """去掉列表符号与行首标签，拿到条目正文。"""
    bullet = BULLET_RE.match(line.strip())
    body = bullet.group("body") if bullet else line.strip()
    return _clean_label(body)


def parse_ingredient_lines(line: str) -> list[Ingredient]:
    """把一行拆成**一个或多个**食材 / 厨具。

    上游大量使用并列写法（``A、B、C`` / ``A/B/C`` / ``A + B``）。这里选择
    **拆分而不是丢弃**：这些名字里有真实食材（``葱、姜、蒜``），丢掉会让菜谱少料
    （检索与购物清单都会失真）；拆开则每味都能各自归一化。

    **只负责拆分**，两件事刻意不做：

    1. 不判断工具 / 食材（由 :func:`parse_ingredient_line` 与整篇解析器负责）；
    2. **不给拆出来的每一项摊派用量**——上游写的是「总量」，
       平摊到每味上就是编造数字。

    返回空 list 表示这一行不是食材（章节小标题、整句说明、虚词）。
    """
    single = parse_ingredient_line(line)
    if not single.name:
        return []

    # 先把 markdown 链接替换成链接文字，再考虑拆分
    body = MD_LINK_RE.sub(lambda m: m.group("text"), _bullet_body(line))
    # 「糖浆（可选）」这类说明文字会被真正拆开，丢掉则拆出的名字不完整
    body = PAREN_RE.sub(" ", body)
    body = ENUMERATION_TAIL_RE.sub("", body).strip().rstrip("、+/ ").strip()
    if not body:
        return []

    parts = [ENUMERATION_TAIL_RE.sub("", part).strip() for part in ENUMERATION_SEP_RE.split(body)]
    parts = [part for part in parts if part]
    if len(parts) <= 1:
        return [single]

    optional = "可选" in line
    items: list[Ingredient] = []
    for part in parts:
        item = parse_ingredient_line(part)
        if not item.name:
            continue
        if optional and not item.optional:
            item = item.model_copy(update={"optional": True})
        items.append(item)
    return items


# --------------------------------------------------------------------------- 整篇解析


def _split_sections(text: str) -> dict[str, str]:
    parts = H2_SPLIT_RE.split(text)
    sections: dict[str, str] = {}
    for index in range(1, len(parts) - 1, 2):
        sections[parts[index].strip()] = parts[index + 1]
    return sections


def _bullet_lines(body: str) -> list[str]:
    return [line for line in body.splitlines() if BULLET_RE.match(line.strip())]


def _prose(body: str) -> str | None:
    """取列表开始之前的说明文字（如「一份正好够 2 个人吃」）。"""
    collected: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if BULLET_RE.match(line):
            break
        collected.append(line)
    return " ".join(collected) or None


def _first_paragraph(text: str) -> str | None:
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("预估烹饪难度", "预估卡路里")):
            continue
        if IMAGE_RE.match(line):
            continue
        return line
    return None


def _steps(body: str) -> list[str]:
    steps: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if STEP_START_RE.match(line):
            steps.append(STEP_START_RE.sub("", line).strip())
        elif steps:
            steps[-1] = f"{steps[-1]} {line}"
    return [step for step in steps if step]


def _normalize(item: Ingredient, dictionary: IngredientDictionary | None) -> Ingredient:
    """给食材补上标准名与分类；词表未收录就保持 ``None``（不编造）。"""
    if dictionary is None or item.kind != "ingredient":
        return item
    entry = dictionary.resolve(item.name)
    if entry is None:
        return item
    return item.model_copy(update={"canonical": entry.name, "category": entry.category})


def parse_recipe_markdown(
    text: str,
    *,
    source_path: str,
    dictionary: IngredientDictionary | None = None,
) -> Recipe:
    """把一篇 HowToCook markdown 解析成 :class:`Recipe`。

    缺少标准章节时抛 ``ValueError``（让导入器记录失败而不是产出残缺数据）。
    """
    title_match = H1_RE.search(text)
    if not title_match:
        raise ValueError("缺少 H1 标题")

    name = title_match.group("title").strip()
    if name.endswith("的做法"):
        name = name[: -len("的做法")]

    sections = _split_sections(text)
    missing = [section for section in REQUIRED_SECTIONS if section not in sections]
    if missing:
        raise ValueError(f"缺少章节：{'、'.join(missing)}")

    # 上游有两种布局：``分类/菜名.md`` 与 ``分类/菜名/菜名.md``，分类一律取顶层目录
    parts = Path(source_path).parts
    category = parts[0] if len(parts) > 1 else ""

    ingredients: dict[str, Ingredient] = {}
    tools: list[str] = []

    # 先吃「计算」（每份精确用量），再用「必备原料和工具」补名字与厨具
    for body, authoritative in ((sections["计算"], True), (sections["必备原料和工具"], False)):
        for line in _bullet_lines(body):
            for item in parse_ingredient_lines(line):
                if item.kind == "tool":
                    if item.name not in tools:
                        tools.append(item.name)
                    continue
                item = _normalize(item, dictionary)
                if authoritative:
                    ingredients[item.name] = item
                else:
                    ingredients.setdefault(item.name, item)

    calories = parse_calories(text)
    images, external_images = extract_images(text, source_path)
    return Recipe(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"howtocook:{source_path}")),
        slug=source_path.removesuffix(".md").replace("/", "-"),
        name=name,
        category=category,
        description=_first_paragraph(text[title_match.end() :]),
        difficulty=parse_difficulty(text),
        calories_kcal=calories,
        calories_source=CALORIES_SOURCE if calories is not None else None,
        time_minutes=None,  # 上游不提供，不猜
        servings_text=_prose(sections["计算"]),
        ingredients=list(ingredients.values()),
        tools=tools,
        steps=_steps(sections["操作"]),
        images=images,
        external_images=external_images,
        extra=(sections.get("附加内容", "").strip() or None),
        source=SOURCE_NAME,
        source_path=source_path,
        source_url=f"{UPSTREAM_URL}/blob/{UPSTREAM_COMMIT}/{source_path}",
        license=SOURCE_LICENSE,
    )


# --------------------------------------------------------------------------- 批量导入


def iter_recipe_files(root: Path) -> list[Path]:
    """按分类目录收集菜谱 markdown（父目录以 ``.`` 开头的跳过）。"""
    return sorted(
        path for path in root.rglob("*.md") if not any(part.startswith(".") for part in path.relative_to(root).parts)
    )


def import_all(
    root: Path,
    *,
    limit: int | None = None,
    dictionary: IngredientDictionary | None = None,
) -> tuple[list[Recipe], dict]:
    """解析整个数据集，返回 (菜谱列表, 报告)。

    ``dictionary`` 缺省时读取 ``data/ingredients/aliases.yaml``（见 T1.3）。
    """
    if dictionary is None:
        dictionary = load_dictionary()
    files = iter_recipe_files(root)
    if limit:
        files = files[:limit]

    recipes: list[Recipe] = []
    failures: list[dict[str, str]] = []
    unresolved: list[dict[str, str]] = []
    missing_images: list[dict[str, str]] = []
    unmapped: Counter[str] = Counter()
    normalized_count = 0
    tool_candidates: Counter[str] = Counter()

    for path in files:
        source_path = path.relative_to(root).as_posix()
        try:
            recipe = parse_recipe_markdown(
                path.read_text(encoding="utf-8"),
                source_path=source_path,
                dictionary=dictionary,
            )
        except ValueError as exc:
            failures.append({"path": source_path, "reason": str(exc)})
            continue
        recipes.append(recipe)
        for item in recipe.ingredients:
            if item.amount_min is None and item.amount_text:
                unresolved.append({"path": source_path, "line": item.name, "amount_text": item.amount_text})
            if item.canonical is None:
                unmapped[item.name] += 1
            else:
                normalized_count += 1
        for image in recipe.images:
            if not (root / image).exists():
                missing_images.append({"path": source_path, "image": image})
        tool_candidates.update(recipe.tools)

    report = {
        "source": SOURCE_NAME,
        "upstream_commit": UPSTREAM_COMMIT,
        "root": root.as_posix(),
        "files_seen": len(files),
        "parsed": len(recipes),
        "failed": len(failures),
        "failures": failures,
        "categories": dict(sorted(Counter(r.category for r in recipes).items())),
        "difficulty_coverage": sum(1 for r in recipes if r.difficulty is not None),
        "calories_coverage": sum(1 for r in recipes if r.calories_kcal is not None),
        "ingredients_total": sum(len(r.ingredients) for r in recipes),
        "ingredients_unique": len({i.name for r in recipes for i in r.ingredients}),
        "ingredients_normalized": normalized_count,
        "ingredients_normalization_rate": round(
            normalized_count / max(1, sum(len(r.ingredients) for r in recipes)) * 100, 1
        ),
        "ingredients_unmapped_unique": len(unmapped),
        "unmapped_top": unmapped.most_common(30),
        "tools_unique": dict(sorted(tool_candidates.items(), key=lambda kv: (-kv[1], kv[0]))),
        "unresolved_amount_count": len(unresolved),
        "unresolved_amount_samples": unresolved[:20],
        "recipes_with_images": sum(1 for r in recipes if r.images),
        "images_total": sum(len(r.images) for r in recipes),
        "external_images_total": sum(len(r.external_images) for r in recipes),
        "missing_image_count": len(missing_images),
        "missing_image_samples": missing_images[:20],
    }
    return recipes, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HowToCook markdown → 结构化菜谱 JSON")
    parser.add_argument("--root", type=Path, default=DEFAULT_SOURCE_ROOT, help="原始 markdown 根目录")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="菜谱 JSON 输出路径")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="导入报告输出路径")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 个文件（调试用）")
    parser.add_argument("--print", dest="show", action="store_true", help="把结果打到 stdout，不写文件")
    args = parser.parse_args(argv)

    if not args.root.exists():
        print(f"源目录不存在：{args.root}", file=sys.stderr)
        return 1

    recipes, report = import_all(args.root, limit=args.limit)
    payload = [recipe.model_dump() for recipe in recipes]

    if args.show:
        print(json.dumps(payload[:3] if args.limit is None else payload, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"解析成功 {report['parsed']}/{report['files_seen']}  （失败 {report['failed']}）")
    print(f"  分类       : {report['categories']}")
    print(f"  难度/热量  : {report['difficulty_coverage']} / {report['calories_coverage']} 有值")
    print(f"  食材       : {report['ingredients_total']} 条，去重 {report['ingredients_unique']} 种")
    print(
        f"  归一化     : {report['ingredients_normalized']} 条命中"
        f"（{report['ingredients_normalization_rate']}%），未收录 {report['ingredients_unmapped_unique']} 种"
    )
    print(f"  厨具识别   : {len(report['tools_unique'])} 种 -> {list(report['tools_unique'])[:12]}")
    print(
        f"  配图       : {report['recipes_with_images']} 道菜有图，共 {report['images_total']} 张"
        f"（缺失 {report['missing_image_count']}，外链 {report['external_images_total']}）"
    )
    print(f"  用量待确认 : {report['unresolved_amount_count']} 条")
    print(f"  输出       : {args.output}")
    print(f"  报告       : {args.report}")
    return 0 if report["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
