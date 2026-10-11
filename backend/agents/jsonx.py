"""Agent 层共用的 LLM 输出解析工具。

远程 LLM（SiliconFlow / DeepSeek）即使被要求 ``response_format="json_object"``，实际返回也**经常**是
````` ```json ... ``` ```` 围栏包裹，或者 JSON 前后带一句自然语言说明。因此本模块不直接 ``json.loads``
硬解析，而是先做「稳健提取」：取第一个 ``{``/``[`` 到最后一个 ``}``/``]`` 的最长包络，再解析。

纯函数、无 IO、无 side effect，便于单测覆盖各种脏输出。
"""

from __future__ import annotations

import json
import re
from typing import Any

_OPEN_TO_CLOSE = {"{": "}", "[": "]"}
# 匹配 "前一句说明 ```json {..} ``` 后一句说明" 里的围栏内容
_FENCED = re.compile(r"```[A-Za-z0-9_+-]*[ \t]*\n?(?P<body>.*?)[ \t]*```", re.DOTALL)


def extract_json_payload(text: str, *, expect: str | None = None) -> Any | None:
    """从可能含围栏 / 说明文字的 LLM 输出里提取 JSON 值。

    Args:
        text: 原始模型输出。
        expect: ``"object"`` 只接受 ``{...}``，``"array"`` 只接受 ``[...]``；``None`` 接受两者。

    Returns:
        解析出的 Python 对象；无法解析时返回 ``None``（调用方据此走降级，绝不抛异常）。
    """
    if not isinstance(text, str) or not text.strip():
        return None

    candidates: list[str] = []
    # 1) 优先看围栏内部（最干净的形态）
    for match in _FENCED.finditer(text):
        candidates.append(match.group("body"))
    # 2) 再看整段文本（无围栏 / 围栏没闭合）
    candidates.append(text)

    for candidate in candidates:
        parsed = _parse_best_effort(candidate, expect=expect)
        if parsed is not None:
            return parsed
    return None


def extract_json_object(text: str) -> dict[str, Any] | None:
    """提取 JSON 对象；结构不是 dict 时返回 ``None``。"""
    parsed = extract_json_payload(text, expect="object")
    return parsed if isinstance(parsed, dict) else None


def extract_json_array(text: str) -> list[Any] | None:
    """提取 JSON 数组；结构不是 list 时返回 ``None``。"""
    parsed = extract_json_payload(text, expect="array")
    return parsed if isinstance(parsed, list) else None


def _parse_best_effort(text: str, *, expect: str | None) -> Any | None:
    """在 ``text`` 里找 JSON 包络并解析；失败返回 ``None``。"""
    for opener in _ordered_openers(text, expect=expect):
        start = text.find(opener)
        while start != -1:
            end = text.rfind(_OPEN_TO_CLOSE[opener])
            if end > start:
                try:
                    return json.loads(text[start : end + 1])
                except (ValueError, TypeError):
                    pass
            # 同一个开头字符出现多次时继续找下一个
            start = text.find(opener, start + 1)
    return None


def _ordered_openers(text: str, *, expect: str | None) -> tuple[str, ...]:
    """按 ``expect`` 决定优先尝试哪种包络；``None`` 时按最先出现者优先。"""
    if expect == "object":
        return ("{",)
    if expect == "array":
        return ("[",)
    first_object = text.find("{")
    first_array = text.find("[")
    if first_object == -1:
        return ("[", "{")
    if first_array == -1:
        return ("{", "[")
    return ("{", "[") if first_object <= first_array else ("[", "{")


def coerce_str_list(value: Any) -> list[str]:
    """把 LLM 给的「列表 / 单个字符串 / 空」统一成 ``list[str]``，逐项去空白。"""
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        return []
    return [item.strip() for item in items if isinstance(item, str) and item.strip()]


def coerce_positive_int(value: Any, *, minimum: int, maximum: int) -> int | None:
    """把 LLM 给的耗时解析成范围内的正整数；不合法返回 ``None``（宁可留空也不猜数字）。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = int(value)
    elif isinstance(value, str):
        match = re.search(r"\d+", value)
        if match is None:
            return None
        number = int(match.group())
    else:
        return None
    if number < minimum or number > maximum:
        return None
    return number
