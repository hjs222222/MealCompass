"""`scripts/check_docs_consistency.py` 的单测。

这个脚本是**纪律的执行器**：它把「README 里的数字必须能追到 `docs/evidence/`」
从"靠人自觉"变成"跑一条命令就知道"。所以它自己必须被测住——
一个永远返回 0 的检查器比没有检查器更糟，因为它提供虚假的安全感。

因此这里的测试重点是**它真的会失败**：每类问题都要有一条"注入错误 → 必须报错"的用例。
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPTS = REPO_ROOT / "backend" / "scripts"


def _load(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_dsh_script_{name}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


checker = _load("check_docs_consistency")

README = (REPO_ROOT / "README.md").read_text("utf-8")
EVIDENCE = REPO_ROOT / "docs" / "evidence"


@pytest.fixture
def summary() -> dict:
    return json.loads((EVIDENCE / "eval_reports_summary.json").read_text("utf-8"))


# --------------------------------------------------------------------------- #
# parse_cell：表里两种写法都要认


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("63.75%", (63.75, 63.75)),
        ("**63.75%**", (63.75, 63.75)),
        ("**77.50–78.33%**", (77.50, 78.33)),  # en dash（README 实际用的）
        ("77.50-78.33%", (77.50, 78.33)),  # 普通连字符
        (" 59.29 – 59.54% ", (59.29, 59.54)),
    ],
)
def test_parse_cell_accepts_single_value_and_range(cell: str, expected: tuple[float, float]) -> None:
    assert checker.parse_cell(cell) == expected


@pytest.mark.parametrize("cell", ["", "不是数字", "abc%", "top10"])
def test_parse_cell_returns_none_for_garbage(cell: str) -> None:
    assert checker.parse_cell(cell) is None


# --------------------------------------------------------------------------- #
# check_metrics：数字必须与报告一致


def test_check_metrics_passes_on_real_readme(summary: dict) -> None:
    """真实 README 当前必须通过（否则要么 README 错了，要么证据错了）。"""
    assert checker.check_metrics(README, summary) == []


def test_check_metrics_catches_tampered_number(summary: dict) -> None:
    """**关键回归**：把 R@5 改成 99.99% 必须被抓住。"""
    tampered = README.replace("| 纯向量 | **63.75%** |", "| 纯向量 | **99.99%** |")
    assert tampered != README, "篡改没生效，这条测试就是假的"

    problems = checker.check_metrics(tampered, summary)
    assert problems
    assert any("99.99" in item and "63.75" in item for item in problems)


def test_check_metrics_catches_number_outside_range(summary: dict) -> None:
    """区间必须**覆盖**报告值；把区间挪到 60–70% 就漏掉了 77.50%。"""
    tampered = README.replace("**77.50–78.33%**", "**60.00–70.00%**")
    assert tampered != README
    problems = checker.check_metrics(tampered, summary)
    assert problems
    assert any("R@10" in item and "77.5" in item for item in problems), problems


def test_check_metrics_alone_accepts_over_wide_range_hence_variance_check_exists() -> None:
    """**这两条检查是分工的**：把区间写成 70–80% 仍然"覆盖"77.50%，`check_metrics` 会放行。

    所以光有"覆盖"是不够的——区间必须是**实测极差**，这个约束由
    `check_variance_ranges` 负责。这条测试把这个分工钉住，防止以后有人把
    `check_variance_ranges` 当冗余删掉，从而让"随便框一个大范围"混过 CI。
    """
    summary = json.loads((EVIDENCE / "eval_reports_summary.json").read_text("utf-8"))
    over_wide = README.replace("**77.50–78.33%**", "**70.00–80.00%**")
    assert over_wide != README

    assert checker.check_metrics(over_wide, summary) == []  # 覆盖住了，指标检查放行
    problems = checker.check_variance_ranges(over_wide, EVIDENCE)  # 但极差检查抓得住
    assert any("78.33" in item for item in problems), problems


def test_check_metrics_reports_missing_row(summary: dict) -> None:
    tampered = "\n".join(line for line in README.splitlines() if not line.startswith("| 纯向量 "))
    problems = checker.check_metrics(tampered, summary)
    assert any("纯向量" in item for item in problems)


def test_check_metrics_reports_missing_mode_in_summary(summary: dict) -> None:
    shrunk = {"reports": [r for r in summary["reports"] if r["mode"] != "hybrid"]}
    problems = checker.check_metrics(README, shrunk)
    assert any("hybrid" in item for item in problems)


def test_check_metrics_catches_unparsable_cell(summary: dict) -> None:
    tampered = README.replace("| 纯向量 | **63.75%** |", "| 纯向量 | 待测 |")
    problems = checker.check_metrics(tampered, summary)
    assert any("无法解析" in item for item in problems)


# --------------------------------------------------------------------------- #
# check_variance_ranges：区间必须来自跨轮极差，不能手写


def test_check_variance_ranges_passes_on_real_readme() -> None:
    assert checker.check_variance_ranges(README, EVIDENCE) == []


def test_check_variance_ranges_catches_handwritten_range() -> None:
    """手写一个"差不多"的区间必须被抓住——这是 README 最容易掺水的地方。"""
    tampered = README.replace("**77.50–78.33%**", "**77.50–79.00%**")
    assert tampered != README
    problems = checker.check_variance_ranges(tampered, EVIDENCE)
    assert any("77.5" in item and "78.33" in item for item in problems), problems


def test_check_variance_ranges_reports_missing_variance_file() -> None:
    problems = checker.check_variance_ranges(README, REPO_ROOT / "docs" / "no_such_evidence_dir")
    assert any("缺跨轮极差文件" in item for item in problems)


def test_check_variance_ranges_allows_single_value_when_spread_is_zero() -> None:
    """R@5 跨轮极差为 0 → README 给单值是对的，不该逼着写成区间。"""
    row = next(line for line in README.splitlines() if line.startswith("| 混合 + 重排 "))
    assert "64.17%" in row  # 单值而非区间
    assert checker.check_variance_ranges(README, EVIDENCE) == []


# --------------------------------------------------------------------------- #
# check_evidence_refs / check_evidence_dir


def test_check_evidence_refs_passes_on_real_readme() -> None:
    assert checker.check_evidence_refs(README, EVIDENCE) == []


def test_check_evidence_refs_catches_dangling_link() -> None:
    tampered = README.replace("docs/evidence/rerank_variance.txt", "docs/evidence/never_written.txt")
    assert tampered != README
    problems = checker.check_evidence_refs(tampered, EVIDENCE)
    assert any("never_written" in item for item in problems)


def test_check_evidence_refs_requires_at_least_one_reference() -> None:
    problems = checker.check_evidence_refs("没有任何引用", EVIDENCE)
    assert any("没有任何指向" in item for item in problems)


def test_check_evidence_dir_passes_on_real_dir() -> None:
    assert checker.check_evidence_dir(EVIDENCE) == []


def test_check_evidence_dir_rejects_empty_dir() -> None:
    problems = checker.check_evidence_dir(REPO_ROOT / "docs" / "no_such_evidence_dir")
    assert any("不存在" in item for item in problems)


# --------------------------------------------------------------------------- #
# main：端到端跑真实仓库必须 exit 0


def test_main_returns_zero_on_real_repo(capsys: pytest.CaptureFixture[str]) -> None:
    assert checker.main([]) == 0
    out = capsys.readouterr().out
    assert "[OK]" in out
    assert "指标格 12 个全部覆盖" in out


def test_main_returns_nonzero_for_bad_readme(monkeypatch: pytest.MonkeyPatch) -> None:
    """篡改后的 README 交给 main，必须 exit 非 0（CI 才拦得住）。"""
    tampered = REPO_ROOT / ".tmp" / "README_for_test.md"
    tampered.parent.mkdir(parents=True, exist_ok=True)
    tampered.write_text(README.replace("| 纯向量 | **63.75%** |", "| 纯向量 | **11.11%** |"), encoding="utf-8")
    try:
        assert checker.main(["--readme", ".tmp/README_for_test.md"]) == 1
    finally:
        tampered.unlink(missing_ok=True)


def test_main_returns_nonzero_when_summary_missing(capsys: pytest.CaptureFixture[str]) -> None:
    assert checker.main(["--evidence", "docs"]) == 1
    assert "找不到评估摘要" in capsys.readouterr().out
