
# MealCompass 技术栈清单（v1.3）

> **用途**：喂给 AI Coding 工具（Cursor / Copilot / Claude 等），作为项目开发的技术边界约束。
> **选型原则**：成熟优先、社区资料丰富、AI 训练数据覆盖度高；原 4-6 周全量设计已在 2026-10-11 收敛为三周核心 Agent 闭环，实际范围以 `TODO.md` §0.5 为准。
> **阅读说明**：✅ 表示 AI 训练数据覆盖充分；⚠️ 表示资料中等，需注意版本兼容。
> **变更 v1.2（2026-10-11）**：总览表新增**「实装状态」列**。原因是 v1.0/v1.1 把**规划中**的依赖和**已在用**的依赖混在一张表里，读者会以为 RAGAS / Sentry / shadcn/ui 都在跑。三周聚焦后口径收敛为：**只有代码里真的 import 了、且真机跑通过的才算「在用」**，其余标注状态并指向 [`failed-features.md`](./failed-features.md)。
> **变更 v1.3（2026-10-13）**：前端状态纯函数测试使用 Node.js 20+ 内置 `node:test`，不新增依赖；组件与浏览器自动化框架仍待选型。
> **变更 v1.1（2026-10-06）**：统一跨文档冲突（分层目录、接口位置、前端目录、可观测降级），全局口径见 [`../README.md`](../README.md) 的「全局约定（唯一口径）」。

## 一、技术栈总览

**实装状态口径**：`✅ 在用`（代码里真的调了、真机跑过） ｜ `🚧 已装未接线`（依赖在环境里但代码没用） ｜ `📋 仅规划`（没装、也没用）

| 层级                 | 技术选型                   | 版本锚定                | 实装状态 | 关键理由                                        |
| -------------------- | -------------------------- | ----------------------- | -------- | ----------------------------------------------- |
| **AI 编排**    | LangGraph                  | ≥ 0.2（实装 1.2.14）   | ✅ 在用 | 状态机可控，LangChain 生产版                    |
| **RAG 工具链** | LangChain                  | 0.3.x（实装 `langchain-core`） | ✅ 在用 | RAG 生态最成熟，文档加载/分块/检索全套          |
| **后端框架**   | FastAPI                    | 0.115+                  | ✅ 在用 | 异步高性能，自动 Swagger，AI 应用首选           |
| **数据校验**   | Pydantic                   | v2                      | ✅ 在用 | FastAPI 原生集成，类型安全                      |
| **向量数据库** | PostgreSQL + pgvector      | PG 16+ / pgvector 0.8   | ✅ 在用 | 一份数据库搞定关系+向量+全文检索，零额外运维    |
| **全文检索**   | PostgreSQL tsvector        | 同 PG                   | ✅ 在用（**辅助**；主通道是内存 BM25） | 与 pgvector 同库，无需额外部署 Elasticsearch    |
| **Embedding**  | BGE-M3                     | `BAAI/bge-m3`（SiliconFlow 远端） | ✅ 在用（真机 `degraded_calls=0`） | 中文效果好，支持稠密+稀疏，1024 维              |
| **重排**       | bge-reranker-v2-m3         | `BAAI/bge-reranker-v2-m3` | ✅ 在用 | 轻量，多语言，推理快                            |
| **LLM**        | DeepSeek / OpenAI 兼容 API | `deepseek-ai/DeepSeek-V3` | ✅ 在用 | 通过 OpenAI 兼容接口，可无缝切换                |
| **关键词检索** | rank-bm25 + jieba          | —                      | ✅ 在用 | 轻量，无需独立服务，适合中小规模                |
| **前端框架**   | Next.js                    | 14+                     | ✅ 在用 | React 全栈框架，生态最大，AI 训练数据覆盖极充分 |
| **前端语言**   | TypeScript                 | 5.x                     | ✅ 在用 | 类型安全，AI 生成代码质量更高                   |
| **CSS**        | Tailwind CSS               | v4                      | ✅ 在用 | 实用类优先，AI 生成效率高                       |
| **UI 组件**    | shadcn/ui                  | latest                  | 📋 **仅规划** | `components/ui/` 为空，当前全部手写 Tailwind → [F7](./failed-features.md) |
| **服务端状态** | TanStack Query             | v5                      | ✅ 在用 | 缓存/重取/错误处理标准化                        |
| **客户端状态** | Zustand                    | v5                      | ✅ 在用 | 轻量，学习成本低                                |
| **前端状态测试** | Node.js 内置 `node:test` | Node 20+ | ✅ 在用 | 快照序列化测试进入 CI，无新依赖；浏览器自动化仍待选型 |
| **可观测**     | Langfuse Cloud             | `langfuse-python` ≥ 4.17.0 | ✅ 在用（真机 trace 已确认 GENERATION + usage） | LLM 链路追踪；读取走 Observations API v2        |
| **错误监控**   | Sentry                     | —                       | 📋 **仅规划** | 无任何 SDK 调用，异常只进本地日志 → [F18](./failed-features.md) |
| **评估框架**   | RAGAS                      | latest                  | 📋 **仅规划** | 只评了检索侧，RAGAS 四项没跑 → [F11](./failed-features.md) |
| **容器化**     | Docker + Docker Compose    | —                      | ✅ 在用（PG 必要；Redis 见下行） | 一键起全栈                                      |
| **缓存**       | Redis                      | 7.x                     | 🚧 **已装未接线** | 容器 healthy，但代码 0 引用 → [F17](./failed-features.md) |

## 二、分层详解

### 2.1 AI 层（Agent + RAG）

**框架选型：LangGraph + LangChain**

选择理由：LangGraph 是 LangChain 的“生产版”，提供显式状态管理和 checkpointing，适合复杂可控的工作流。LangChain 负责文档加载、分块、检索等 RAG 链路，两者配合使用。LlamaIndex 虽然 RAG 能力强，但本项目重点在 Agent 编排（多约束、工具调用、反思校验），LangGraph 更匹配。

**LangGraph 结构约束**（**⚠️ v1.2 修订：下面是原规划的 7 节点全量图，实际交付的是 4 节点最小闭环，两者必须分清**）：

```
【原规划（未实现）】
State: 消息历史 / 用户画像 / 约束条件 / 候选菜谱 / 选中菜谱 / 当前步骤
Nodes: parse → clarify → search → filter → rank → reflect → output
Edges: 条件路由（信息不足→澄清，检索为空→放宽约束，校验失败→重试）

【实际交付（在跑）】
Nodes: parse → search →（无候选则 no_solution 短路）→ generate → validate
State: 扁平 TypedDict，无消息历史、无 checkpointer（未挂 PostgresSaver，也无 MemorySaver）
Edges: search 后条件分支；其余为线性
```

**为什么砍到 4 节点**：三周聚焦里，**一条能讲透、有降级、可测量的链路**比七个节点更能说明问题。`clarify` / `filter` / `rank` / `reflect` 的职责被下推了——硬约束直接进 SQL（`rag/retriever.py`），引用校验做成 `validate` 节点，所以它们不是"没做"，而是**没有以独立节点的形式存在**。多轮对话与会话持久化是主动推迟（[F9](./failed-features.md)）。

**RAG 管线约束**（与实测一致）：

```
菜谱卡片层（粗召回） → 向量检索(pgvector, 1024维 HNSW) + BM25(rank-bm25 + jieba)
                    → RRF 融合(k=60, 等权) → bge-reranker-v2-m3 重排 → Top 10
菜谱步骤层（精取详情） → 按 recipe_id 取步骤块（3,806 条步骤向量）
生成层              → 硬约束规则引擎校验 + LLM 生成 + 引用强制
```

> **实测提示（v1.2 补充）**：这条管线**已完整跑通**，但消融显示 **RRF 那一步是净负贡献**（`hybrid` R@5 61.25% < 纯向量 63.75%；重排把 R@10 从 68.75% 拉到 77.50%，增益全部来自重排）。原因与权重建议见 `README.md`「结论二/结论三」——**不要把"管线更长"当成"效果更好"**。

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

**本地兜底已用真模型验证（2026-10-07）**：`BAAI/bge-m3` 与 `BAAI/bge-reranker-v2-m3` 各约 2.2 GB（跳过 2 GB 的 onnx 导出），落在 `<仓库>/.cache/`（已 gitignore）。

| 检查项 | 实测 |
| --- | --- |
| 本地 embedding 维度 | 1024（与 `vector(1024)` 对齐） |
| 本地 rerank 排序 | 番茄炒蛋 →「西红柿炒鸡蛋」0.9961 / 「红烧肉」0.0026 |
| **本地 vs 远程向量余弦相似度** | **0.9999**（同模型、同向量空间，混用不毁索引） |
| 降级链路 | 远程打不通 → `provider=local`，兜底向量仍是 1024 维 |

一键自查：`python -m scripts.check_model_clients`（4 项断言）。

> 不选 `Qwen/Qwen3-Embedding-*` 的原因：维度与既有的 `vector(1024)` 不匹配，换维度要重建索引与迁移，收益不抵成本。
- LLM 通过 API 调用，保留 `LLMClient` 抽象层，便于切换
- 单次推荐 Token 成本 ≤ ¥0.05

### 2.5 前端层

**Next.js 14 + TypeScript + Tailwind + + TanStack Query + Zustand** ✅（**shadcn/ui 未初始化**，见下）

选择理由：Next.js 是 React 生态最成熟的全栈框架，AI 训练数据覆盖最充分，生成代码质量最高。React 在 LLM 训练数据集中占主导地位，AI 生成 UI 代码时几乎首选 React。

**关键约束**：

- 使用 App Router（非 Pages Router）
- 服务端状态用 TanStack Query，客户端状态用 Zustand
- ⚠️ **UI 组件从 shadcn/ui 复制到项目** —— **这一条当前是「规划」，不是现状**：`components/ui/` 是空目录，skeleton 均为手写 Tailwind。三周聚焦把它排到了外围（[F7](./failed-features.md)）。
- 响应式设计，移动端可用
- 目录不带 `src/` 前缀：`app/`、`components/ui/`、`lib/`
- Tailwind v4 用 CSS-first：token 定义在 `app/globals.css` 的 `@theme`，不生成 `tailwind.config.js`

**备选方案**：如果团队更熟悉 Vue，可替换为 Vue 3 + Nuxt 3 + Element Plus，学习曲线更平缓，但 AI 训练数据覆盖度低于 React。

### 2.6 评估与可观测层

**Langfuse ✅ 在用 ｜ RAGAS 📋 仅规划**

**Langfuse（已实装）** 用于 LLM 链路追踪（每一步的输入/输出/延迟/Token）。本项目实现：`infra/observability.py` 统一封装（SDK v4.17.0），key 缺失时降级为 no-op，不阻塞本地开发；读取 trace 一律用 Observations API v2。真机已确认 `parse-intent` 与 `generate-recommendations` 记为 GENERATION 并带 `model` + `usage_details`。

**RAGAS（未实装）** 本文件 v1.1 写的"RAGAS 用于自动化评估（Faithfulness / Answer Relevancy / Context Precision / Context Recall）"**目前没有一行代码**。实际情况是：**只做了检索侧评估**，用自写的 `backend/scripts/eval.py` 算 Recall@5 / Recall@10 / MRR@10 / nDCG@5，共 40 条人工核验查询。

**为什么没上 RAGAS**：① 生成侧评估需要 LLM 当裁判，Token 成本高且判分本身有抖动，40 条样本下结论不稳；② 三周聚焦里"把检索侧消融做扎实"优先级更高（也确实产出了 RRF 结构性缺陷这条负结论）；③ 装 RAGAS 会引入清单外依赖。登记为 [F11](./failed-features.md)，属**主动推迟**而非失败。

**评估指标约束**（**v1.2 修订：原表全是「目标值」，与本项目实测值差距很大，现已改为「目标值 / 实测值」并列**）：

| 维度  | 指标                    | 目标值            | **实测值（2026-10-11）** |
| ----- | ----------------------- | ----------------- | ----------------------- |
| 检索  | Recall@5 / nDCG@5       | ≥ 85% / ≥ 0.8   | **63.75% / 0.6309**（纯向量，40 条评估集）——**未达标，差距归因见 README** |
| 生成  | 引用准确率 / 约束满足率 | ≥ 95% / 100%     | **引用准确率 100%**（`domain/citations.py` 硬校验，编造 `recipe_id` 必被丢弃 + 单测）；**约束满足率未单独测量** |
| Agent | 任务成功率 / 工具准确率 | ≥ 90% / ≥ 95%   | **未测量**（无工具调用节点，本闭环不做 tool calling） |
| 性能  | P95 延迟 / Token 成本   | ≤ 3s / ≤ ¥0.05 | **检索 P95 859 ms（达标）；`/recommend` 端到端 9–12 s（未达标，`parse`+`generate` 串行）**；Token 成本未计 |

> ⚠️ **原 v1.1 表把「目标值」写成了一列孤立数字，读起来像是已经达成。** 这是文档最容易误导人的地方，也是本次修订的起因。**「85%」这个目标值已被删除出 README 的结论口径**，这里保留只是为了标注差距。
> 生成侧四项（RAGAS）未做 → [F11](./failed-features.md)；端到端延迟欠账 → [F14](./failed-features.md)。


## 三、开发工具链

| 工具                     | 用途               | 备注                                |
| ------------------------ | ------------------ | ----------------------------------- |
| **uv**             | Python 包管理      | 比 pip 快 10-100x，AI 生成友好      |
| **Ruff**           | Linter + Formatter | 替代 flake8 + black + isort         |
| **pytest**         | 测试               | **当前实测 589 passed / 4 skipped，生产代码覆盖率 95%**（门禁 ≥ 70%） |
| **Docker Compose** | 本地全栈启动       | 一条命令起 PG + Redis + 后端 + 前端（**Redis 当前只起容器，代码未用**） |
| **Langfuse**       | LLM 可观测         | 自托管或 Cloud                      |
| **GitHub Actions** | CI                 | Lint + Test + Build                 |

## 四、AI 编码约束清单

以下约束可直接写入 Cursor Rules 或 `.cursorrules`：

```
# 技术栈约束
- Python: 3.11+, FastAPI 0.115+, Pydantic v2
- Agent: LangGraph >= 0.2, LangChain 0.3.x
- 数据库: PostgreSQL 16 + pgvector 0.8
- Embedding: BGE-M3 (BAAI/bge-m3), 1024维
- 重排: bge-reranker-v2-m3
- 前端: Next.js 14 App Router + TypeScript + Tailwind v4（目录不带 src/）；**shadcn/ui 未初始化**，勿引用其组件
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

| 技术         | 官方文档                               | AI 训练数据覆盖 | 本项目 |
| ------------ | -------------------------------------- | --------------- | ------ |
| LangGraph    | langchain-ai.github.io/langgraph       | ✅ 充分         | ✅ 在用（1.2.14） |
| LangChain    | python.langchain.com                   | ✅ 充分         | ✅ 在用（`langchain-core`） |
| FastAPI      | fastapi.tiangolo.com                   | ✅ 充分         | ✅ 在用 |
| Pydantic v2  | docs.pydantic.dev                      | ✅ 充分         | ✅ 在用 |
| pgvector     | github.com/pgvector/pgvector           | ✅ 充分         | ✅ 在用（0.8） |
| Next.js      | nextjs.org/docs                        | ✅ 极充分       | ✅ 在用（App Router） |
| Tailwind CSS | tailwindcss.com/docs                   | ✅ 极充分       | ✅ 在用（v4 CSS-first） |
| shadcn/ui    | ui.shadcn.com                          | ✅ 充分         | 📋 **未采用**（手写组件，[F7](./failed-features.md)） |
| BGE-M3       | huggingface.co/BAAI/bge-m3             | ⚠️ 中等       | ✅ 在用（SiliconFlow 远端） |
| bge-reranker | huggingface.co/BAAI/bge-reranker-v2-m3 | ⚠️ 中等       | ✅ 在用 |
| Langfuse     | langfuse.com/docs                      | ⚠️ 中等       | ✅ 在用（真机 trace 已验证） |
| RAGAS        | docs.ragas.io                          | ⚠️ 中等       | 📋 **未采用**（[F11](./failed-features.md)） |

## 六、避坑指南

| 坑                           | 说明                            | 应对                                             |
| ---------------------------- | ------------------------------- | ------------------------------------------------ |
| **LangGraph API 变动** | 版本迭代快，AI 可能混用新旧 API | 锁定版本，参考官方 latest 文档                   |
| **BGE 模型下载**       | HuggingFace 国内访问慢          | 用 ModelScope 镜像或 Ollama 拉取；本项目走 SiliconFlow 远端 API，**不下载本地模型**（`sentence-transformers` 未安装，本地兜底未验证） |
| **pgvector 索引**      | 默认无索引，数据量大后慢        | 建 HNSW 索引（`CREATE INDEX USING hnsw`）      |
| **Next.js App Router** | 与 Pages Router 概念差异大      | 明确使用 App Router，不用`getServerSideProps`  |
| **shadcn/ui 版本**     | CLI 和组件版本可能不一致        | ⚠️ **本项目未采用 shadcn/ui**（`components/ui/` 为空，全部手写 Tailwind）。若后续引入，用 `npx shadcn@latest` 统一版本，并把主题映射到 `docs/UI_STYLE.md` 的 Natural Organic 调色板 |
| **RAGAS 评估成本**     | 每次评估调用 LLM，Token 消耗大  | ⚠️ **本项目未采用 RAGAS**（只做了检索侧评估）。若后续引入：用小模型做裁判、控制评估集规模；注意裁判判分本身有抖动，小样本下的差异不能当结论 |
| **BM25 中文分词**      | jieba 分词效果影响检索质量      | **tsv 与 BM25 必须共用 `rag/tokenization.py` 的同一分词**（改分词 = 全量重建 tsv 与 BM25 语料）；另注意 BM25 语料是内存实现，**不能继承向量通道的 Top50 边界**，否则丧失独立召回价值 |
| **RRF 融合的隐性陷阱** | 等权 RRF 下 `1/(k+1) < 2/(k+池大小)`，双通道候选**必然**压过所有单通道候选 | 别只看"两路都召回了"就觉得更稳；**必须做消融**（本项目实测混合检索 R@5 61.25% < 纯向量 63.75%，详见 `README.md` 结论二） |
| **重灌后忘重建索引**   | 卡片文本变了但向量没重算，指标"看起来没变"却完全不可信 | 走 `docs/CONVENTIONS.md` §4.6 的六步证据链：留底 → 重灌 → **重建索引** → 校验标注 → 全量重跑 → 一次性统一文档 |

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
