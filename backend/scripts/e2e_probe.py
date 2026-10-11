"""端到端真机复测：把 README 里公示的 5 个场景逐个重跑一遍。

用法（需先起 API）：::

    cd backend
    .venv\\Scripts\\python.exe -m uvicorn main:app --port 8000
    # 另一个终端
    $env:TEMP='<仓库>\\.tmp'
    .venv\\Scripts\\python.exe ..\\.tmp\\e2e_probe.py --out docs/evidence/e2e_probe.txt

**为什么这个脚本留在仓库里（而不是随手删掉）**：
README 的「端到端接口实测」表里有 5 行数字（含延迟），面试官现场让复现时，
必须有一条命令能重新跑出这张表，否则那些数字就是不可验证的孤证。
脚本把原始输出同时写进 `docs/evidence/e2e_probe.txt`（入库），
正文只做排版，不改任何数字。

注意：`/recipes/search` 的候选字段是 **`results`**（本脚本按哪个字段是否存在自动适配，
不做硬编码——第一次探测就是因为写死了字段名而误报 `results=0`）。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"

CASES: list[tuple[str, str, dict[str, object]]] = [
    ("POST", "/recommend", {"query": "西红柿炒鸡蛋"}),
    ("POST", "/recommend", {"query": "20 分钟能搞定的家常菜"}),
    ("POST", "/recommend", {"query": "清淡的汤，不要辣"}),
    ("POST", "/recipes/search", {"query": "有鸡蛋和番茄", "top_k": 5}),
    ("POST", "/recommend", {"query": ""}),
]


def candidates_of(data: dict[str, object]) -> list[dict[str, object]]:
    """兼容 `candidates` / `results` 两种字段名，避免又踩一次写死字段的坑。

    第一次探测就是因为写死读 `results`（而契约字段是 `candidates`），
    把 5 条候选报成 0 条、差点被当成"检索真的没召回"写进 README。
    """
    for key in ("candidates", "results"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def describe_fields(data: dict[str, object]) -> str:
    """把响应的**顶层字段名与条目数**打出来。

    这是"字段名写错"这类事故的**结构性防线**：只要探针把原始字段名打出来，
    「`candidates=0`」和「响应里根本没有 `candidates` 这个键」在人眼里就是两件事，
    不会再被误读成"检索没召回"。
    """
    parts = []
    for key, value in data.items():
        if isinstance(value, list):
            parts.append(f"{key}[{len(value)}]")
        else:
            parts.append(str(key))
    return " ".join(parts)


def run_case(base: str, method: str, path: str, payload: dict[str, object], timeout: float) -> list[str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(base + path, data=body, method=method, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw, status = resp.read().decode("utf-8"), resp.status
    except urllib.error.HTTPError as exc:
        raw, status = exc.read().decode("utf-8"), exc.code
    elapsed_ms = (time.perf_counter() - t0) * 1000

    lines = [
        f"=== {method} {path} {json.dumps(payload, ensure_ascii=False)}",
        f"    HTTP {status}  耗时 {elapsed_ms:.0f} ms",
    ]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        lines.append(f"    非 JSON: {raw[:300]}")
        return lines

    # 顶层字段名先行：字段名写错时这一行会立刻暴露，不会被读成"接口返回空"
    lines.append(f"    响应字段: {describe_fields(data)}")

    if path == "/recommend":
        recs = data.get("recommendations") or []
        lines.append(
            f"    recommendations={len(recs)} degraded={data.get('degraded')} "
            f"degradations={data.get('degradations')} node_path={data.get('node_path')}"
        )
        lines.append(f"    no_solution_reason={data.get('no_solution_reason')!r}")
        for r in recs:
            lines.append(
                f"      - {r.get('name')} (id={str(r.get('recipe_id'))[:8]}…) reason={str(r.get('reason'))[:70]!r}"
            )
    elif path == "/recipes/search":
        found = candidates_of(data)
        lines.append(f"    candidates={len(found)} degraded={data.get('degraded')}")
        lines.append(f"    top5={[r.get('name') for r in found[:5]]}")
    else:
        lines.append(f"    body={json.dumps(data, ensure_ascii=False)[:400]}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="复跑 README 公示的端到端场景")
    parser.add_argument("--base", default=BASE, help="API 基址")
    parser.add_argument("--timeout", type=float, default=180.0, help="单请求超时（秒）")
    parser.add_argument("--out", default="docs/evidence/e2e_probe.txt", help="原始输出留底路径")
    args = parser.parse_args()

    out: list[str] = []
    for method, path, payload in CASES:
        out.extend(run_case(args.base, method, path, payload, args.timeout))
        out.append("")

    text = "\n".join(out)
    print(text)
    target = pathlib.Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print(f"[留底] {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
