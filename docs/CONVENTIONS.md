MealCompass 开发规范与参考资料

> **性质**：开发规范，约束团队成员与 AI Coding 工具的行为边界。
> **AI 工具入口**：所有 AI 编码工具请先读根目录 [`AGENTS.md`](../AGENTS.md)——里面有阅读顺序、收尾流程（自检 → 同步文档 → 提交）与汇报格式。
> **原则**：规则要可执行、可检查，不做无法验证的“正确废话”。
> **适用范围**：MealCompass 项目全部代码。

## 一、目录结构规范

### 1.1 后端分层（严格单向依赖）

```
backend/
  api/          # 路由层：只做参数校验 + 调用 service，不写业务逻辑
  services/     # 业务编排：事务边界，组合 domain + infra
  domain/       # 领域层：纯逻辑，无 IO，可单测
    ports.py    # 所有 Protocol 接口（RecipeRepository / Retriever / LLMClient）
    rules/      # 规则引擎
    profiles/   # 用户画像（口味、忌口、厨具、技能）
  agents/       # Agent 层：LangGraph 节点、工具、状态定义
  rag/          # RAG 层：检索、重排、切分、索引
  infra/        # 基础设施：DB、LLM 客户端、Redis、观测
  core/         # 配置、日志、异常、安全
  scripts/      # 一次性脚本（种子数据、建索引、评估）
  tests/        # 测试
```

**依赖方向**：`api → services → domain / agents / rag → infra`。`domain` 不依赖任何层。

**规则**：

- ✅ 按业务领域组织代码，不按文件类型组织
- ✅ 用户画像放 `domain/profiles/`，跨层接口 Protocol 放 `domain/ports.py`
- ❌ `api` 层不直接调 `infra`，必须经 `services`
- ❌ `domain` 层不做 IO（不导入 DB、HTTP 客户端）
- ❌ 同层模块不互相调用，通过 `services` 编排

### 1.2 前端目录

```
frontend/
  app/                  # Next.js App Router
    (auth)/             # 路由组：登录/注册
    (main)/             # 路由组：主功能
  components/
    ui/                 # shadcn/ui 组件（必须在此目录）
    recipe/             # 业务组件
  lib/
    api.ts              # API 客户端
    stores/             # Zustand
    hooks/              # TanStack Query hooks
```

**规则**：

- 使用 App Router，不使用 Pages Router
- 默认使用 React Server Components，仅在需要交互时加 `"use client"`
- shadcn/ui 组件统一放在 `components/ui/`
- 不使用 `src/` 前缀（`app/`、`components/`、`lib/` 直接放在 `frontend/` 下）

## 二、后端开发规范

### 2.1 Python 代码风格

- 4 空格缩进，禁止 Tab
- 行宽上限 120（Ruff 配置为准）
- 命名：模块 `snake_case`，类 `PascalCase`，常量 `UPPER_CASE`，私有 `_prefix`
- 导入顺序：标准库 → 第三方 → 本地，组间空行

### 2.2 类型注解（强制）

所有函数参数和返回值必须有类型注解：

```python
# ✅ 正确（Python 3.10+）
def get_user(user_id: str) -> User | None: ...
def process_items(items: list[str]) -> dict[str, int]: ...

# ❌ 禁止
def get_user(user_id): ...
```

- 使用 `X | None` 而非 `Optional[X]`（Python 3.10+）
- 使用 `list[str]` 而非 `List[str]`（Python 3.9+）

### 2.3 Pydantic v2

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator

class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # ORM 模型用
    user_id: str
    taste_preferences: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)

    @field_validator("taste_preferences")
    @classmethod
    def dedupe_preferences(cls, v: list[str]) -> list[str]: ...
```

**规则**：

- 使用 `model_dump()`，禁止 `.dict()`
- 使用 `field_validator` / `model_validator`（v2），禁止 v1 风格
- ORM 模型映射使用 `ConfigDict(from_attributes=True)`
- 避免 `Any`，使用具体类型

### 2.4 FastAPI 路由

```python
# ✅ 正确：路由薄，逻辑在 service
@router.post("/recommend")
async def recommend(
    req: RecommendRequest,
    service: RecommendService = Depends(get_recommend_service),
) -> RecommendResponse:
    return await service.recommend(req)

# ❌ 错误：在路由里写业务逻辑
@router.post("/recommend")
async def recommend(req: RecommendRequest):
    recipes = await db.execute(...)  # 禁止
    filtered = [r for r in recipes if ...]  # 禁止
```

**规则**：

- 路由函数不超过 10 行
- 依赖注入用 `Depends`，不手动 `new`
- 所有 IO 操作用 `async`

### 2.5 Ruff 配置

```toml
# pyproject.toml
[tool.ruff]
line-length = 120
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]
ignore = []
```

**提交前必须通过**：`ruff check . && ruff format --check .`

## 三、前端开发规范

### 3.1 TypeScript 严格模式

```json
// tsconfig.json
{
  "compilerOptions": {
    "strict": true,
    "noImplicitAny": true,
    "strictNullChecks": true,
    "noImplicitReturns": true
  }
}
```

**规则**：

- 禁止 `any`，用 `unknown` 或泛型替代
- 禁止 `// @ts-ignore`，必须解决类型错误
- 减少 `as` 断言，优先类型守卫
- `strictNullChecks` 是最有价值的选项，强制处理 null/undefined
- **落地方式（T1.17 实测）**：前两条由 `frontend/.eslintrc.json` 用 **ESLint 核心规则**强制——`no-restricted-syntax`（选择器 `TSAnyKeyword`）拦 `any`，`no-warning-comments`（terms `["@ts-ignore"]`）拦忽略指令。原因是 `eslint-config-next@14` 只加载 `@typescript-eslint/parser`、**不注册** `@typescript-eslint` 插件，写 `@typescript-eslint/*` 规则名会让 `pnpm lint` 对每个文件报 `Definition for rule ... was not found`；为这两条规则新增插件依赖也不划算。两条规则均已用探针文件实测会报错，不是静默失效。

### 3.2 Next.js App Router

| 文件            | 用途                          |
| --------------- | ----------------------------- |
| `layout.tsx`  | 布局（默认 Server Component） |
| `page.tsx`    | 页面                          |
| `loading.tsx` | 加载 UI                       |
| `error.tsx`   | 错误 UI                       |
| `route.ts`    | API 端点                      |

**规则**：

- 默认 Server Component，仅在需要 `useState`/`useEffect`/事件处理时加 `"use client"`
- 数据获取用 Server Component 的 `async/await`，客户端用 TanStack Query
- 不在 `layout.tsx` 中加 `"use client"`
- 渲染策略：推荐 / 对话 / 购物清单等交互页用客户端组件（CSR + TanStack Query）；落地页、菜谱详情、legal 用 Server Component（SSR）

### 3.3 shadcn/ui

- 组件统一放在 `components/ui/`
- shadcn/ui 主题变量必须映射到 `docs/UI_STYLE.md` 的 Natural Organic token，禁止保留默认 slate/zinc 冷色主题
- 使用语义化 variant，不直接改样式：`<Button variant="destructive">`
- 保留 Radix UI 的可访问性属性（`aria-*`、`role`）
- 使用 `cn()` 合并 className

### 3.4 状态管理

| 类型       | 工具                  | 场景                  |
| ---------- | --------------------- | --------------------- |
| 服务端状态 | TanStack Query        | API 数据、缓存、重取  |
| 客户端状态 | Zustand               | UI 状态、表单临时状态 |
| 表单状态   | React Hook Form + Zod | 表单校验              |

**规则**：服务端数据不放入 Zustand，Zustand 不存 API 响应缓存。

### 3.5 Tailwind v4（CSS-first）

- 设计 token 在 `app/globals.css` 用 `@theme` 定义，**不生成 `tailwind.config.js`**
- 颜色 / 圆角 / 字体一律走 token（见 `docs/UI_STYLE.md`），不写裸色值
- 禁止类：`bg-blue-*` / `bg-purple-*` / `bg-cyan-*` / `text-black` / `rounded-none` / `rounded-sm` / `shadow-lg|xl` / `bg-gradient-to-r`

## 四、AI / Agent 开发规范

### 4.1 LangGraph 状态设计

```python
from typing import Annotated
from langgraph.graph import StateGraph

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]  # reducer
    profile: UserProfile
    constraints: dict
    candidates: list[RecipeCandidate]
    selected: RecipeCandidate | None
```

**规则**：

- 使用 `TypedDict` 或 `Pydantic BaseModel` 定义状态
- 保持状态扁平，避免深层嵌套
- 累积型字段（消息、日志）必须定义 reducer
- 状态保持轻量，避免性能问题

### 4.2 持久化

```python
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver.from_conn_string(DATABASE_URL)
graph = builder.compile(checkpointer=checkpointer)
```

- **Checkpointer**：短期记忆，线程内状态快照
- **Store**：长期记忆，跨线程用户偏好
- `thread_id` 保持在 255 字符以内
- 生产环境使用 `PostgresSaver`，禁止 `MemorySaver`
- Redis 只做缓存与限流，**不作为会话状态的事实源**（事实源是 `PostgresSaver`）

### 4.3 RAG 规范

**检索管线**：

```
查询理解 → 混合检索（向量 + BM25）→ RRF 融合 → 重排 → Top 10 → 生成
```

**规则**：

- 硬约束下推到检索层（SQL `WHERE` / 向量过滤），不在检索后过滤
- 模型调用（Embedding / 重排）实行**远程优先、本地兜底**：默认走 OpenAI 兼容的远程接口，失败或离线时回落本地推理；调用方只依赖 `domain/ports.py` 的 Protocol，并在 trace metadata 里标注 provider 与是否降级
- ⚠️ **本地兜底必须与远程用同一个模型**：向量空间不一致时，库里存的远程向量和本地查询向量没法比，索引直接作废。因此不能图省事换小模型（何况 `bge-small-zh` 是 512 维，与 `vector(1024)` 对不上）。改模型 = 全量重建索引
- 本地模型缓存由 `infra/model_cache.py` 统一固定到 `<仓库>/.cache`（`HF_HOME` 与 `SENTENCE_TRANSFORMERS_HOME` **两个都要设**，只设一个会重复下载）
- 中文全文索引（`recipe_embeddings.tsv`）与 BM25（rank-bm25 + jieba）**共用 `rag/tokenization.py` 的同一分词**：tsv 由 jieba 词项空格拼接后 `to_tsvector('simple', ...)` 生成（官方 pgvector 镜像无 zhparser）。改分词 = 全量重建 tsv 与 BM25 语料，否则库里词项和检索词项不一致
- 生成必须引用 `recipe_id`，禁止编造知识库外内容
- 反思校验失败重试 ≤ 2 次，仍失败降级返回安全候选
- 温度参数设为 0.1 以减少幻觉

### 4.4 工具定义

```python
from langchain_core.tools import tool

@tool
async def search_recipes(query: str, filters: dict, top_k: int = 10) -> list[dict]:
    """根据查询和过滤条件检索菜谱。

    Args:
        query: 自然语言查询
        filters: 硬约束过滤条件
        top_k: 返回数量
    """
    ...
```

**规则**：

- 每个工具必须有 docstring（LLM 依赖它理解工具用途）
- 工具必须有超时和异常兜底
- 新增工具 = 新增文件 + 注册，不改主流程

### 4.5 可观测（Langfuse）

- **唯一出口** `infra/observability.py`；业务代码不得直接 `import langfuse`。
- **先加载 `.env`，再 import langfuse** —— 顺序错了 SDK 会用空凭证初始化（官方 Common Mistakes）。
- 未配置 key 时整体降级为 no-op，本地开发不被可观测性阻塞。
- 观察名是**稳定 API**（评估器、看板、过滤器都按名字匹配），只能取 `SpanName` 常量，禁止在调用点手写字符串：

| 常量 | 观察名 | 类型 |
| ---- | ------ | ---- |
| `RECOMMEND_REQUEST` | `recommend-request` | span（根；一个推荐请求 = 一个 trace） |
| `PARSE_INTENT` | `parse-intent` | **generation**（见下方 ⚠️） |
| `CLARIFY_REQUEST` | `clarify-request` | span（未接线） |
| `RETRIEVE_RECIPES` | `retrieve-recipes` | retriever |
| `RERANK_RECIPES` | `rerank-recipes` | span |
| `FILTER_HARD_CONSTRAINTS` | `apply-hard-constraints` | span |
| `GENERATE_RECOMMENDATIONS` | `generate-recommendations` | generation |
| `REFLECT_VALIDATE` | `reflect-validate` | span |
| `EVAL_RETRIEVAL` | `eval-retrieval` | span（离线评估） |
| `EVAL_FAITHFULNESS` | `eval-faithfulness` | span（离线评估，未接线） |
| `TOOL_*` | `tool-*` | tool |

> ⚠️ **`PARSE_INTENT` 的类型是 `generation`，不是本表原来写的 `span`。**
> 原因：本表第 312 行的硬规则「LLM 调用必须记为 `generation` 并带 `model` + `usage_details`」优先级更高，
> 而 `parse-intent` **确实是一次 LLM 调用**（把自然语言翻译成硬约束）。两条规则冲突时以硬规则为准。
> 真机已在 Langfuse 确认：`parse-intent` 为 GENERATION，带
> `model=deepseek-ai/DeepSeek-V3` 与 `usage_details={input_tokens:177, output_tokens:37, total:214}`。
>
> 决策记录：**观察名（命名契约）不变，只改类型**。类型是给看板分组用的，改名才会破坏已保存的过滤器；
> 类型改对反而让成本/Token 视图变得完整。历史 trace 里的类型不会追溯修改。

**已知的行为不一致（只登记，未修）**：`generate` 节点有**两套规则文案模板**，同为"没走成 LLM 润色"的理由，用户看到的文字却不同：

| 场景 | 代码位置 | 后缀 |
| --- | --- | --- |
| `recommendation_shortfall` 补齐的那条 | `agents/nodes.py:240-245` | **无**（`命中你的需求「{query}」的混合检索第 {rank} 名结果`） |
| `generate_fallback` 整段兜底 | `agents/nodes.py:336` | **有**（同模板 + 「（未启用 LLM 润色，由规则兜底生成）」） |

这是既有行为，`agents/` 冻结期**只登记不改**（会改变对外文案，属行为变更），已记录为 [`failed-features.md`](./failed-features.md) F19。


- 命名规则：**动词开头、低基数、不含动态值**；动态信息进 metadata。
- LLM 调用必须记为 `generation` 并带 `model` + `usage_details`，否则成本 / Token 视图为空。
- 根观察必须显式设置 input / output，且只放用户看得懂的内容（不要塞函数参数）。
- 每个 trace 带 `user_id` / `session_id` / `environment` / `tags`（用 `attributes()`）。
- 短生命周期进程（脚本、离线评估）结束前必须 `flush()`。
- ⚠️ **读取 trace 一律走 Observations API v2**（`client.api.observations.get_many`）。2026-09-16 之后创建的 Langfuse 组织访问旧 `/api/public/traces` 会返回 `410 LEGACY_API_UNAVAILABLE_FOR_NEW_ORGANIZATION`。
- 密钥、密码、完整用户身份、真实联系方式**绝不进 trace**；忌口/过敏原等敏感个人数据进 metadata 前先脱敏或只记数量

### 4.6 语料变更后的证据链纪律（2026-10-11 起）

> 起因：解析层噪声清理后重灌，`hybrid` 的 Recall@5 从 59.58% 变成 61.25%。**这不是 bug，是预期效应**——
> 卡片文档 = 菜名 + 简介 + **食材**，食材变了 embedding 就变了，检索排序必然变。
> 但中间偷懒一步，留下的就是一组**不可信的数字**。

**只要改动会影响「卡片文档」或「索引词项」**（解析器、`rag/chunking.py`、`rag/tokenization.py`、embedding 模型、词表），**必须**按顺序走完：

| 步骤 | 命令 / 动作 | 为什么不能省 |
| --- | --- | --- |
| 1. 留底 | 复制 `data/eval/reports/*.json` 与 `data/recipes/import_report.json` 到 `.tmp/<name>_before/`，**并把关键报告复制进 `docs/evidence/`（入库）** | 没有旧值就无法判断"变好还是变坏"；只放在 gitignore 的 `.tmp/` 里 = 下次 clone 的人无法对账 |
| 2. 重灌 | `python -m scripts.import_howtocook` → `python -m scripts.seed_recipes` | 幂等设计保证可重复跑 |
| 3. **重建索引** | `python -m scripts.build_index`（卡片 + 步骤两层） | **最容易漏的一步**：不重建则库里向量对应旧文本，指标会"看起来没变"却完全不可信 |
| 4. 校验标注 | `python -m scripts.eval --validate-only` → 必须 **40/40** | 若某条标注菜名消失，说明过滤过头了，**这是严重回归，必须回退那一条规则** |
| 5. 全量重跑 | `--mode all` + `--mode weight`（并检查 `provider_stats.degraded_calls == 0`） | 单组重跑无法比较；被降级污染的数字不可比，要丢弃重跑 |
| 6. 统一文档 | README / `docs/INTERVIEW.md` / `docs/DATA_SOURCES.md` / `docs/failed-features.md` / `TODO.md` **一次性全换** | **禁止新旧数字混用**——同一张表里混两组语料的数就是自相矛盾 |

**三条硬规矩**：

- **指标因数据变干净而变化是正常结果，不是回退的理由。** 要把"数据更干净"和"指标更好看"分开看。
- **负面结论必须留档，不许因为不好看就删。** 本项目最值钱的产出恰恰是「混合检索没有赢」这条实测负结论。
- **正文数字必须能追到 `docs/evidence/` 的某一行原始输出。** 追不到的数字不许写进 README / 面试材料；连"脚本自己出错导致的误报"也要留档（例：`e2e_run1_OLD_PROBE_field_bug.txt`）。目录说明见 [`evidence/README.md`](./evidence/README.md)。

## 五、数据库规范

### 5.1 表设计

- 主键统一 `UUID`
- 承载**上游原文**的字段（如 `servings_text`、`amount_text`、`description`）一律用 `TEXT`，不要用 `VARCHAR(n)`：长度不由我们拍板，实测有 257 字的原文
- 时间字段统一 `TIMESTAMP WITH TIME ZONE`
- JSON 字段用 `JSONB`（非 `JSON`）
- 向量维度固定 1024（BGE-M3）
- 食材归一化词典放 `data/ingredients/aliases.yaml`：只合并同一食材的不同叫法，**风味/品种不同的不合并**；别名不得跨条目重复（加载时会报错）；新增条目后重跑 `scripts/import_howtocook.py` 看 `import_report.json` 的 `unmapped_top`

### 5.2 pgvector 索引

```sql
-- HNSW 索引（推荐，对增量数据友好）
CREATE INDEX ON recipe_embeddings
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- 查询时调整搜索宽度
SET hnsw.ef_search = 100;
```

**规则**：

- 默认使用 HNSW，不用 IVFFlat
- `m = 16` 适合大多数场景
- `ef_search` 从 40 开始，需要更高召回调到 100-200
- 每个距离函数建独立索引

### 5.3 迁移

- 使用 Alembic 管理迁移
- 每次迁移必须可回滚
- 禁止手动改线上表结构

## 六、测试规范

### 6.1 测试结构

```
tests/
  unit/           # 纯逻辑测试（domain 层）
  integration/    # API + DB 集成
  e2e/            # 端到端
  conftest.py     # fixtures
```

### 6.2 FastAPI 测试模式

```python
# conftest.py
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

@pytest.fixture
def client():
    from main import app
    return TestClient(app)

# 异步端点用 httpx + pytest-asyncio
@pytest.fixture
async def async_client():
    from main import app
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
```

**规则**：

- 单元测试不碰真实 DB，用 SQLite in-memory 或 mock
- 使用 `dependency_overrides` 替换依赖
- 覆盖率 ≥ 70%
- 提交 PR 前必须全部通过

### 6.3 测试命令

```bash
uv run pytest --cov=. --cov-report=term-missing
uv run pytest tests/unit -x -q     # 快速跑单元测试
```

## 七、Git 与 CI 规范

### 7.1 分支策略

```
main          # 生产分支，只接受 PR
develop       # 开发分支
feature/xxx   # 功能分支
fix/xxx       # 修复分支
```

### 7.2 Commit 格式

```
<type>: <description>

feat: 新增忌口规则引擎
fix: 修复 pgvector HNSW 索引未命中问题
docs: 更新 API 接口文档
refactor: 将检索逻辑从 api 层移至 rag 层
test: 补充规则引擎单元测试
```

### 7.3 CI 流水线

```yaml
# .github/workflows/ci.yml
jobs:
  backend:
    steps:
      - ruff check .
      - ruff format --check .
      - pytest --cov=. --cov-fail-under=70
  frontend:
    steps:
      - pnpm typecheck
      - pnpm lint
      - pnpm build
```

> 离线评估（`scripts/eval.py`）在 MVP 阶段**不进入必跑 CI**；M2 评估集稳定后可加 nightly 任务。

## 八、环境与部署规范

### 8.1 Docker Compose 服务

```yaml
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    env_file: .env
  frontend:
    build: ./frontend
    ports: ["3000:3000"]
  postgres:
    image: pgvector/pgvector:pg16
    volumes: [pgdata:/var/lib/postgresql/data]
  redis:
    image: redis:7-alpine
```

**规则**：

- 前后端独立容器，各自 Dockerfile
- 环境变量通过 `.env` 注入，不硬编码
- 生产环境 Next.js 使用 `standalone` 输出模式
- `docker compose up -d` 默认只起 **postgres + redis**（当前阶段就靠这两个）；`backend` / `frontend` 挂在 `app` profile 下，用 `docker compose --profile app up -d` 启用
- 建表走 Alembic：`cd backend && .venv\Scripts\python.exe -m alembic upgrade head`；**schema 的唯一事实源是 `backend/infra/tables.py`**，改表必须同时改迁移并跑 `test_schema_metadata.py` 的漂移检查
- `alembic.ini` 必须保持纯 ASCII：alembic 用系统 locale 编码读它（zh-CN Windows 是 GBK），中文注释会让它直接崩

### 8.2 环境变量

| 变量                    | 必需 | 说明              |
| ----------------------- | ---- | ----------------- |
| `DATABASE_URL`        | ✅   | PostgreSQL 连接串 |
| `REDIS_URL`           | ✅   | Redis 连接串      |
| `LLM_API_KEY`         | ✅   | LLM API Key       |
| `LLM_BASE_URL`        | ✅   | 兼容接口地址      |
| `LLM_MODEL`           | ✅   | 模型名（deepseek-chat） |
| `EMBEDDING_MODEL`     | ✅   | BAAI/bge-m3       |
| `RERANKER_MODEL`      | ✅   | bge-reranker-v2-m3 |
| `JWT_SECRET`          | ✅   | JWT 密钥          |
| `LANGFUSE_PUBLIC_KEY` | ✅   | 可观测（可留空，留空即降级为本地日志） |
| `LANGFUSE_SECRET_KEY` | ✅   | 可观测（可留空，留空即降级为本地日志） |
| `LANGFUSE_BASE_URL`    | ✅   | JP: https://jp.cloud.langfuse.com |
| `LANGFUSE_TRACING_ENVIRONMENT` | ✅ | dev / staging / production |
| `SENTRY_DSN`          | P1   | 异常上报（可留空） |

## 九、参考资料

### 9.1 官方文档

| 技术                   | 链接                             | 重点章节                                         |
| ---------------------- | -------------------------------- | ------------------------------------------------ |
| **FastAPI**      | fastapi.tiangolo.com             | Tutorial, Dependencies, Testing                  |
| **Pydantic v2**  | docs.pydantic.dev                | Models, Validators, Settings                     |
| **LangGraph**    | langchain-ai.github.io/langgraph | State, Persistence, Graph API                    |
| **LangChain**    | python.langchain.com             | RAG, Retrieval, Tools                            |
| **Next.js 14**   | nextjs.org/docs/14               | App Router, Server Components, Project Structure |
| **TypeScript**   | typescriptlang.org/docs          | Strict Mode, Type Narrowing                      |
| **pgvector**     | github.com/pgvector/pgvector     | Indexing, HNSW, Performance                      |
| **RAGAS**        | docs.ragas.io                    | Metrics, Evaluation                              |
| **Langfuse**     | langfuse.com/docs                | Tracing, Evaluation                              |
| **shadcn/ui**    | ui.shadcn.com                    | Components, Theming, CLI                         |
| **Ruff**         | docs.astral.sh/ruff              | Configuration, Rules                             |
| **Tailwind CSS** | tailwindcss.com/docs             | Utility Classes, Responsive                      |

### 9.2 必读文章

| 主题                | 来源             | 核心收获                                               |
| ------------------- | ---------------- | ------------------------------------------------------ |
| FastAPI 项目结构    | Sourcetrail 指南 | 按功能组织 vs 按文件类型组织                           |
| TypeScript 严格模式 | Steve Kinney     | `strictNullChecks` 是 React 项目最高价值选项         |
| LangGraph 状态设计  | LangGraph 官方   | 状态保持扁平、用 reducer 管理累积字段                  |
| pgvector 索引选择   | Microsoft Learn  | HNSW vs IVFFlat 的取舍，参数调优                       |
| RAG 评估            | RAGAS 相关论文   | 检索和生成分开评估，Context Recall > 0.8               |
| Pydantic v2 迁移    | GitHub 风格指南  | `model_dump()` 替代 `.dict()`，`ConfigDict` 配置 |
| shadcn/ui 规范      | 社区最佳实践     | 组件放`components/ui/`，保留 Radix 可访问性          |

### 9.3 AI 编码约束（写入 `.cursorrules`）

```
# 代码风格
- Python: 4空格缩进, 行宽120, 类型注解必须完整, PEP 8
- TypeScript: strict: true, 禁止 any, 禁止 @ts-ignore

# 架构
- 分层: api → services → domain/agents/rag → infra (单向)
- 用户画像放 domain/profiles/，接口 Protocol 放 domain/ports.py
- domain 层不做 IO, api 层不写业务逻辑
- shadcn/ui 组件必须放在 components/ui/（项目不用 src/ 前缀）

# 数据
- Pydantic v2: model_dump() 不用 .dict(), ConfigDict 配置
- UUID 主键, JSONB 字段, 向量维度 1024
- pgvector: HNSW 索引 (m=16, ef_construction=64)

# Agent
- State 用 TypedDict, 保持扁平, 累积字段用 reducer
- 生产环境用 PostgresSaver, 禁止 MemorySaver
- 工具必须有 docstring 和异常兜底

# RAG
- 硬约束下推到检索层, 不在检索后过滤
- 生成必须引用 recipe_id, 温度 0.1
- 反思重试 ≤ 2 次

# 测试
- 单元测试不碰真实 DB, 覆盖率 ≥ 70%
- 提交前必须通过 ruff check + pytest
```

## 十、规范迭代日志

| 版本 | 日期       | 变更     | 原因             |
| ---- | ---------- | -------- | ---------------- |
| v1.0 | 2026-10-06 | 初始版本 | 建立开发规范基线 |
| v1.1 | 2026-10-06 | 统一跨文档冲突；补充渲染策略、Tailwind v4、会话存储、环境变量清单 | 与 README、ARCHITECTURE、TECH_STACK 对齐，消除歧义 |
| v1.2 | 2026-10-06 | 指向 `AGENTS.md` 作为 AI 入口；配图入库约定 | 让 AI 工具的阅读顺序与收尾流程有唯一出处 |
| v1.3 | 2026-10-06 | 补充食材归一化词典的存放位置与维护规则 | T1.3 落地，避免词表散落在代码里 |
| v1.4 | 2026-10-06 | 补 Docker Compose（profile 用法）与 Alembic 建表流程；`alembic.ini` 必须 ASCII | T0.8/T0.9 落地 |
| v1.5 | 2026-10-06 | 补「上游原文字段一律用 TEXT」的规则 | 实机入库踩到 VARCHAR(160) 溢出 |
| v1.6 | 2026-10-07 | 新增「本地兜底必须同模型」「两个缓存变量都要设」两条规则 | 兜底的正确性前提，踩过重复下载 |
| v1.7 | 2026-10-07 | 新增「tsv 与 BM25 共用同一 jieba 分词」规则 | T1.6 落地，避免库里词项与检索词项不一致 |
| v1.8 | 2026-10-09 | §3.1 补「禁 `any` / 禁 `@ts-ignore`」的落地方式（ESLint 核心规则，不用 `@typescript-eslint/*`） | T1.17 实测：`eslint-config-next@14` 不注册该插件，写其规则名会让 lint 全线报错 |
| v1.9 | 2026-10-11 | 新增 §4.6「语料变更后的证据链纪律」：任何改变卡片文档/索引的重灌，必须走「留底 → 重灌 → **重建索引** → 校验标注 → 全量重跑 → 一次性统一所有文档数字」；禁止新旧数字混用 | 解析层噪声清理后重灌，`hybrid` R@5 从 59.58% 变成 61.25%——不是 bug 而是卡片文本变了的预期效应；若不重建索引，向量与文本会对不上，指标会"看起来没变"却完全不可信 |
| v1.10 | 2026-10-11 | §4.5 观察名表维持 v1.7 口径；补记「规则生成的推荐理由有两套模板」这一已知不一致（`shortfall` 补齐 vs `generate_fallback`），登记为 `failed-features.md` F19 | 同为规则文案却一个带后缀一个不带，属行为变更，冻结期只登记不改 |
| v1.11 | 2026-10-11 | §4.6 第 1 步强化：留底不能只放 `.tmp/`（gitignore），**关键报告要复制进 `docs/evidence/`（入库）**，并升级为「三条硬规矩」（新增：正文数字必须能追到 `docs/evidence/` 的原始输出）；新增规矩「端到端脚本不得写死响应字段」「含 LLM 往返的指标默认多次运行给区间」 | 两件事都是真实踩到的：① 探针写死读 `results`（真实字段是 `candidates`），把 5 条候选报成 0 条、差点当成新负结论；② 同代码同语料三轮跑出 12.0/10.4/9.2 s，给单一精确值等于隐藏方差 |

**迭代规则**：

1. 每次规范变更在此登记
2. 记录变更内容和原因
3. 破坏性变更需标注影响范围
4. 规范允许推翻，但需说明新方案优于旧方案的理由

---

**一句话总结**：类型注解全覆盖、分层单向依赖、Pydantic v2 用新 API、HNSW 索引、LangGraph 状态扁平、测试覆盖率 70%、提交前 Ruff + pytest 通过。规范要可执行，不做无法验证的“正确废话”。
