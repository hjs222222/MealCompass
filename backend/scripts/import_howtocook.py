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


def _looks_like_prose(name: str) -> bool:
    """「必备原料和工具」里混有整句说明（如「北方大米，米和水放在电饭煲的容器内…」）。"""
    if len(name) > PROSE_MAX_LEN:
        return True
    return len(name) > PROSE_MIN_LEN and bool(PROSE_PUNCT_RE.search(name))


def _canonical_tool(name: str) -> str | None:
    """命中厨具关键词就收敛到关键词本身（``烤箱 大小不限`` → ``烤箱``）。"""
    for keyword in TOOL_KEYWORDS:
        if keyword in name:
            return keyword
    return None


# --------------------------------------------------------------------------- 单行解析


def parse_ingredient_line(line: str) -> Ingredient:
    """解析一行食材 / 厨具。支持三种真实写法：

    ``- 鳝丝 400 g`` ／ ``- 小龙虾 = 2 斤`` ／ ``- 椰浆 100ml*份数``
    """
    bullet = BULLET_RE.match(line.strip())
    body = bullet.group("body") if bullet else line.strip()
    if not body:
        return Ingredient(name="")

    notes = [n.strip() for n in PAREN_RE.findall(body) if n.strip()]
    core = re.sub(r"\s{2,}", " ", PAREN_RE.sub(" ", body)).strip()

    per_serving = bool(SERVING_MULTIPLIER_RE.search(core))
    core = SERVING_MULTIPLIER_RE.sub("", core).strip()

    optional = any("可选" in n for n in notes) or "可选" in core

    name, rest = _split_name_and_amount(core)
    if not name:
        return Ingredient(name="")

    canonical = _canonical_tool(name)
    if _looks_like_prose(name):
        # 整句说明：只有以厨具开头时才当厨具，否则整行丢弃（既不是食材也不是厨具）
        if not (canonical and name.startswith(canonical)):
            return Ingredient(name="")
        name = canonical
    elif canonical:
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
            item = parse_ingredient_line(line)
            if not item.name:
                continue
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
        slug=f"{category}-{name}",
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
