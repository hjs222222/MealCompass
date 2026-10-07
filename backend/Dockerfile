# MealCompass 后端镜像
#
# 注意：`main.py`（FastAPI 入口）要到 T1.14 才落地，在那之前这个镜像
# 主要用来跑 alembic 迁移和 scripts/ 下的脚本。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 先装依赖，利用 layer 缓存（依赖清单与 pyproject.toml 保持一致）
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        "fastapi>=0.115" \
        "uvicorn[standard]>=0.30" \
        "pydantic>=2.7" \
        "pydantic-settings>=2.3" \
        "python-dotenv>=1.0" \
        "pyyaml>=6.0" \
        "sqlalchemy[asyncio]>=2.0" \
        "asyncpg>=0.29" \
        "alembic>=1.13" \
        "pgvector>=0.3" \
        "langfuse>=3.0"

COPY . .

EXPOSE 8000

# 等 T1.14 落地后换成真正的 uvicorn 启动命令
CMD ["python", "-c", "print('MealCompass backend image ready; main.py lands in T1.14')"]
