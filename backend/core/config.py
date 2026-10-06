"""应用配置：pydantic-settings 读 `.env`，dev / prod 分离。

约定：
- 这里是**唯一**的环境变量入口。业务代码不得直接读 ``os.environ``
  （唯一例外是 ``infra/observability.py``，它必须在 import langfuse 之前把凭证写进环境变量）。
- 密钥只从 `.env` 或真实环境变量来，绝不写进代码、文档或 trace。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/core/config.py -> core -> backend -> 仓库根
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    """全量配置。字段名小写，自动匹配大写下划线环境变量。"""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- 应用 ----
    app_env: str = Field(default="dev", description="dev / staging / prod")
    log_level: str = "INFO"

    # ---- LLM（OpenAI 兼容）----
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"

    # ---- 检索模型 ----
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"

    # ---- Langfuse 可观测 ----
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str = "https://cloud.langfuse.com"
    langfuse_tracing_environment: str = "dev"

    # ---- 数据库 ----
    database_url: str = "postgresql+asyncpg://mealcompass:mealcompass@localhost:5432/mealcompass"
    redis_url: str = "redis://localhost:6379/0"

    # ---- 安全 ----
    jwt_secret: str = "change-me-in-dev-only"

    @property
    def tracing_enabled(self) -> bool:
        """没配 key 就整体降级为 no-op，本地开发不被可观测性阻塞。"""
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """进程内单例配置。"""
    return Settings()
