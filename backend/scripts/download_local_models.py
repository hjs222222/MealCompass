"""下载本地兜底模型到仓库内缓存（带进度条，可中断续传）。

本地兜底必须与远程**同模型**：向量空间不一致的话，库里存的远程向量和本地查询向量没法比，
索引用不了。所以这里拉的就是 `BAAI/bge-m3` 与 `BAAI/bge-reranker-v2-m3`。

省流说明：`BAAI/bge-m3` 官方仓库 4.27 GB，其中 2.16 GB 是 `onnx/` 导出（我们用不着），
本脚本跳过它，实际下载约 **4.4 GB**。

用法（在 `backend/` 下）::

    $env:HF_HOME = '<仓库>/.cache/huggingface'
    .venv\\Scripts\\python.exe -m scripts.download_local_models

模型落在 `<仓库>/.cache/`（已 gitignore）；下载中断后重跑会从断点续传。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

os.environ.setdefault("PYTHONUNBUFFERED", "1")
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "0"  # 显式打开进度条

if __package__ in (None, ""):
    sys.path.insert(0, str(REPO_ROOT / "backend"))

from core.config import get_settings  # noqa: E402
from infra.model_cache import SENTENCE_TRANSFORMERS_HOME, prepare_local_model_cache  # noqa: E402

prepare_local_model_cache()

# 只跳过确定用不到的东西：ONNX 导出、README 配图
IGNORE_PATTERNS: dict[str, list[str]] = {
    "BAAI/bge-m3": ["onnx/*", "imgs/*", "*.png", "*.jpg", "*.jpeg"],
    "BAAI/bge-reranker-v2-m3": ["assets/*", "imgs/*", "*.png", "*.jpg", "*.jpeg"],
}


def _human(num_bytes: int) -> str:
    return f"{num_bytes / 1024 / 1024 / 1024:.2f} GB"


def _dir_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def main() -> int:
    from huggingface_hub import snapshot_download

    settings = get_settings()
    targets = [settings.embedding_model, settings.reranker_model]

    print(f"权重缓存 = {SENTENCE_TRANSFORMERS_HOME}")
    print(f"待下载  : {', '.join(targets)}")
    print("（跳过 onnx/ 与示例图片，约省 2 GB；进度条由 huggingface_hub 输出到 stderr）\n")

    failures: list[str] = []
    for repo in targets:
        print(f"===== 开始下载 {repo} =====", flush=True)
        started = time.time()
        try:
            path = snapshot_download(
                repo_id=repo,
                # 必须与加载时用同一个目录，否则「下到 A、加载去 B 找」，白下 4.4 GB
                cache_dir=str(SENTENCE_TRANSFORMERS_HOME),
                ignore_patterns=IGNORE_PATTERNS.get(repo, []),
                max_workers=4,
            )
        except Exception as exc:  # noqa: BLE001 - 网络问题要给出可操作的提示
            failures.append(f"{repo}: {exc}")
            print(f"  失败：{exc}", file=sys.stderr, flush=True)
            print("  提示：国内网络可先设 $env:HF_ENDPOINT='https://hf-mirror.com' 再重跑", file=sys.stderr)
            continue
        print(f"  完成：{_human(_dir_size(Path(path)))}，用时 {time.time() - started:.0f}s", flush=True)
        print(f"  位置：{path}", flush=True)

    if failures:
        print(f"\n有 {len(failures)} 个模型没下成功：", file=sys.stderr)
        for item in failures:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("\n两个模型就绪。接着跑：.venv\\Scripts\\python.exe -m scripts.check_model_clients")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
