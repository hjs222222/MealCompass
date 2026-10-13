
# MealCompass 轻量化架构草案（v0.1）

> **性质**：草案，不是宪法。允许迭代，每次迭代必须记录原因。
> **用途**：喂给 AI Coding 工具作为架构约束基线。
> **原则**：模块化单体 > 微服务；抽象接口先行；能少一个组件就少一个。

## 一、目录架构（怎么分层）

```
mealcompass/
├── backend/
│   ├── api/                  # 路由层：只做参数校验 + 调用 service
│   │   ├── v1/
│   │   │   ├── auth.py
│   │   │   ├── profile.py
│   │   │   ├── recommend.py
│   │   │   ├── recipe.py
│   │   │   ├── shopping.py
│   │   │   └── feedback.py
│   │   └── deps.py           # FastAPI Depends 统一出口
│   │
│   ├── services/             # 业务编排层：事务边界，组合 domain + infra
│   │   ├── auth_service.py
│   │   ├── profile_service.py
│   │   ├── recommend_service.py
│   │   ├── recipe_service.py
│   │   ├── shopping_service.py
│   │   └── feedback_service.py
│   │
│   ├── domain/               # 领域层：纯逻辑，无 IO，可单测（唯一无 IO 层）
│   │   ├── ports.py          # 所有 Protocol：RecipeRepository / Retriever / LLMClient / EmbeddingClient / RerankClient
│   │   ├── models/           # 实体、值对象
│   │   ├── rules/            # 规则引擎
│   │   │   ├── base.py       # Rule Protocol
│   │   │   ├── allergen.py   # 忌口 / 过敏原硬约束
│   │   │   ├── time_limit.py # 可用时间硬约束
│   │   │   ├── tools.py      # 可用厨具硬约束
│   │   │   ├── taste.py      # 口味 / 菜系软偏好
│   │   │   └── registry.py   # 规则注册表
│   │   └── profiles/         # 用户画像定义
│   │       ├── base.py       # UserProfile 值对象
│   │       └── defaults.py   # 默认画像与口味标签
│   │
│   ├── agents/               # Agent 层：LangGraph 编排
│   │   ├── state.py          # State 定义
│   │   ├── graph.py          # 图构建
│   │   ├── nodes/            # 节点
│   │   │   ├── parse.py
│   │   │   ├── clarify.py
│   │   │   ├── search.py
│   │   │   ├── filter.py
│   │   │   ├── rank.py
│   │   │   ├── reflect.py
│   │   │   └── output.py
│   │   └── tools/            # 工具注册表
│   │       ├── base.py
│   │       ├── search_recipes.py
│   │       ├── get_recipe.py
│   │       ├── substitute.py
│   │       ├── scale.py
│   │       └── shopping_list.py
│   │
│   ├── rag/                  # RAG 层：检索、重排、切分
│   │   ├── chunking.py
│   │   ├── embedding.py      # BGE-M3 封装
│   │   ├── retriever.py      # 混合检索（向量 + BM25 + RRF）
│   │   ├── reranker.py       # bge-reranker 封装
│   │   └── indexer.py        # 建索引脚本
│   │
│   ├── infra/                # 基础设施层：DB、LLM、Redis、缓存
│   │   ├── db.py             # SQLAlchemy / asyncpg
│   │   ├── llm_client.py     # OpenAI 兼容接口封装
│   │   ├── redis_client.py
│   │   ├── vector_store.py   # pgvector 封装
│   │   └── observability.py  # Langfuse / Sentry
│   │
│   ├── core/                 # 核心配置
│   │   ├── config.py         # pydantic-settings
│   │   ├── logging.py
│   │   ├── exceptions.py
│   │   └── security.py       # JWT、密码哈希
│   │
│   ├── scripts/              # 一次性脚本
│   │   ├── seed_recipes.py   # 导入菜谱
│   │   ├── build_index.py    # 建向量索引
│   │   ├── eval.py           # 跑评估集
│   │   ├── e2e_probe.py      # 端到端 5 场景真机复跑（证据入口）
│   │   ├── e2e_latency_summary.py  # 多轮探针输出 → 区间表
│   │   ├── summarize_eval_reports.py  # 评估报告 → 可入库摘要（含 SHA256）
│   │   ├── channel_attribution.py     # RRF 通道归因（只读复算）
│   │   └── rerank_variance.py         # 重排跑间抖动量化
│   │
│   ├── tests/
│   ├── main.py               # FastAPI 入口
│   ├── pyproject.toml
│   └── Dockerfile
│
├── frontend/
│   ├── app/                  # Next.js App Router
│   │   ├── (auth)/
│   │   │   ├── login/page.tsx
│   │   │   └── register/page.tsx
│   │   ├── (main)/
│   │   │   ├── recommend/page.tsx
│   │   │   ├── chat/page.tsx
│   │   │   ├── recipe/[id]/page.tsx
│   │   │   ├── cook/[id]/page.tsx
│   │   │   ├── shopping/page.tsx
│   │   │   ├── history/page.tsx
│   │   │   └── profile/page.tsx
│   │   ├── onboarding/page.tsx
│   │   ├── legal/page.tsx
│   │   └── layout.tsx
│   ├── components/
│   │   ├── ui/               # shadcn/ui
│   │   ├── recipe/
│   │   ├── recommend/
│   │   └── common/
│   ├── lib/
│   │   ├── api.ts            # API 客户端
│   │   ├── stores/           # Zustand
│   │   └── hooks/            # TanStack Query hooks
│   ├── package.json
│   └── Dockerfile
│
├── data/
│   ├── recipes/              # 原始菜谱 JSON（可重建，gitignore）
│   ├── rules/                # 规则 YAML（可热更新）
│   ├── ingredients/          # 食材归一化词典（别名 → 标准名，T1.3）
│   └── eval/                 # 评估集（queries.yaml 入库；reports/ 可重建，gitignore）
│
├── docs/
│   └── evidence/             # ★ 入库的原始证据（指标摘要/抖动/归因/端到端/清理前后）
│                             #   正文数字必须能追到这里，见 docs/evidence/README.md
│
├── docker-compose.yml
└── README.md
```

> **前端落地进度（2026-10-09，T1.17/T1.18）**：上面的 `frontend/` 是**目标**结构，当前只落了骨架与数据层：
> `app/{layout,page,loading,error}.tsx`、`app/(auth)/login/`、`app/(main)/dashboard/`、`components/{providers,status-panel}.tsx`、`lib/api.ts`、`lib/query-client.ts`、`lib/hooks/`、`lib/stores/`。
> 尚未创建：`recommend` / `chat` / `recipe` / `cook` / `shopping` / `history` / `profile` / `onboarding` / `legal` 页面，以及 `components/ui/`（shadcn/ui）。未完成项登记在 `docs/failed-features.md`。
>
> **前端边界契约**：`app/layout.tsx` 保持 Server Component；`components/providers.tsx` 是唯一客户端 Provider 边界（QueryClientProvider）。服务端状态只走 TanStack Query（`lib/hooks/`），客户端 UI 状态只走 Zustand（`lib/stores/`），两者不混。`lib/api.ts` 是唯一 HTTP 出口，错误统一归一化为 `ApiError`。

**分层依赖方向（单向，不可逆）**：

```
api → services → domain
              → agents → rag → infra
              → infra
```

- `domain` 不依赖任何层（纯逻辑）
- `infra` 可被上层依赖，但不反向依赖
- `api` 只调 `services`，不直接调 `infra`

**浏览器跨域边界（W3.10）**：`main.create_app` 装配 FastAPI 自带的 `CORSMiddleware`，来源由 `core.config.Settings.cors_allow_origins` 统一读取（环境变量 `CORS_ALLOW_ORIGINS`，JSON 数组）。默认允许 localhost / 127.0.0.1 的 3000 端口；允许 GET / POST / OPTIONS、JSON 与 request-id 请求头，暴露 `X-Request-ID`，不启用跨域凭证。CORS 在 request-id 中间件外层，确保该中间件生成的安全 500 响应仍可被浏览器读取。

## 二、核心模块（有哪些模块）

| 模块                    | 职责                  | 对外接口                  | 依赖                          |
| ----------------------- | --------------------- | ------------------------- | ----------------------------- |
| **auth**          | 注册/登录/JWT         | `AuthService`           | infra.db, core.security       |
| **profile**       | 画像 CRUD、约束集选择 | `ProfileService`        | domain.profiles, infra.db     |
| **recipe**        | 菜谱 CRUD、详情、缩放 | `RecipeService`         | infra.db                      |
| **rag**           | 检索、重排、索引      | `Retriever`（定义在 `domain/ports.py`） | infra.vector_store, infra.llm |
| **agent**         | LangGraph 编排        | `run_agent(state)`      | rag, domain.rules, infra.llm  |
| **rules**         | 硬约束判定            | `RuleEngine.evaluate()` | domain.models                 |
| **recommend**     | 推荐编排              | `RecommendService`      | agent, profile, recipe        |
| **shopping**      | 清单合并、导出        | `ShoppingService`       | recipe                        |
| **feedback**      | 反馈、记忆            | `FeedbackService`       | infra.db                      |
| **observability** | LLM 追踪、异常        | 无（横切）                | Langfuse, Sentry              |

**模块间通信规则**：

- 同层模块不互相调用，通过 `services` 编排
- 跨层调用只允许上层调下层
- 新功能 = 新增模块 + 注册，不改核心

## 三、数据模型（长什么样）

### 3.1 核心表

> ⚠️ **实现以 `backend/infra/tables.py` 为准**（v0.6 起），下面是设计草图。已落地的细化：
>
> - `difficulty` 用 `SMALLINT` + `CHECK (BETWEEN 1 AND 5)`（导入器产出的是 1-5 星整数，不是字符串）
> - `recipes` 补了 `slug` / `description` / `category` / `images` / `external_images` / `source_path` / `source_url` / `license` / `extra` / `servings_text`
> - `recipe_ingredients` 补了 `name_raw` / `amount_text` / `amount_min` / `amount_max` / `note` / `per_serving`；**`ingredient_id` 可空**（词表未收录的食材没有标准实体）
> - `recipe_steps` 加 `(recipe_id, step_no)` 唯一约束
> - 索引：`recipe_embeddings.embedding` 与 `recipe_steps.embedding` 各建 HNSW（m=16, ef_construction=64, cosine）；`recipe_embeddings.tsv` 与 `recipes.tags` 建 GIN
> - 迁移与 metadata 的漂移由 `tests/unit/test_schema_metadata.py` 自动拦截
> - `slug` 由 `source_path` 派生（上游有两道菜 H1 同名「鸡蛋羹」，用「分类-菜名」会撞唯一约束）
> - `servings_text` / `amount_text` 这类**上游原文**字段用 `TEXT`：实测有 257 字的原文，VARCHAR(n) 会直接让入库失败

```sql
-- 用户
users (
  id UUID PK,
  email VARCHAR UNIQUE,
  password_hash VARCHAR,
  created_at TIMESTAMP
)

-- 画像
user_profiles (
  id UUID PK,
  user_id UUID FK,
  taste_preferences JSONB,     -- ["微辣","清淡","川菜"]
  hard_constraints JSONB,      -- 规则 ID 列表（忌口/过敏、时间、厨具）
  soft_preferences JSONB,      -- 软偏好（少油少盐、菜系等）
  tools_available JSONB,       -- ["炒锅","空气炸锅"]
  skill_level VARCHAR,
  updated_at TIMESTAMP
)

-- 菜谱
recipes (
  id UUID PK,
  name VARCHAR,
  aliases JSONB,               -- ["西红柿炒鸡蛋"]
  cuisine VARCHAR,
  tags JSONB,                  -- ["快手","低脂"]
  time_minutes INT,
  difficulty VARCHAR,
  tools JSONB,
  servings INT,
  nutrition JSONB,             -- {"calories":320}（仅热量，HowToCook 预估）
  images JSONB,                -- 配图相对路径数组，首张作封面；外链另存 external_images
  source VARCHAR,              -- 数据来源，合规用
  created_at TIMESTAMP
)

-- 菜谱步骤（独立表，便于步骤级检索）
recipe_steps (
  id UUID PK,
  recipe_id UUID FK,
  step_no INT,
  content TEXT,
  embedding VECTOR(1024)       -- pgvector
)

-- 食材
ingredients (
  id UUID PK,
  name VARCHAR UNIQUE,
  category VARCHAR             -- 蔬果/肉类/调料
)

-- 食材同义词
ingredient_aliases (
  id UUID PK,
  ingredient_id UUID FK,
  alias VARCHAR,
  UNIQUE(alias)
)
-- 种子数据：data/ingredients/aliases.yaml（T1.3，别名 → 标准名 + 分类）

-- 菜谱-食材关联
recipe_ingredients (
  id UUID PK,
  recipe_id UUID FK,
  ingredient_id UUID FK,
  amount FLOAT,
  unit VARCHAR,
  optional BOOLEAN
)

-- 菜谱卡片向量（粗召回用）
recipe_embeddings (
  recipe_id UUID PK FK,
  embedding VECTOR(1024),
  tsv TSVECTOR                 -- 全文检索
)

-- 对话
conversations (
  id UUID PK,
  user_id UUID FK,
  state JSONB,                 -- LangGraph 状态快照
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)

messages (
  id UUID PK,
  conversation_id UUID FK,
  role VARCHAR,                -- user/assistant
  content TEXT,
  metadata JSONB,
  created_at TIMESTAMP
)

-- 反馈
feedbacks (
  id UUID PK,
  user_id UUID FK,
  recipe_id UUID FK,
  type VARCHAR,                -- like/dislike/favorite/cooked
  created_at TIMESTAMP
)

-- 购物清单
shopping_lists (
  id UUID PK,
  user_id UUID FK,
  recipe_ids JSONB,
  items JSONB,                 -- [{"name":"番茄","amount":4,"unit":"个","checked":false}]
  created_at TIMESTAMP
)
```

### 3.2 规则配置（YAML，不入库）

```yaml
# data/rules/default.yaml
hard_constraints:
  - id: avoid_allergens        # 忌口 / 过敏原，命中即过滤
    field: ingredients
    operator: "not_in"
    value_from_profile: allergies
  - id: time_limit
    field: time_minutes
    operator: "<="
    value_from_profile: max_minutes
  - id: tools_available
    field: tools
    operator: "subset_of"
    value_from_profile: tools_available
soft_preferences:
  - id: prefer_mild             # 口味偏好，加分而非过滤
    field: tags
    contains: 清淡
    boost: 1.2
```

**为什么规则用 YAML 不用 DB**：可版本控制、可评审、非技术人员可改、无需迁移。未来需要热更新再迁 DB。

### 3.3 索引策略

```sql
-- 向量索引（HNSW）
CREATE INDEX ON recipe_embeddings
  USING hnsw (embedding vector_cosine_ops);

-- 全文索引
CREATE INDEX ON recipe_embeddings USING gin(tsv);

-- 常用过滤字段
CREATE INDEX ON recipes (time_minutes);
CREATE INDEX ON recipes USING gin(tags);
```

## 四、服务端逻辑（哪些必须在服务端）

**判定原则**：涉及安全、数据一致性、成本、密钥、规则判定的，必须在服务端。

| 逻辑                | 必须在服务端 | 理由                         |
| ------------------- | ------------ | ---------------------------- |
| JWT 签发与校验      | ✅           | 密钥不能暴露前端             |
| 密码哈希            | ✅           | 同上                         |
| 硬约束规则判定      | ✅           | 前端可篡改，忌口/过敏约束必须可信 |
| 过敏原/疾病禁忌过滤 | ✅           | 安全关键，不可信前端         |
| LLM 调用            | ✅           | API Key 保护 + 成本控制      |
| Embedding 计算      | ✅           | 模型权重 + 资源              |
| 向量检索            | ✅           | 数据库访问                   |
| BM25 检索           | ✅           | 同上                         |
| 重排                | ✅           | 模型推理                     |
| Agent 编排          | ✅           | 状态机 + 工具调用            |
| 反思校验            | ✅           | 安全兜底                     |
| 购物清单合并        | ✅           | 数据一致性                   |
| 限流                | ✅           | 防刷                         |
| 成本统计            | ✅           | 账单                         |
| 用户画像存储        | ✅           | 隐私                         |
| 历史记录            | ✅           | 数据持久化                   |
| 菜谱详情渲染        | ❌           | 可前端                       |
| 份量缩放计算        | ⚠️ 可前端  | 但需服务端校验               |
| UI 状态             | ❌           | 前端 Zustand                 |
| 表单校验（基础）    | ❌           | 前端可做，服务端仍需二次校验 |
| 计时器              | ❌           | 前端                         |
| 语音播报            | ❌           | 前端 Web Speech API          |

**服务端二次校验原则**：前端做的校验，服务端必须再做一次（信任边界）。

## 五、关键接口草案

```python
# domain/ports.py —— 所有 Protocol 集中在此文件
class RecipeRepository(Protocol):
    async def get_by_id(self, recipe_id: str) -> Recipe | None: ...
    async def search(
        self,
        filters: HardFilters | None = None,
        limit: int = 50,
    ) -> list[Recipe]: ...

class Retriever(Protocol):
    async def search(
        self,
        query: str,
        filters: HardFilters | None = None,  # 硬约束下推
        top_k: int = 10,
    ) -> list[RecipeCandidate]: ...

# domain/rules/base.py
class Rule(Protocol):
    def evaluate(self, recipe: Recipe, profile: UserProfile) -> RuleResult: ...

# agents/graph.py（**已落地，见 v1.6**）
@dataclass
class AgentDeps:
    retriever: Retriever
    llm: LLMClient
    settings: Settings

def build_graph(deps: AgentDeps, *, checkpointer: Any = None) -> Any: ...
async def run_agent(query: str, filters: HardFilters | None, *, deps: AgentDeps, top_k: int = 3) -> RecommendResponse: ...

# domain/ports.py（实现：infra/llm_client.py）
class LLMClient(Protocol):
    model: str
    async def complete(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.1,
        response_format: str | None = None,
    ) -> str: ...

class EmbeddingClient(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

class RerankClient(Protocol):
    async def rerank(self, query: str, docs: list[str], top_k: int = 10) -> list[tuple[int, float]]: ...
```

**推荐菜谱详情展示（W3.12、W3.17）**：`domain.ports.RecipeDetailsReader.get_details(recipe_ids)` 批量读取最终引用 ID 的菜谱详情；`infra.recipe_details.SqlRecipeDetailsReader` 读取原料份量、工具、步骤、附加说明、图片及来源，并由纯函数提取简介中明确的原文总时长文本（保留约值/区间）。Agent 完成引用校验后，service 只为最终 ID 补充 `Recommendation.details`。独立页面 `/recipe/[id]` 通过 `GET /recipes/{recipe_id}` 与 `RecipePageReader`/`RecipePageService` 按 ID 重新读取，支持直接访问和刷新；推荐卡片标题与完整菜谱入口均链接该页。图片通过受限 `/recipe-images/{path}` 静态端点提供；路径越界、非图片后缀和不存在文件返回 404。读取详情失败保留推荐并标记 `recipe_details_unavailable`。步骤详情展示不代表步骤向量参与召回，F21 仍未实现。

**接口约束**：

- 所有 IO 操作 `async`
- 所有对外接口用 Pydantic 模型
- Protocol 统一定义在 `domain/ports.py`，实现在 `infra/`（LLM、向量库）与 `rag/`（检索编排）
- Embedding / Rerank 的协议实现落在 `infra/embedding_client.py` 与 `infra/rerank_client.py`：`Remote*`（SiliconFlow OpenAI 兼容）+ `Local*`（sentence-transformers，可选）+ `Fallback*`（远程优先、本地兜底）；`rag/` 只负责编排（切分、检索、融合、索引），不直接持有模型客户端
- 降级事实通过 `Fallback*.last_provider` / `degraded_count` / `last_error` 暴露，由调用方写进 trace 的 metadata

## 六、迭代日志（每次修改必记）

| 版本 | 日期       | 变更     | 原因     |
| ---- | ---------- | -------- | -------- |
| v0.1 | 2026-10-06 | 初始草案 | 建立基线 |
| v0.2 | 2026-10-06 | 统一跨文档冲突（人群范围、profiles 归属、接口位置、会话存储、工期）；补充接口清单 | 消除与 PRD/TECH_STACK/CONVENTIONS 的歧义 |
| v0.3 | 2026-10-06 | **取消医学人群细分**，规则改为通用约束（忌口/时间/厨具/口味）；新增 EmbeddingClient / RerankClient 接口（远程优先、本地兜底） | 医学营养数据不可得，避免不可验证的约束 |
| v0.4 | 2026-10-06 | 菜谱模型新增 `images` / `external_images`；354 张配图随菜谱入库 | 网页端详情页需要成品图，纯文本 RAG 之外还要展示 |
| v0.5 | 2026-10-06 | 新增 `data/ingredients/aliases.yaml` 归一化词典与 `domain/ingredients.py`；`Ingredient` 增加 `canonical` / `category` | 检索与忌口过滤需要把「西红柿/番茄」收敛到同一个标准名 |
| v0.6 | 2026-10-06 | 落库实现：`infra/tables.py`（12 张表）+ Alembic `0001_initial_schema`；§3.1 补实现要点 | 数据齐了要进库，检索/规则才有落点 |
| v0.7 | 2026-10-06 | 迁移 0002：`servings_text` / `amount_text` 放宽为 TEXT；`slug` 改由 `source_path` 派生 | 实机入库暴露的两个真问题：原文超长、同名菜谱 slug 冲突 |
| v0.8 | 2026-10-07 | 落地 `domain/ports.py` 的 EmbeddingClient / RerankClient 与 `infra/` 的 Remote / Local / Fallback 三实现 | T1.7：模型调用要远程优先、本地兜底且可观测 |
| v0.9 | 2026-10-07 | 新增 `infra/model_cache.py`（模型缓存固定到仓库内）；本地兜底用真模型验证（本地/远程余弦 0.9999） | 缓存路径不一致会白下 4.4 GB；本地兜底必须证明与远程同空间 |
| v1.0 | 2026-10-07 | T1.6 落地：`rag/chunking.py` 双层切分（卡片=菜名+简介+食材 / 步骤=原文）+ `scripts/build_index.py`（embedding + tsv 入库，幂等可重跑）；`rag/tokenization.py` 统一 jieba 分词，tsv 用 `to_tsvector('simple')` | 双层索引是混合检索（T1.8）的落点；tsv 与 BM25 共用同一分词，词项一致 |
| v1.1 | 2026-10-07 | T1.8 落地：`rag/retriever.py` HybridRetriever（向量 Top50 + BM25 Top50 → RRF → Top10）；`rag/corpus.py` CardCorpus 与向量共用同一卡片文档；`scripts/smoke_retrieval.py` 真查询冒烟 | 混合检索是 F-B3 的落点；BM25 语料与向量 embed 的是同一份文本，两个通道才可融合 |
| v1.2 | 2026-10-07 | T1.9 落地：`rag/reranker.py` 重排编排（失败降级回 RRF 顺序并标记 degraded）；`HybridRetriever` 可选 `reranker` 参数；`smoke_retrieval --rerank` 真远程验证 | F-B4 重排落点；重排绝不能拖垮检索，降级是契约 |
| v1.4 | 2026-10-07 | T1.14-T1.16 收尾：FastAPI lifespan 校验 prod secret，`APP_VERSION` 统一 `/version` 与 OpenAPI；request-id middleware 与 JSON 日志保留安全扩展字段、服务端 traceback | 配置/异常/日志契约需可验证，敏感信息不得进入响应或日志 |
| v1.5 | 2026-10-09 | T1.17/T1.18 落地 `frontend/`：App Router 骨架 + `(auth)`/`(main)` 路由组（layout 保持 Server Component，Providers 是唯一客户端边界）；Natural Organic token 进 `app/globals.css` 的 `@theme`；数据层 `lib/api.ts`（类型守卫 + `ApiError`）+ `lib/hooks/`（TanStack Query）+ `lib/stores/`（Zustand）+ `status-panel`（加载/错误/重试） | 前后端骨架是 M1 验收落点；服务端状态与客户端状态必须分离，HTTP 错误必须归一化 |
| **v1.6** | **2026-10-11** | **W1-W3 三周聚焦：新增 `domain/models/recommend.py`（`RecommendRequest`/`SearchRequest`/`SearchResponse`/`RecommendResponse` 四个对外契约模型）+ `infra/llm_client.py`（`RemoteLLM` / `strip_code_fence` / `build_llm_client`，OpenAI 兼容 + 指数退避）+ `agents/`（`state.py` 状态与常量、`jsonx.py` 脏 JSON 稳健解析、`nodes.py` 五节点、`graph.py` 组装与 `AgentDeps`）+ `services/recommend_service.py`（`RecommendService`）+ `api/v1/recommend.py`（`POST /recommend`、`POST /recipes/search`）+ `scripts/eval.py` + `data/eval/queries.yaml` + `.github/workflows/ci.yml`。**Agent 拓扑固定为 `START → parse → search ─┬─(有候选)→ generate → validate → END └─(无候选)→ no_solution → END`**；`domain/citations.py` 从死代码变为 `node_validate` 的核心校验 | **原计划 7 节点（澄清追问/反思重试/工具调用）+ 5 工具 + 11 页面在三周内做不完，且核心链路一行代码都没有**；改为「一条能讲透、能测量、有降级路径的完整链路」，把时间投到评估集与消融实验。评估结论已证明这个取舍的价值：**混合检索在 40 条评估集上未超过纯向量（RRF 负贡献），唯一正收益来自重排**——这类结论只有做了消融才会知道 |
| v1.7 | 2026-10-11 | `CONVENTIONS` §4.5 观察名表修正：`PARSE_INTENT` 的类型由 `span` 改为 **`generation`**（补 `CLARIFY_REQUEST` / `EVAL_RETRIEVAL` / `EVAL_FAITHFULNESS` 三行）。**观察名（命名契约）不变，只改类型** | 「LLM 调用必须记为 generation 并带 model + usage_details」是硬规则，而 `parse-intent` 确实是一次 LLM 调用；两条规则冲突时以硬规则为准。真机 Langfuse 已确认带 `model` 与 `usage_details`，类型改对反而让成本/Token 视图变完整 |
| v1.8 | 2026-10-11 | `/dashboard` 文案修正：删掉「页面刻意不展示推荐结果：推荐 Agent…尚未实现」这句已过期的描述，改为指向 `/recommend`，并把「未完成能力统一记录在 `docs/failed-features.md`」保留 | 推荐链路已上线（`/recommend`），旧文案与现状矛盾；文档与界面都不许假装未做的东西可用，也不许假装已做的东西不存在 |
| v1.9 | 2026-10-11 | 解析层（`scripts/import_howtocook.py`）新增噪声过滤与并列拆分：`_is_section_heading` / `_looks_like_prose` 扩容（用量句、容量句、缩放规则）/ `TOOL_KEYWORDS` 扩 20 项 / 新导出 `parse_ingredient_lines`（`、` `/` `+` 拆分）。**卡片文档的食材输入随之变化**，因此重灌 `seed_recipes` 后**必须重跑 `scripts/build_index`**（本次重建 372 卡片 + 3,806 步骤向量） | 「必备原料和工具」区里混着章节小标题（`工具`/`原料:`）、说明句（`盐的用量为`）、缩放规则（`肉量 = 份数 * 200g`）与工具名，被当成食材后既污染 `unmapped_top` 又拉低归一化率；修在解析层而不是往词表塞垃圾。**代价是卡片文本变了 → embedding 变 → 检索指标变**，已按「留底 → 重灌 → 重建索引 → 校验 40/40 → 全量重跑」流程处理，三组消融结论未变 |
| v1.10 | 2026-10-11 | 检索评估结论落地到文档：`README.md`「评估结果」四节 + 权重敏感性表全部换成重灌后的实测数字；`docs/INTERVIEW.md` 补 Q4.4b（降级标签精确契约）、Q4.4c（`node_parse` 数组边界）、Q7.4 重写（RRF 结构不等式 + 权重实验）、Q7.5（抖动与 P95 不可信）、Q7.6（63.75% 的差距归因） | 早期 README 写过「Recall@5 ≥ 85%」这个**无测量支撑**的目标值，且「BM25 噪声顶头部」的归因被逐条三元组分析否定；文档必须与实测一致，负面结论也要留档 |
| v1.11 | 2026-10-11 | **新增证据层 `docs/evidence/`（入库）与 5 个复现脚本**：`scripts/e2e_probe.py`（端到端 5 场景）、`e2e_latency_summary.py`（多轮聚合成区间）、`summarize_eval_reports.py`（评估摘要 + SHA256）、`channel_attribution.py`（RRF 通道归因）、`rerank_variance.py`（重排抖动）。架构上属于**只读的观测/汇总层**：只消费 `data/eval/reports/*.json` 与 HTTP 响应，不改 `rag/`、`agents/` | 正文数字需要一个可对账的落点：`data/eval/reports/` 与 `.tmp/` 都在 gitignore 里，别人 clone 后无法验证任何数字。同时暴露出两类真实事故：探针写死响应字段名（`results` vs 契约 `candidates`）导致把 5 条候选报成 0 条；同一代码三轮延迟差 2.8 s 而给的是单一精确值 |

| v1.12 | 2026-10-12 | FastAPI 入口装配 CORS 中间件；`Settings.cors_allow_origins` / `CORS_ALLOW_ORIGINS` 配置浏览器来源白名单；错误响应保留跨域头 | 浏览器 JSON POST 预检 405，状态接口虽返回 200 但无跨域头，造成 network_error |

| v1.13 | 2026-10-12 | 新增 RecipeStepsReader / SqlRecipeStepsReader，推荐校验后回填原文步骤；Recommendation.steps 默认空列表，前端查看做法 | 数据库步骤已入库但推荐契约未输出，用户无法查看做法 |

| v1.14 | 2026-10-12 | HardFilters / RecommendRequest / SearchRequest 新增 `category: str | None` 字段并 SQL 下推到 `recipes.category`（已有 `ix_recipes_category` 索引）；`core/logging.py` 加 `RotatingFileHandler`（5MB×3，写 `.tmp/logs/mealcompass.log`）；食材词表补「南瓜」标准食材 + [小南瓜/金瓜/倭瓜/番瓜/南瓜块/南瓜泥] 别名，修复"不要南瓜"仍推荐山药南瓜炖鸡汤的硬约束漏过滤 | ① `recipes.category` 列早已存在但检索层没接，前端无法按分类筛；② 日志只有 stderr 被启动脚本重定向到固定文件，无轮转；③ 食材写法差异（小南瓜≠南瓜）+ 词表缺条目导致忌口硬约束漏菜，这是 demo 级信任事故 |

| v1.15 | 2026-10-13 | `rag/retriever.py` 在生成两个召回通道的允许 ID 集合时，先用 `aliases.yaml` 展开忌口标准名与同义名，再用转义后的包含匹配检查 `recipes.name`、`recipe_ingredients.name_raw`、已映射标准名和别名；跨其他食材名称有歧义的短别名不作宽泛展开；词典增加经上游原文证实的「薯条」→「土豆」；仍在 SQL 层排除，不改变索引文本与向量 | 先前的 `LIKE` 只查原料关联行：当前库里「五花肉条」未映射，菜名「猪肉烩酸菜」也未进入谓词，导致已有修复后仍漏猪肉；「西红柿」与「番茄酱」跨标准名也会漏。直接展开全部猪肉别名还会误伤「牛里脊」，需保留本质区分 |

| v1.16 | 2026-10-13 | 新增 `GET /recipes/{recipe_id}`、`RecipePageReader` 与 `/recipe/[id]`；详情按真实 ID 读取，推荐卡片不再内嵌完整原料与步骤 | 用户从推荐卡片进入完整菜谱后需要独立网址，便于刷新与分享 |

**迭代规则**：

1. 每次架构变更必须在此表登记
2. 记录变更内容和原因（为什么改）
3. 破坏性变更需标注影响范围
4. 草案允许推翻，但需说明新方案优于旧方案的理由

## 七、AI 编码约束（可直接写入 .cursorrules）

```
# 架构约束
- 分层: api → services → domain / agents / rag → infra
- domain 层不依赖任何其他层，纯逻辑
- 用户画像放 `domain/profiles/`，跨层接口 Protocol 放 `domain/ports.py`
- api 层不直接调 infra，必须经过 services
- 同层模块不互相调用

# 数据约束
- 所有表用 UUID 主键
- 向量维度固定 1024（BGE-M3）
- 硬约束字段建索引
- 规则用 YAML，不入库

# 服务端约束
- LLM 调用、规则判定、检索、鉴权必须在服务端
- 前端校验服务端必须二次校验
- 所有 IO 操作用 async

# 接口约束
- 抽象接口先行（Protocol）
- 所有对外接口用 Pydantic 模型
- 换 LLM 供应商 ≤ 1 天工作量

# 禁止
- 不引入技术栈清单外的依赖
- 不在 api 层写业务逻辑
- 不在 domain 层做 IO
- 不把硬约束判断交给 LLM
```

## 八、待定问题（v0.2 已全部定稿）

| 问题         | 选项                 | **已定结论（v0.2）**                                  |
| ------------ | -------------------- | ----------------------------------------------------- |
| 规则热更新   | YAML 文件 vs DB      | **YAML 文件**（`data/rules/`），量大再迁 DB           |
| 会话存储     | PG JSONB vs Redis    | **PostgresSaver 为唯一事实源**，Redis 只做缓存与限流  |
| 前端 SSR/CSR | 全 SSR vs 混合       | **混合**：推荐 / 对话 / 购物清单 CSR，落地页 / 详情页 SSR |
| 评估触发     | 手动 vs CI           | **先手动**（`scripts/eval.py`），M2 稳定后再入 CI     |
| 语音         | Web Speech vs 第三方 | **Web Speech API**，零成本                            |

---

**一句话总结**：这是草案，不是宪法。分层单向依赖、规则用 YAML、硬约束在服务端、接口先行。每次迭代记日志，改必有因。
