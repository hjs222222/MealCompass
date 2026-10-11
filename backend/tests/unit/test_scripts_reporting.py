"""`scripts/` 下几个**只做汇总/归因**的脚本里，纯函数部分的单测。

为什么值得测：这几个脚本是 README 里数字的**复现入口**。它们自己写错时不会报错，
只会安静地打印一个错的数（本项目真实发生过：端到端探针写死读 `results`，
而契约字段是 `candidates`，于是把 5 条候选报成 0 条）。所以"取字段"和"分通道"
这两件小事必须有测试钉住。
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "backend" / "scripts"


def _load(name: str):
    """按文件路径加载脚本模块（`scripts` 不是包，不能直接 import）。"""
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_dsh_script_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


e2e_probe = _load("e2e_probe")
channel_attribution = _load("channel_attribution")
summarize_eval_reports = _load("summarize_eval_reports")
e2e_latency_summary = _load("e2e_latency_summary")


# --------------------------------------------------------------------------- #
# scripts/e2e_probe.py：取候选字段


def test_candidates_of_accepts_canonical_field() -> None:
    """契约字段是 `candidates`（`SearchResponse.candidates`）。"""
    data = {"candidates": [{"name": "罗宋汤"}, {"name": "温泉蛋"}]}
    assert [item["name"] for item in e2e_probe.candidates_of(data)] == ["罗宋汤", "温泉蛋"]


def test_candidates_of_falls_back_to_results() -> None:
    """旧/别名字段 `results` 也要认——兼容比"只认一个字段"更安全。"""
    assert e2e_probe.candidates_of({"results": [{"name": "罗宋汤"}]}) == [{"name": "罗宋汤"}]


def test_candidates_of_prefers_candidates_over_results() -> None:
    data = {"candidates": [{"name": "A"}], "results": [{"name": "B"}]}
    assert e2e_probe.candidates_of(data)[0]["name"] == "A"


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"candidates": None},
        {"candidates": []},
        {"candidates": "不是列表"},
        {"results": 42},
    ],
)
def test_candidates_of_returns_empty_list_instead_of_crashing(data: dict) -> None:
    """**关键回归**：字段缺失/类型不对时必须返回空列表并让调用方打印 0，而不是抛异常。

    注意这**只解决一半问题**：打印出的 0 仍然可能被误读成「接口真的返回 0 条」。
    另一半是探针必须把**原始 JSON 字段名**也打出来，这样人一眼能看出是字段名写错了。
    """
    assert e2e_probe.candidates_of(data) == []


def test_candidates_of_filters_non_dict_items() -> None:
    assert e2e_probe.candidates_of({"candidates": [{"name": "A"}, "垃圾", 1]}) == [{"name": "A"}]


def test_describe_fields_lists_top_level_keys_and_list_sizes() -> None:
    """字段名事故的结构性防线：探针必须把响应的顶层字段名打出来。

    有这一行，「`candidates=0`」和「响应里根本没有 `candidates` 键」才不会被混为一谈。
    """
    data = {"candidates": [{"a": 1}, {"a": 2}], "degraded": False, "empty": []}
    text = e2e_probe.describe_fields(data)
    assert "candidates[2]" in text
    assert "degraded" in text
    assert "empty[0]" in text


def test_e2e_probe_cases_cover_the_five_readme_scenarios() -> None:
    """README 的端到端表有 5 行，探针必须一行不落地覆盖（否则表格就是不可复现的孤证）。"""
    assert len(e2e_probe.CASES) == 5
    queries = [payload["query"] for _, path, payload in e2e_probe.CASES if path == "/recommend"]
    assert queries == ["西红柿炒鸡蛋", "20 分钟能搞定的家常菜", "清淡的汤，不要辣", ""]


# --------------------------------------------------------------------------- #
# scripts/channel_attribution.py：通道分类


@pytest.mark.parametrize(
    ("v_rank", "b_rank", "expected"),
    [
        (1, 1, "双通道"),
        (1, 50, "双通道"),  # 名次多差都算双通道——这正是结构性缺陷的来源
        (1, None, "仅向量"),
        (None, 1, "仅BM25"),
        (None, None, "两路Top50均未召回"),
    ],
)
def test_classify_covers_all_four_channel_states(v_rank: int | None, b_rank: int | None, expected: str) -> None:
    assert channel_attribution._classify(v_rank, b_rank) == expected


def test_recall5_uses_only_first_five_positions() -> None:
    """恰好截断在第 5 位：`e` 算命中、`f`（第 6 位）不算。"""
    top10 = ["a", "b", "c", "d", "e", "f"]
    assert channel_attribution.recall5({"top10": top10, "relevant": ["f"]}) == 0.0
    assert channel_attribution.recall5({"top10": top10, "relevant": ["e"]}) == 1.0
    assert channel_attribution.recall5({"top10": top10, "relevant": ["e", "f"]}) == 0.5


def test_recall5_handles_empty_relevant_set() -> None:
    """金标准为空时必须返回 0.0 而不是 ZeroDivisionError。"""
    assert channel_attribution.recall5({"top10": ["a"], "relevant": []}) == 0.0


# --------------------------------------------------------------------------- #
# scripts/summarize_eval_reports.py：摘要口径


def test_round_metrics_only_keeps_the_four_declared_keys() -> None:
    """摘要只能含约定的四个指标，防止把临时字段带进入库证据。"""
    out = summarize_eval_reports._round_metrics(
        {"recall@5": 0.63750001, "recall@10": 0.72, "mrr@10": 0.74, "ndcg@5": 0.6308785, "多余字段": 1.0}
    )
    assert set(out) == {"recall@5", "recall@10", "mrr@10", "ndcg@5"}
    assert out["recall@5"] == 0.6375
    assert out["ndcg@5"] == 0.630879


def test_resolve_treats_default_style_paths_as_repo_relative() -> None:
    """`docs/evidence/x.json` 这类默认值按仓库根解析（与 scripts/eval.py 同口径）。"""
    resolved = summarize_eval_reports._resolve("docs/evidence/x.json")
    assert resolved == REPO_ROOT / "docs" / "evidence" / "x.json"


# --------------------------------------------------------------------------- #
# scripts/e2e_latency_summary.py：多轮聚合


def test_latency_regex_matches_probe_output_line() -> None:
    match = e2e_latency_summary.LATENCY_RE.search("    HTTP 200  耗时 10085 ms")
    assert match is not None
    assert match["status"] == "200"
    assert match["ms"] == "10085"


def test_case_regex_parses_probe_header() -> None:
    match = e2e_latency_summary.CASE_RE.match('=== POST /recommend {"query": "西红柿炒鸡蛋"}')
    assert match is not None
    assert match["method"] == "POST"
    assert match["path"] == "/recommend"
    assert match["payload"] == '{"query": "西红柿炒鸡蛋"}'


def test_case_regex_rejects_non_header_lines() -> None:
    assert e2e_latency_summary.CASE_RE.match("    HTTP 200  耗时 10085 ms") is None
    assert e2e_latency_summary.CASE_RE.match("=== 汇总（7 条回落查询） ==") is None


def test_summarize_computes_min_max_and_spread() -> None:
    records = [
        {"case": "POST /recommend {}", "status": 200, "ms": 12007},
        {"case": "POST /recommend {}", "status": 200, "ms": 9168},
        {"case": "POST /recommend {}", "status": 200, "ms": 11470},
    ]
    rows = e2e_latency_summary.summarize(records)
    assert len(rows) == 1
    row = rows[0]
    assert row["runs"] == 3
    assert (row["min_ms"], row["max_ms"]) == (9168, 12007)
    assert row["spread_ms"] == 2839
    assert row["values"] == [9168, 11470, 12007]


def test_summarize_keeps_error_status_codes() -> None:
    """422 那一条也是 README 的一行，别把它当异常丢掉。"""
    rows = e2e_latency_summary.summarize([{"case": "POST /recommend 空 query", "status": 422, "ms": 6}])
    assert rows[0]["statuses"] == [422]


def test_summarize_sorts_by_slowest_first() -> None:
    records = [
        {"case": "快", "status": 200, "ms": 6},
        {"case": "慢", "status": 200, "ms": 12007},
    ]
    assert [row["case"] for row in e2e_latency_summary.summarize(records)] == ["慢", "快"]


def test_parse_runs_excludes_known_buggy_rounds() -> None:
    """**关键回归**：带 `OLD_PROBE` 的轮次必须被排除。

    那一轮探针写死读 `results`，把 5 条候选报成 0 条，延迟也是旧脚本测的。
    让它进入聚合 = README 的区间不可信。
    """
    used, records = e2e_latency_summary.parse_runs(REPO_ROOT / "docs" / "evidence")
    assert used, "应当至少聚合到一轮干净输出"
    assert all("OLD_PROBE" not in name for name in used)
    assert all("OLD_PROBE" not in record["run"] for record in records)


def test_parse_runs_extracts_one_latency_per_case() -> None:
    """每条用例只能取到**紧跟在表头之后**的那一个延迟（响应体里也可能出现同类文本）。"""
    used, records = e2e_latency_summary.parse_runs(REPO_ROOT / "docs" / "evidence")
    assert len(used) >= 3
    # 每份输出 5 条用例 → 总数必须正好是 5 × 轮数，不能多也不能少
    assert len(records) == 5 * len(used)
