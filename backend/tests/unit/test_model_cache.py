"""本地模型缓存必须固定在仓库内，且不覆盖用户已显式设置的值。

背景：`.cache/` 下同时存在 `huggingface/`（HF hub 元数据）与 `sentence-transformers/`（真正的权重）。
两个路径必须一起指定，否则会出现「下到 A、加载时去 B 找」→ 重复下载 4.4 GB。
"""

from __future__ import annotations

import os
from pathlib import Path

from infra.model_cache import prepare_local_model_cache

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_prepare_redirects_both_caches_into_repo(monkeypatch) -> None:
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("SENTENCE_TRANSFORMERS_HOME", raising=False)

    root = prepare_local_model_cache()

    assert root == REPO_ROOT / ".cache"
    assert Path(os.environ["HF_HOME"]) == root / "huggingface"
    assert Path(os.environ["SENTENCE_TRANSFORMERS_HOME"]) == root / "sentence-transformers"


def test_prepare_does_not_override_existing_values(monkeypatch) -> None:
    monkeypatch.setenv("HF_HOME", str(REPO_ROOT / "custom-hf"))
    monkeypatch.setenv("SENTENCE_TRANSFORMERS_HOME", str(REPO_ROOT / "custom-st"))

    prepare_local_model_cache()

    assert os.environ["HF_HOME"] == str(REPO_ROOT / "custom-hf")
    assert os.environ["SENTENCE_TRANSFORMERS_HOME"] == str(REPO_ROOT / "custom-st")
