"""本地模型缓存目录：固定在仓库内，避免沙箱写不了别处、也避免重复下载。

**两个环境变量都必须设**：

- `HF_HOME` —— HuggingFace hub 的元数据与小文件
- `SENTENCE_TRANSFORMERS_HOME` —— sentence-transformers 存放真正的权重

只设一个就会出现「下到 A、加载时去 B 找」→ 白白重下几 GB。
已由用户显式设置的值不会被覆盖。
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_ROOT = REPO_ROOT / ".cache"

HF_HOME = CACHE_ROOT / "huggingface"
SENTENCE_TRANSFORMERS_HOME = CACHE_ROOT / "sentence-transformers"


def prepare_local_model_cache() -> Path:
    """把缓存变量指向 `<仓库>/.cache`（已 gitignore），返回缓存根目录。"""
    os.environ.setdefault("HF_HOME", str(HF_HOME))
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(SENTENCE_TRANSFORMERS_HOME))
    return CACHE_ROOT
