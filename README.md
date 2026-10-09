
# MealCompass · 饭点罗盘

> 基于混合检索与 LangGraph Agent 的多约束菜谱规划助手
> 根据你的食材、时间、厨具、口味偏好，推荐今天吃什么/做什么，并生成步骤、替代食材与购物清单。
>
> **文档版本 v1.1（2026-10-06）**：已统一跨文档冲突，全局口径见下方「全局约定（唯一口径）」。

[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-14-black)](https://nextjs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-orange)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-336791)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](./LICENSE)

## 📖 项目简介

MealCompass 是一个面向**所有做饭的普通人**的智能菜谱推荐 Agent。它不只是一个“今天吃什么”的随机转盘，而是结合了**混合检索（向量 + BM25 + 重排）**、**规则引擎（硬约束）** 和 **LangGraph Agent 编排**，根据你的食材、时间、厨具和忌口，提供安全、个性化、可解释的菜谱推荐。

**核心差异化**：

- 🧩 **硬约束规则引擎**：过敏原/忌口、可用时间、可用厨具由 YAML 规则判定，LLM 不参与，确保安全且可解释。
- 🔍 **混合检索**：BGE-M3 稠密向量 + BM25 关键词 + RRF 融合 + bge-reranker 重排，Recall@5 ≥ 85%。
- 🤖 **Agent 编排**：LangGraph 状态机，包含查询理解、澄清追问、工具调用、反思校验，支持多轮对话。
- 🏗️ **可维护架构**：模块化单体 + 分层依赖 + 抽象接口先行，新增约束/工具零核心改动。
- 📊 **可评估可观测**：Langfuse 链路追踪 + RAGAS 量化评估，所有指标可复现。

## ✨ 核心功能

| 模块         | 功能                                             | 状态   |
| ------------ | ------------------------------------------------ | ------ |
| 用户与画像   | 邮箱 + JWT 登录、通用画像（口味/忌口/厨具/技能，MVP）、长期记忆（P1） | MVP/P1 |
| 知识库与 RAG | 200+ 结构化菜谱、混合检索、重排、引用防幻觉      | MVP    |
| Agent 推荐   | 查询理解、澄清追问、3 道推荐、反思校验、工具调用 | MVP    |
| 约束引擎     | 忌口/过敏、时间、厨具硬过滤 + 口味软偏好（YAML 可配） | MVP   |
| 菜谱与烹饪   | 菜谱详情、份量缩放、食材替代、烹饪指导模式       | MVP/P1 |
| 购物与规划   | 购物清单合并、一周菜单、食材库存                 | MVP/P1 |
| 反馈与迭代   | 点赞/踩/收藏/做过、历史记录、评估看板            | MVP/P1 |
| 系统与运维   | 分层架构、配置外置、Langfuse、Docker 部署        | MVP    |

> 详细功能列表与验收标准（DoD）见 [`docs/PRD.md`](./docs/PRD.md)。

## 🧱 技术栈

| 层级                | 技术                                              | 版本锚定                |
| ------------------- | ------------------------------------------------- | ----------------------- |
| **AI 编排**   | LangGraph + LangChain                             | ≥ 0.2 / 0.3.x          |
| **后端**      | FastAPI + Pydantic v2                             | 0.115+                  |
| **数据库**    | PostgreSQL + pgvector                             | PG 16+ / pgvector 0.7+  |
| **Embedding** | BGE-M3                                            | BAAI/bge-m3             |
| **重排**      | bge-reranker-v2-m3                                | BAAI/bge-reranker-v2-m3 |
| **LLM**       | DeepSeek / OpenAI 兼容 API                        | —                      |
| **前端**      | Next.js 14 + TypeScript + Tailwind v4 + shadcn/ui | 14+                     |
| **状态**      | TanStack Query + Zustand                          | v5                      |
| **可观测**    | Langfuse + Sentry                                 | latest                  |
| **评估**      | RAGAS                                             | latest                  |
| **容器化**    | Docker + Docker Compose                           | —                      |

> 完整技术栈清单与 AI 编码约束见 [`docs/TECH_STACK.md`](./docs/TECH_STACK.md)。

## 🧭 全局约定（唯一口径）

> 跨文档冲突已在本节统一。任何文档、代码或 AI 生成内容与此处不一致时，**以本节为准**。

| 议题 | 统一结论 |
| ---- | -------- |
| **登录** | 邮箱 + 密码 + JWT（注册 / 登录 / 登出 / 刷新）；**不做第三方 OAuth** |
| **目标用户** | **面向所有普通人，不做医学人群细分**（GI / 钠 / 蛋白质等医学营养数据不可得）。约束只来自用户自己的忌口、时间、厨具与口味 |
| **画像归属** | `backend/domain/profiles/`（`domain` 是唯一无 IO 层） |
| **接口定义** | 所有 Protocol 集中在 `domain/ports.py`（`RecipeRepository` / `Retriever` / `LLMClient`），实现在 `infra/`、`rag/` |
| **前端目录** | 不使用 `src/` 前缀：`app/`、`components/ui/`、`lib/` 直接放在 `frontend/` 下 |
| **渲染策略** | 推荐 / 对话 / 购物清单 = CSR（client + TanStack Query）；落地页 / 菜谱详情 / legal = Server Component（SSR） |
| **样式** | Natural Organic（`docs/UI_STYLE.md`）；Tailwind v4 CSS-first，token 定义在 `app/globals.css` 的 `@theme`，不生成 `tailwind.config.js`；shadcn/ui 主题必须映射到该调色板 |
| **数据源** | 菜谱来自 HowToCook（Unlicense / 公有领域，可自由分发与商用）。372 道菜谱 + 354 张成品配图已收录进 `data/raw/howtocook/` 并随仓库提交；上游完整 clone（623 MB）不入库 |
| **模型调用** | **远程优先、本地兜底**：Embedding / Rerank 默认走 SiliconFlow、DeepSeek 等 OpenAI 兼容接口，失败或离线时回落 Ollama / sentence-transformers 本地推理；实现在 `infra/`，接口在 `domain/ports.py`，trace 里标注实际走的是哪条路 |
| **会话存储** | `PostgresSaver` 是会话状态唯一事实源；Redis 只做缓存与限流 |
| **规则** | YAML 文件（`data/rules/`），不入库，可版本控制 |
| **可观测** | Langfuse Cloud 免费版（日本区，Python SDK v4.17+）+ Sentry；未配置 key 时自动降级为本地结构化日志；**读取 trace 走 `/api/public/v2/observations`**（旧 `/api/public/traces` 对 2026-09-16 后新建的组织返回 410） |
| **评估** | `scripts/eval.py` 手动跑；稳定后再入 CI，MVP 阶段不进必跑流水线 |
| **语音** | Web Speech API（客户端） |
| **工期** | 总计 4-6 周（单人全职）：M1 1-1.5 周 / M2 1.5-2 周 / M3 1-1.5 周 / M4 0.5-1 周 |

**文档地图**：`README.md`（本文件）· `docs/PRD.md` · `docs/TECH_STACK.md` · `docs/ARCHITECTURE.md` · `docs/CONVENTIONS.md` · `docs/UI_STYLE.md` · `docs/API.md`（自动生成）· `TODO.md`

## 🏗️ 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                      前端 (Next.js)                      │
│  /recommend  /chat  /recipe  /cook  /shopping  /profile │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP / JSON
┌──────────────────────────▼──────────────────────────────┐
│                    API 层 (FastAPI)                      │
│  api/v1: auth / profile / recommend / recipe / shopping │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                   Service 层 (业务编排)                   │
│  AuthService / ProfileService / RecommendService / ...  │
└───────┬──────────────────┬──────────────────┬───────────┘
        │                  │                  │
┌───────▼──────┐  ┌────────▼────────┐  ┌─────▼──────────┐
│   Domain     │  │     Agents      │  │      RAG       │
│  规则引擎    │  │  LangGraph 编排  │  │  混合检索+重排  │
│  用户画像    │  │  工具注册表      │  │  切分/索引      │
└───────┬──────┘  └────────┬────────┘  └─────┬──────────┘
        │                  │                  │
┌───────▼──────────────────▼──────────────────▼───────────┐
│              Infra 层 (DB / LLM / Redis / 观测)          │
│  PostgreSQL + pgvector  |  LLM Client  |  Langfuse      │
└─────────────────────────────────────────────────────────┘
```

**分层依赖规则**：`api → services → domain / agents / rag → infra`，单向不可逆，`domain` 不依赖任何层。

## 📁 目录结构

```
mealcompass/
├── backend/
│   ├── api/                  # 路由层
│   ├── services/             # 业务编排
│   ├── domain/               # 领域层（模型、规则、画像）
│   ├── agents/               # LangGraph 节点与工具
│   ├── rag/                  # 检索、重排、切分、索引
│   ├── infra/                # DB、LLM、Redis、观测
│   ├── core/                 # 配置、日志、安全
│   ├── scripts/              # 种子数据、建索引、评估
│   ├── tests/
│   ├── main.py
│   └── Dockerfile
├── frontend/
│   ├── app/                  # Next.js App Router
│   ├── components/           # UI 组件
│   ├── lib/                  # API 客户端、stores、hooks
│   └── Dockerfile
├── data/
│   ├── recipes/              # 原始菜谱 JSON
│   ├── rules/                # 规则 YAML（可热更新）
│   └── eval/                 # 评估集
├── docs/                     # 文档（PRD / 技术栈 / 架构 / 规范 / UI 风格）
├── docker-compose.yml
└── README.md
```

> 详细架构说明见 [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)。

## 🚀 快速开始

### 前置要求

- Docker & Docker Compose
- Python 3.11+（本地开发）
- Node.js 20+（本地开发）
- 一个 OpenAI 兼容的 API Key（推荐 DeepSeek）

### 一键启动（Docker Compose）

```bash
# 克隆仓库
git clone https://github.com/yourname/mealcompass.git
cd mealcompass

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY 等

# 启动依赖（postgres + redis）
# backend / frontend 在 app profile 下，等各自 Dockerfile 就绪后：docker compose --profile app up -d
docker compose up -d

# 建表（Alembic，schema 事实源是 backend/infra/tables.py）
cd backend && .venv/Scripts/python.exe -m alembic upgrade head && cd ..

# 解析原始数据并灌库（幂等，可重复跑）
cd backend
.venv/Scripts/python.exe -m scripts.import_howtocook   # HowToCook markdown -> JSON
.venv/Scripts/python.exe -m scripts.seed_recipes        # JSON + 食材词典 -> PostgreSQL
.venv/Scripts/python.exe -m scripts.build_index         # 建双层向量索引（T1.6，幂等可重跑）
cd ..
```

访问：

- 前端：http://localhost:3000
- 后端 API 文档：http://localhost:8000/docs
- Langfuse：http://localhost:3001

### 本地开发

**后端**：

```bash
cd backend
uv sync
uv run uvicorn main:app --reload
```

**前端**：

```bash
cd frontend
pnpm install
pnpm dev
```

## 🔧 环境变量

| 变量                    | 说明              | 示例                                                          |
| ----------------------- | ----------------- | ------------------------------------------------------------- |
| `DATABASE_URL`        | PostgreSQL 连接串 | `postgresql+asyncpg://user:pass@localhost:5432/mealcompass` |
| `REDIS_URL`           | Redis 连接串      | `redis://localhost:6379/0`                                  |
| `LLM_API_KEY`         | LLM API Key       | `sk-...`                                                    |
| `LLM_BASE_URL`        | LLM 兼容接口      | `https://api.deepseek.com`                                  |
| `LLM_MODEL`           | 模型名            | `deepseek-chat`                                             |
| `EMBEDDING_MODEL`     | Embedding 模型    | `BAAI/bge-m3`                                               |
| `RERANKER_MODEL`      | 重排模型          | `BAAI/bge-reranker-v2-m3`                                   |
| `LANGFUSE_PUBLIC_KEY` | Langfuse 公钥     | —                                                            |
| `LANGFUSE_SECRET_KEY` | Langfuse 私钥     | —                                                            |
| `SENTRY_DSN` | 异常上报（可选） | — |
| `JWT_SECRET`          | JWT 密钥          | —                                                            |
| `NEXT_PUBLIC_API_BASE_URL` | 前端访问的后端基址（唯一暴露给浏览器的变量） | `http://localhost:8000`（默认值，可留空） |

> 完整变量见 `.env.example`（前端为 `frontend/.env.example`）。

## 📊 评估指标

| 维度     | 指标                    | 目标值            |
| -------- | ----------------------- | ----------------- |
| 检索     | Recall@5 / nDCG@5       | ≥ 85% / ≥ 0.8   |
| 生成     | 引用准确率 / 约束满足率 | ≥ 95% / 100%     |
| Agent    | 任务成功率 / 工具准确率 | ≥ 90% / ≥ 95%   |
| 性能     | P95 延迟 / Token 成本   | ≤ 3s / ≤ ¥0.05 |
| 工程质量 | 单元测试覆盖率          | ≥ 70%            |

运行评估：

```bash
docker compose exec backend python scripts/eval.py
```

结果将输出到终端并同步至 Langfuse。

## 🧪 测试

```bash
# 后端单元测试
cd backend
uv run pytest --cov=.

# 前端：类型检查 + Lint + 构建
cd frontend
pnpm typecheck && pnpm lint && pnpm build

# 后端 Lint
uv run ruff check . && uv run ruff format --check .
```

## 📚 文档索引

| 文档                                              | 说明                                   |
| ------------------------------------------------- | -------------------------------------- |
| [`docs/PRD.md`](./docs/PRD.md) | 产品需求文档（功能列表、验收标准） |
| [`docs/TECH_STACK.md`](./docs/TECH_STACK.md) | 技术栈清单与 AI 编码约束 |
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) | 架构草案（分层、模块、数据模型） |
| [`docs/CONVENTIONS.md`](./docs/CONVENTIONS.md) | 开发规范（分层 / 测试 / CI / Git） |
| [`docs/UI_STYLE.md`](./docs/UI_STYLE.md) | 前端 UI 风格（Natural Organic） |
| [`docs/API.md`](./docs/API.md) | API 文档（由 FastAPI OpenAPI 自动生成） |
| [`TODO.md`](./TODO.md) | 待办与排期（决策项 / 里程碑 / 验收标准） |
| [`docs/failed-features.md`](./docs/failed-features.md) | 未完成功能与环境受限项登记（不假装可用） |

## 🗺️ 路线图

| 阶段 | 周期   | 交付                                         |
| ---- | ------ | -------------------------------------------- |
| M1   | 1-1.5 周 | 知识库 + 基础 RAG + 前后端骨架 |
| M2   | 1.5-2 周 | 规则引擎（通用约束）+ LangGraph Agent + 评估集 |
| M3   | 1-1.5 周 | 购物清单 / 烹饪模式 / 部署 / Langfuse |
| M4   | 0.5-1 周 | README + 架构图 + Demo 视频 + 简历打磨 |

> **总工期 4-6 周（单人全职）**：与 `TECH_STACK.md` 的选型前提一致。时间不足时优先砍 M3 的 P1 项，**评估与部署不可省**。

## 🤝 贡献指南

1. Fork 本仓库
2. 创建功能分支 `git checkout -b feature/xxx`
3. 提交前确保 `pytest` 与 `ruff` 通过
4. 提交 PR，描述变更内容与原因
5. 架构变更需同步更新 `docs/ARCHITECTURE.md` 的迭代日志

## 📄 许可证

[MIT](./LICENSE)

---

**⚠️ 免责声明**：MealCompass 提供的推荐仅供参考，不构成医疗或营养建议。有特殊饮食需求者请咨询专业人士。

**🙏 数据来源**：菜谱数据来自开源数据集（HowToCook、Food.com 等），已标注来源，遵守相应许可证。
