
# MealCompass · 饭点罗盘

> 基于混合检索与 LangGraph Agent 的多约束菜谱规划助手
> 根据你的食材、时间、厨具、健康画像，推荐今天吃什么/做什么，并生成步骤、替代食材与购物清单。

[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-14-black)](https://nextjs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-orange)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-336791)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](./LICENSE)

## 📖 项目简介

MealCompass 是一个面向多人群的智能菜谱推荐 Agent。它不只是一个“今天吃什么”的随机转盘，而是结合了**混合检索（向量 + BM25 + 重排）**、**规则引擎（硬约束）** 和 **LangGraph Agent 编排**，为不同健康需求的人群（健身、糖尿病、儿童、高血压等）提供安全、个性化、可解释的菜谱推荐。

**核心差异化**：

- 🩺 **多人群约束**：基于 YAML 规则引擎，硬约束（过敏原、GI、钠等）由规则判定，LLM 不参与，确保安全。
- 🔍 **混合检索**：BGE-M3 稠密向量 + BM25 关键词 + RRF 融合 + bge-reranker 重排，Recall@5 ≥ 85%。
- 🤖 **Agent 编排**：LangGraph 状态机，包含查询理解、澄清追问、工具调用、反思校验，支持多轮对话。
- 🏗️ **可维护架构**：模块化单体 + 分层依赖 + 抽象接口先行，新增人群/工具零核心改动。
- 📊 **可评估可观测**：Langfuse 链路追踪 + RAGAS 量化评估，所有指标可复现。

## ✨ 核心功能

| 模块         | 功能                                             | 状态   |
| ------------ | ------------------------------------------------ | ------ |
| 用户与画像   | 注册/登录、多人群画像、长期记忆                  | MVP    |
| 知识库与 RAG | 200+ 结构化菜谱、混合检索、重排、引用防幻觉      | MVP    |
| Agent 推荐   | 查询理解、澄清追问、3 道推荐、反思校验、工具调用 | MVP    |
| 多人群约束   | 健身、糖尿病、儿童、高血压（可扩展）             | MVP    |
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
│  人群画像    │  │  工具注册表      │  │  切分/索引      │
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
├── docs/                     # PRD、技术栈、架构草案
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

# 启动全栈
docker compose up -d

# 初始化数据库与索引
docker compose exec backend python scripts/seed_recipes.py
docker compose exec backend python scripts/build_index.py
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
| `JWT_SECRET`          | JWT 密钥          | —                                                            |

> 完整变量见 `.env.example`。

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

# 前端类型检查
cd frontend
pnpm typecheck

# Lint
uv run ruff check .
pnpm lint
```

## 📚 文档索引

| 文档                                              | 说明                                   |
| ------------------------------------------------- | -------------------------------------- |
| [`docs/PRD.md`](./docs/PRD.md)                   | 产品需求文档（功能列表、验收标准）     |
| [`docs/TECH_STACK.md`](./docs/TECH_STACK.md)     | 技术栈清单与 AI 编码约束               |
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) | 轻量化架构草案（分层、模块、数据模型） |
| [`docs/API.md`](./docs/API.md)                   | API 接口文档（自动生成）               |

## 🗺️ 路线图

| 阶段 | 周期   | 交付                                         |
| ---- | ------ | -------------------------------------------- |
| M1   | 1-2 周 | 知识库 + 基础 RAG + 前后端骨架               |
| M2   | 2-3 周 | 规则引擎 + 3 人群 + LangGraph Agent + 评估集 |
| M3   | 1-2 周 | 购物清单 / 烹饪模式 / 部署 / Langfuse        |
| M4   | 1 周   | README + 架构图 + Demo 视频 + 简历打磨       |

## 🤝 贡献指南

1. Fork 本仓库
2. 创建功能分支 `git checkout -b feature/xxx`
3. 提交前确保 `pytest` 与 `ruff` 通过
4. 提交 PR，描述变更内容与原因
5. 架构变更需同步更新 `docs/ARCHITECTURE.md` 的迭代日志

## 📄 许可证

[MIT](./LICENSE)

---

**⚠️ 免责声明**：MealCompass 提供的推荐仅供参考，不构成医疗建议。特殊人群（糖尿病、高血压等）请在医生或营养师指导下使用。

**🙏 数据来源**：菜谱数据来自开源数据集（HowToCook、Food.com 等），已标注来源，遵守相应许可证。
