"""Tracing 冒烟测试：验证 `.env` → Langfuse Cloud → API 可查回，并做 best-practices 自审。

用法（在 ``backend/`` 目录下执行）::

    .venv\\Scripts\\python.exe scripts\\trace_smoke.py

设计说明：

- LLM 输出用**确定性桩数据**，因为 LLM key 还没填；但 ``model``、
  ``usage_details``、结构化 input/output 全部按真实调用的形态填写，
  这样 Langfuse 的模型 / Token / 成本视图立刻可用，等真 LLM 接入时只需换掉桩。
- 结束前必须 ``flush()``，否则缓冲的 trace 不会发送（官方 Common Mistakes 第一条）。
- 读回用 **Observations API v2**（``/api/public/v2/observations``）。
  旧的 ``/api/public/traces`` 对 2026-09-16 之后创建的组织返回 410 Gone，
  官方迁移文档：https://langfuse.com/docs/api-and-data-platform/features/observations-api
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

# 允许直接 `python scripts/trace_smoke.py` 运行
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import get_settings  # noqa: E402
from infra.observability import (  # noqa: E402
    ObservationType,
    SpanName,
    attributes,
    current_trace_id,
    degraded_reason,
    flush,
    get_langfuse_client,
    traced,
)

USER_QUERY = "健身人群，冰箱里有鸡胸肉和西兰花，30 分钟内能做什么？"

STUB_PARSED = {
    "intent": "recommend",
    "ingredients": ["鸡胸肉", "西兰花"],
    "cohort": "fitness",
    "max_minutes": 30,
    "tools_available": ["炒锅"],
}

STUB_CANDIDATES = ["howtocook/meat_dish/黑椒鸡胸肉", "howtocook/vegetable_dish/蒜蓉西兰花"]
STUB_RECOMMENDATIONS = [
    {"recipe_id": STUB_CANDIDATES[0], "name": "黑椒鸡胸肉", "protein_g": 42, "minutes": 20},
    {"recipe_id": STUB_CANDIDATES[1], "name": "蒜蓉西兰花", "protein_g": 9, "minutes": 10},
]

# v2 观察接口按字段组返回，不请求就没有
OBS_FIELDS = "core,basic,time,io,metadata,model,usage,metrics,trace_context"


def build_trace() -> str | None:
    """构造一条贴近真实推荐流程的 trace。"""
    settings = get_settings()

    with traced(
        SpanName.RECOMMEND_REQUEST,
        input={"query": USER_QUERY},
        metadata={"cohort": "fitness", "source": "trace_smoke"},
    ) as root:
        with attributes(
            user_id="smoke-user",
            session_id="smoke-session-001",
            tags=["smoke", "fitness"],
            metadata={"cohort": "fitness", "stub": True},
            environment=settings.langfuse_tracing_environment,
            trace_name=SpanName.RECOMMEND_REQUEST,
        ):
            with traced(SpanName.PARSE_INTENT, input=USER_QUERY) as span:
                span.update(output=STUB_PARSED, metadata={"model": settings.llm_model})

            with traced(
                SpanName.RETRIEVE_RECIPES,
                as_type=ObservationType.RETRIEVER,
                input={"query": "高蛋白 快手 鸡胸肉 西兰花", "filters": {"max_minutes": 30}},
            ) as span:
                span.update(
                    output={"recipe_ids": STUB_CANDIDATES},
                    metadata={"retriever": "hybrid(vector+bm25)+rrf", "top_k": 10, "num_candidates": 2},
                )

            with traced(
                SpanName.FILTER_HARD_CONSTRAINTS,
                input={"rules": ["protein_min", "allergen", "time_limit"]},
            ) as span:
                span.update(output={"passed": 2, "filtered_out": 0}, metadata={"cohort": "fitness"})

            with traced(
                SpanName.GENERATE_RECOMMENDATIONS,
                as_type=ObservationType.GENERATION,
                model=settings.llm_model,
                input=[{"role": "user", "content": USER_QUERY}],
            ) as generation:
                generation.update(
                    output=STUB_RECOMMENDATIONS,
                    usage_details={"input_tokens": 412, "output_tokens": 268},
                    metadata={"stub": True, "temperature": 0.1, "recipe_ids": STUB_CANDIDATES},
                )

            with traced(SpanName.REFLECT_VALIDATE, input={"checks": ["allergen", "time", "tool", "calories"]}) as span:
                span.update(output={"passed": True, "retries": 0})

        trace_id = current_trace_id()
        root.update(output={"recommendations": STUB_RECOMMENDATIONS, "passed_reflection": True})
        return trace_id


def fetch_observations(trace_id: str) -> list[dict[str, Any]]:
    """用 Observations API v2 读回该 trace 的所有观察。"""
    client = get_langfuse_client()
    if client is None:
        return []
    response = client.api.observations.get_many(trace_id=trace_id, fields=OBS_FIELDS, limit=100)
    rows = getattr(response, "data", None) or []
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(row.model_dump() if hasattr(row, "model_dump") else dict(row))
    return result


def verify(trace_id: str, timeout_seconds: int = 90) -> list[dict[str, Any]]:
    """轮询等待 ingestion 完成（Langfuse 是异步写入）。"""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            rows = fetch_observations(trace_id)
        except Exception as exc:  # noqa: BLE001
            print(f"  查询失败：{type(exc).__name__}: {str(exc)[:200]}")
            return []
        if rows:
            return rows
        time.sleep(5)
    return []


def pick(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) is not None:
            return row[key]
    return None


def audit(rows: list[dict[str, Any]]) -> list[str]:
    """按官方 baseline 自审：模型、Token、命名、嵌套、类型、IO。"""
    findings: list[str] = []
    names = [pick(r, "name") for r in rows]
    types = {pick(r, "type") for r in rows}

    if "@" in names:
        findings.append("有未命名的观察（名为 @）")
    if any(n and any(ch.isdigit() for ch in n.split("-")[-1]) for n in names):
        findings.append("观察名疑似含动态值（低基数规则）")

    generation = next((r for r in rows if pick(r, "type") == "GENERATION"), None)
    if generation is None:
        findings.append("缺少 generation（LLM 调用必须记为 generation）")
    else:
        if not pick(generation, "model"):
            findings.append("generation 没有 model，成本无法自动计算")
        usage = pick(generation, "usage_details")
        if not usage:
            findings.append("generation 没有 usage_details，Token 视图为空")
        if pick(generation, "total_cost") is None:
            findings.append("generation 没有 cost（模型不在价格表里时为正常）")

    root = next((r for r in rows if pick(r, "is_root_observation")), None)
    if root is None:
        findings.append("没有标记为 root 的观察")
    elif not pick(root, "input") or not pick(root, "output"):
        findings.append("root 观察缺 input/output，trace 列表会显示空白")

    if not pick(rows[0], "session_id"):
        findings.append("缺 session_id，Sessions 视图无法按对话串起来")
    if not pick(rows[0], "user_id"):
        findings.append("缺 user_id，无法按用户归因成本")
    if "RETRIEVER" not in types:
        findings.append("检索步骤没有用 retriever 类型")
    return findings


def main() -> int:
    settings = get_settings()
    print("=" * 78)
    print("MealCompass · Langfuse tracing 冒烟测试")
    print(f"  host        : {settings.langfuse_base_url}")
    print(f"  environment : {settings.langfuse_tracing_environment}")
    print(f"  model       : {settings.llm_model}")
    print("  read API    : /api/public/v2/observations")
    print("=" * 78)

    if not settings.tracing_enabled:
        print(f"未启用 tracing（{degraded_reason()}）。")
        print("请在仓库根目录的 .env 中填写 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY 后重试。")
        return 0

    trace_id = build_trace()
    flush()
    print(f"已发送 trace：{trace_id}")

    rows = verify(trace_id) if trace_id else []
    if not rows:
        print("!! 未能通过 Observations API v2 读回该 trace，请检查网络 / 密钥 / 数据区域。")
        return 1

    print("-" * 78)
    print(f"API 侧核验通过 ✓  读回 {len(rows)} 条观察")
    print(f"  trace name : {pick(rows[0], 'trace_name')}")
    print(f"  user / sess: {pick(rows[0], 'user_id')} / {pick(rows[0], 'session_id')}")
    print(f"  tags       : {pick(rows[0], 'tags')}")
    print(f"  environment: {pick(rows[0], 'environment')}")
    print("-" * 78)
    print(f"{'type':<12}{'name':<26}{'model':<16}{'in/out tok':<14}latency")
    for row in sorted(rows, key=lambda r: str(pick(r, "start_time"))):
        usage = pick(row, "usage_details") or {}
        tokens = ""
        if usage:
            tokens = f"{usage.get('input', usage.get('input_tokens', '-'))}/{usage.get('output', usage.get('output_tokens', '-'))}"
        print(
            f"{str(pick(row, 'type')):<12}{str(pick(row, 'name')):<26}"
            f"{str(pick(row, 'model') or '-'):<16}{tokens:<14}{pick(row, 'latency')}"
        )

    print("-" * 78)
    print("root 观察的 input / output：")
    root = next((r for r in rows if pick(r, "is_root_observation")), rows[0])
    print(f"  input : {str(pick(root, 'input'))[:110]}")
    print(f"  output: {str(pick(root, 'output'))[:110]}")

    print("-" * 78)
    findings = audit(rows)
    if findings:
        print("自审发现待改进项：")
        for item in findings:
            print(f"  ! {item}")
    else:
        print("自审通过：模型 / Token / 命名 / 嵌套 / 类型 / IO / session / user 全部达标 ✓")

    print("-" * 78)
    print(f"trace id: {trace_id}")
    print(f"在 UI 查看：{settings.langfuse_base_url} → Tracing → 过滤 trace name = {SpanName.RECOMMEND_REQUEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
