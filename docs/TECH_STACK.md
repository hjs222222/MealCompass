
# MealCompass 技术栈清单（v1.1）

> **用途**：喂给 AI Coding 工具（Cursor / Copilot / Claude 等），作为项目开发的技术边界约束。
> **选型原则**：成熟优先、社区资料丰富、AI 训练数据覆盖度高、本科生可在 4-6 周内独立完成。
> **阅读说明**：✅ 表示 AI 训练数据覆盖充分；⚠️ 表示资料中等，需注意版本兼容。
> **变更 v1.1（2026-10-06）**：统一跨文档冲突（分层目录、接口位置、前端目录、可观测降级），全局口径见 [`../README.md`](../README.md) 的「全局约定（唯一口径）」。

## 一、技术栈总览

| 层级                 | 技术选型                   | 版本锚定                | 关键理由                                        |
| -------------------- | -------------------------- | ----------------------- | ----------------------------------------------- |
| **AI 编排**    | LangGraph                  | ≥ 0.2                  | 状态机可控，LangChain 生产版                    |
| **RAG 工具链** | LangChain                  | 0.3.x                   | RAG 生态最成熟，文档加载/分块/检索全套          |
| **后端框架**   | FastAPI                    | 0.115+                  | 异步高性能，自动 Swagger，AI 应用首选           |
| **数据校验**   | Pydantic                   | v2                      | FastAPI 原生集成，类型安全                      |
| **向量数据库** | PostgreSQL + pgvector      | PG 16+ / pgvector 0.7+  | 一份数据库搞定关系+向量+全文检索，零额外运维    |
| **全文检索**   | PostgreSQL tsvector        | 同 PG                   | 与 pgvector 同库，无需额外部署 Elasticsearch    |
| **Embedding**  | BGE-M3                     | BAAI/bge-m3             | 中文效果好，支持稠密+稀疏，1024 维              |
| **重排**       | bge-reranker-v2-m3         | BAAI/bge-reranker-v2-m3 | 轻量，多语言，推理快                            |
| **LLM**        | DeepSeek / OpenAI 兼容 API | —                      | 通过 OpenAI 兼容接口，可无缝切换                |
| **关键词检索** | rank-bm25 + jieba          | —                      | 轻量，无需独立服务，适合中小规模                |
| **前端框架**   | Next.js                    | 14+                     | React 全栈框架，生态最大，AI 训练数据覆盖极充分 |
| **前端语言**   | TypeScript                 | 5.x                     | 类型安全，AI 生成代码质量更高                   |
| **CSS**        | Tailwind CSS               | v4                      | 实用类优先，AI 生成效率高                       |
| **UI 组件**    | shadcn/ui                  | latest                  | 代码直接复制到项目，零抽象层，AI 可直接读写     |
| **服务端状态** | TanStack Query             | v5                      | 缓存/重取/错误处理标准化                        |
| **客户端状态** | Zustand                    | v5                      | 轻量，学习成本低                                |
| **可观测**             | Langfuse Cloud + Sentry    | langfuse-python ≥ 4.17.0 | LLM 链路追踪 + 评估一体化；读取走 Observations API v2          |
| **评估框架**   | RAGAS                      | latest                  | 专为 RAG 设计，四大指标开箱即用                 |
| **容器化**     | Docker + Docker Compose    | —                      | 一键起全栈                                      |
| **缓存**       | Redis                      | 7.x                     | 会话、限流、热点缓存                            |

## 二、分层详解

### 2.1 AI 层（Agent + RAG）

**框架选型：LangGraph + LangChain**

选择理由：LangGraph 是 LangChain 的“生产版”，提供显式状态管理和 checkpointing，适合复杂可控的工作流。LangChain 负责文档加载、分块、检索等 RAG 链路，两者配合使用。LlamaIndex 虽然 RAG 能力强，但本项目重点在 Agent 编排（多约束、工具调用、反思校验），LangGraph 更匹配。

**LangGraph 结构约束**：

```
State: 消息历史 / 用户画像 / 约束条件 / 候选菜谱 / 选中菜谱 / 当前步骤
Nodes: parse → clarify → search → filter → rank → reflect → output
Edges: 条件路由（信息不足→澄清，检索为空→放宽约束，校验失败→重试）
```

**RAG 管线约束**：

```
菜谱卡片层（粗召回） → 向量检索(pgvector) + BM25(rank-bm25)
                    → RRF 融合 → bge-reranker 重排 → Top 10
菜谱步骤层（精取详情） → 按 recipe_id 取步骤块
生成层              → 硬约束规则引擎校验 + LLM 生成 + 引用强制
```

**关键约束**：

- LLM 不参与硬约束判断（忌口/过敏原、时间、厨具等），由规则引擎判定
- 每条推荐必须附 recipe_id，可追溯
- 反思校验失败重试 ≤ 2 次，仍失败则降级返回安全候选

**注意**：LangGraph 生态在快速迭代，AI 生成的代码可能混用新旧 API。锁定版本 ≥ 0.2 并参考官方文档。

### 2.2 后端层

**FastAPI + Pydantic v2**

选择理由：FastAPI 在性能、可维护性和可扩展性上优于 Flask 和 Django，原生异步支持，自动生成 OpenAPI 文档，非常适合 AI 应用的后端 API 层。Pydantic v2 用于请求/响应校验，与 FastAPI 原生集成。

**分层约束**：

```
backend/
  api/            # 路由 + DTO，仅参数校验
  services/       # 业务编排，事务边界
  domain/         # 实体、值对象、规则引擎、用户画像（纯逻辑，唯一无 IO 层）
    ports.py      # 所有 Protocol 接口（RecipeRepository / Retriever / LLMClient）
    rules/        # 规则引擎
    profiles/     # 用户画像（口味、忌口、厨具、技能）
  agents/         # LangGraph 节点、工具、状态
  rag/            # 检索、重排、切分、索引（实现 domain.ports.Retriever）
  infra/          # DB、LLM 客户端、Redis（实现 domain.ports.*）
  core/           # 配置、依赖注入、日志、异常
```

**关键约束**：

- 抽象接口先行：`RecipeRepository`、`Retriever`、`LLMClient` 统一在 `domain/ports.py` 用 Protocol 定义，实现在 `infra/`、`rag/`
- 换 LLM 供应商 ≤ 1 天工作量（通过 OpenAI 兼容接口）
- 配置外置：`pydantic-settings` 读 `.env`，dev/prod 分离

**依赖注入**：FastAPI 的 `Depends` 即可，不需要引入 `dependency-injector`。

### 2.3 数据层

**PostgreSQL + pgvector（唯一数据库）**

选择理由：项目规模为 200-500 道菜谱、单机部署，pgvector 在这个量级完全够用（Recall@10 = 0.987，P99 延迟 28ms）。关键优势是一份数据库同时搞定关系数据 + 向量检索 + 全文检索，**减少一个需要运维的系统**。

**向量数据库对比参考**：

| 数据库   | Recall@10 | P99 延迟 | 适用场景                  |
| -------- | --------- | -------- | ------------------------- |
| Qdrant   | 0.991     | 12ms     | 大规模、过滤密集          |
| pgvector | 0.987     | 28ms     | 已有 PostgreSQL、中小规模 |
| Chroma   | 0.976     | 67ms     | 本地原型                  |

数据来源

**关键约束**：

- 硬约束下推至 SQL `WHERE` 条件，不在检索后过滤
- 菜谱卡片和步骤块分两张表，分别建索引
- 食材同义词表用 PG 表存储，支持 `LIKE` 和全文检索

**备选方案**：如果后期需要更强的过滤能力或更大规模，迁移到 Qdrant，但接口层不变（依赖 `Retriever` Protocol）。

### 2.4 模型层

**Embedding：BGE-M3** ✅

中文效果好，支持多语言，输出 1024 维稠密向量 + 稀疏向量。可通过 Ollama 或 HuggingFace 加载，也可通过 API 调用。

**重排：bge-reranker-v2-m3** ✅

轻量级重排序模型，多语言，推理快，内存需求 ≥ 8GB。

**LLM：DeepSeek / OpenAI 兼容 API** ✅

通过 OpenAI 兼容接口调用，便于切换不同供应商。推荐 DeepSeek 作为主力，成本低，中文好。

**关键约束**：

- **远程优先、本地兜底**：Embedding（BGE-M3）与重排（bge-reranker-v2-m3）默认走 SiliconFlow / DeepSeek 等 OpenAI 兼容接口；远程失败或离线时回落 Ollama / sentence-transformers 本地推理
- 两种实现都由 `domain/ports.py` 的 `EmbeddingClient` / `RerankClient` Protocol 约束，调用方不感知（`infra/` 出 Remote / Local / Fallback 三个实现）
- trace 的 metadata 标注实际走了远程还是本地、是否触发降级，降级率可在 Langfuse 看板观察

**已实测可用的远程模型（SiliconFlow，2026-10-07 用真实 key 验证）**

| 用途 | 模型 | 实测结果 |
| --- | --- | --- |
| Embedding | `BAAI/bge-m3` | 输出 **1024 维**，与 `vector(1024)` 对齐；同 key 另有 `Pro/BAAI/bge-m3` |
| 重排 | `BAAI/bge-reranker-v2-m3` | query「番茄炒蛋」→「西红柿炒鸡蛋」0.9994、「番茄鸡蛋汤」0.9897、「红烧肉」0.0060，排序正确 |
| 对话 | `deepseek-ai/DeepSeek-V3` | 可正常返回；平台另有 V3.2 / V4-Flash / V4-Pro 与 GLM、Kimi、Qwen 等（chat 共 64 个） |
| 基址 | `https://api.siliconflow.cn/v1` | OpenAI 兼容；embedding / rerank 走各自端点，不是 `/chat/completions` |

已落地：`infra/embedding_client.py` 与 `infra/rerank_client.py` —— `Remote*`（远程）/ `Local*`（sentence-transformers，可选）/ `Fallback*`（降级组合）；调用方只依赖 `domain/ports.py` 的 Protocol。远程走不通时自动切本地，并把 provider 与降级次数暴露给 trace。

> 不选 `Qwen/Qwen3-Embedding-*` 的原因：维度与既有的 `vector(1024)` 不匹配，换维度要重建索引与迁移，收益不抵成本。
- LLM 通过 API 调用，保留 `LLMClient` 抽象层，便于切换
- 单次推荐 Token 成本 ≤ ¥0.05

### 2.5 前端层

**Next.js 14 + TypeScript + Tailwind + shadcn/ui + TanStack Query** ✅

选择理由：Next.js 是 React 生态最成熟的全栈框架，AI 训练数据覆盖最充分，生成代码质量最高。React 在 LLM 训练数据集中占主导地位，AI 生成 UI 代码时几乎首选 React。

**关键约束**：

- 使用 App Router（非 Pages Router）
- 服务端状态用 TanStack Query，客户端状态用 Zustand
- UI 组件从 shadcn/ui 复制到项目，不引入组件库依赖
- 响应式设计，移动端可用
- 目录不带 `src/` 前缀：`app/`、`components/ui/`、`lib/`
- Tailwind v4 用 CSS-first：token 定义在 `app/globals.css` 的 `@theme`，不生成 `tailwind.config.js`

**备选方案**：如果团队更熟悉 Vue，可替换为 Vue 3 + Nuxt 3 + Element Plus，学习曲线更平缓，但 AI 训练数据覆盖度低于 React。

### 2.6 评估与可观测层

**Langfuse + RAGAS** ✅

Langfuse 用于 LLM 链路追踪（每一步的输入/输出/延迟/Token），RAGAS 用于自动化评估（Faithfulness / Answer Relevancy / Context Precision / Context Recall）。两者配合使用，Langfuse 做可观测，RAGAS 做量化评估。未配置 Langfuse key 时自动降级为本地结构化日志，不阻塞本地开发。 本项目实现：`infra/observability.py` 统一封装（SDK v4.17.0），key 缺失时降级为 no-op；读取 trace 一律用 Observations API v2。

**评估指标约束**：

| 维度  | 指标                    | 目标值            |
| ----- | ----------------------- | ----------------- |
| 检索  | Recall@5 / nDCG@5       | ≥ 85% / ≥ 0.8   |
| 生成  | 引用准确率 / 约束满足率 | ≥ 95% / 100%     |
| Agent | 任务成功率 / 工具准确率 | ≥ 90% / ≥ 95%   |
| 性能  | P95 延迟 / Token 成本   | ≤ 3s / ≤ ¥0.05 |

## 三、开发工具链

| 工具                     | 用途               | 备注                                |
| ------------------------ | ------------------ | ----------------------------------- |
| **uv**             | Python 包管理      | 比 pip 快 10-100x，AI 生成友好      |
| **Ruff**           | Linter + Formatter | 替代 flake8 + black + isort         |
| **pytest**         | 测试               | 单元测试覆盖率 ≥ 70%               |
| **Docker Compose** | 本地全栈启动       | 一条命令起 PG + Redis + 后端 + 前端 |
| **Langfuse**       | LLM 可观测         | 自托管或 Cloud                      |
| **GitHub Actions** | CI                 | Lint + Test + Build                 |

## 四、AI 编码约束清单

以下约束可直接写入 Cursor Rules 或 `.cursorrules`：

```
# 技术栈约束
- Python: 3.11+, FastAPI 0.115+, Pydantic v2
- Agent: LangGraph >= 0.2, LangChain 0.3.x
- 数据库: PostgreSQL 16 + pgvector 0.7
- Embedding: BGE-M3 (BAAI/bge-m3), 1024维
- 重排: bge-reranker-v2-m3
- 前端: Next.js 14 App Router + TypeScript + Tailwind v4 + shadcn/ui（目录不带 src/）
- 状态: TanStack Query (服务端) + Zustand (客户端)
- LLM: OpenAI 兼容接口，通过 LLMClient 抽象层调用

# 架构约束
- 分层: api → services → domain / agents / rag → infra（画像在 domain/profiles/，接口在 domain/ports.py）
- 抽象接口先行: RecipeRepository / Retriever / LLMClient 用 Protocol 定义
- 硬约束用规则引擎判定，LLM 不参与
- 检索: 向量 + BM25 混合，RRF 融合，bge-reranker 重排
- 生成: 必须引用 recipe_id，禁止编造知识库外内容

# 代码规范
- 类型注解必须完整
- 配置用 pydantic-settings 读 .env
- 单元测试覆盖率 >= 70%
- 不引入未在技术栈清单中的依赖
```

## 五、资料索引

| 技术         | 官方文档                               | AI 训练数据覆盖 |
| ------------ | -------------------------------------- | --------------- |
| LangGraph    | langchain-ai.github.io/langgraph       | ✅ 充分         |
| LangChain    | python.langchain.com                   | ✅ 充分         |
| FastAPI      | fastapi.tiangolo.com                   | ✅ 充分         |
| Pydantic v2  | docs.pydantic.dev                      | ✅ 充分         |
| pgvector     | github.com/pgvector/pgvector           | ✅ 充分         |
| Next.js      | nextjs.org/docs                        | ✅ 极充分       |
| Tailwind CSS | tailwindcss.com/docs                   | ✅ 极充分       |
| shadcn/ui    | ui.shadcn.com                          | ✅ 充分         |
| BGE-M3       | huggingface.co/BAAI/bge-m3             | ⚠️ 中等       |
| bge-reranker | huggingface.co/BAAI/bge-reranker-v2-m3 | ⚠️ 中等       |
| Langfuse     | langfuse.com/docs                      | ⚠️ 中等       |
| RAGAS        | docs.ragas.io                          | ⚠️ 中等       |

## 六、避坑指南

| 坑                           | 说明                            | 应对                                             |
| ---------------------------- | ------------------------------- | ------------------------------------------------ |
| **LangGraph API 变动** | 版本迭代快，AI 可能混用新旧 API | 锁定版本，参考官方 latest 文档                   |
| **BGE 模型下载**       | HuggingFace 国内访问慢          | 用 ModelScope 镜像或 Ollama 拉取                 |
| **pgvector 索引**      | 默认无索引，数据量大后慢        | 建 HNSW 索引（`CREATE INDEX USING hnsw`）      |
| **Next.js App Router** | 与 Pages Router 概念差异大      | 明确使用 App Router，不用`getServerSideProps`  |
| **shadcn/ui 版本**     | CLI 和组件版本可能不一致        | 用`npx shadcn@latest` 统一版本                 |
| **RAGAS 评估成本**     | 每次评估调用 LLM，Token 消耗大  | 用小模型（如 GPT-4o-mini）做评估，控制评估集规模 |
| **BM25 中文分词**      | jieba 分词效果影响检索质量      | 建食材同义词表，查询时扩展                       |

## 七、不选用的技术及原因

| 技术                          | 不选原因                                      |
| ----------------------------- | --------------------------------------------- |
| Django                        | 过重，AI 应用不需要 ORM/Admin/Auth 全家桶     |
| Flask                         | 异步支持弱，性能不如 FastAPI                  |
| Chroma                        | 适合原型，生产环境运维能力弱于 pgvector       |
| Qdrant                        | 本项目规模不需要独立向量数据库，pgvector 够用 |
| Elasticsearch                 | 运维复杂，PG tsvector 可替代                  |
| LangChain Agents (旧版)       | 已被 LangGraph 取代，不再维护                 |
| LlamaIndex                    | RAG 强但 Agent 编排不如 LangGraph，不重复引入 |
| 微服务架构                    | 本科项目过度设计，模块化单体最优              |
| Vue/Nuxt                      | 备选方案，AI 训练数据覆盖不如 React           |
| 多智能体框架 (AutoGen/CrewAI) | 单主 Agent + 工具足够，多智能体增加调试复杂度 |
