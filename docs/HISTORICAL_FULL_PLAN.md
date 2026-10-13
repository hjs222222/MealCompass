# MealCompass 历史全量计划归档

> 归档日期：2026-10-13
>
> 本文件保留三周聚焦前的 4–6 周完整产品设想、技术决策和旧验收标准，供未来重新立项时追溯。
> 它**不属于当前待办，也不参与项目完成度统计**。当前唯一执行计划见仓库根目录 [`TODO.md`](../TODO.md)。

---

## 1. 完整产品扩展的已定决策（非当前待办）

| #   | 议题           | 结论                                                                                                              | 落点                                 |

> 本节记录未来恢复完整产品范围时应遵循的设计决策；它们不是三周交付已实现功能。当前已实现范围以 `README.md` 的「当前实现状态」为准。

| --- | -------------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| D1  | 规则热更新     | **YAML 文件**（`data/rules/`），量大再迁 DB                                                               | ARCHITECTURE §8                     |
| D2  | 会话存储       | **`PostgresSaver` 为唯一事实源**，Redis 只做缓存与限流                                                    | CONVENTIONS §4.2                    |
| D3  | 前端渲染       | 推荐 / 对话 / 购物清单**CSR**；落地页 / 菜谱详情 / legal **SSR**                                      | CONVENTIONS §3.2                    |
| D4  | 评估触发       | **先手动**（`scripts/eval.py`）；当前三周范围内不进入必跑 CI，未来扩展时再决定是否加入定时任务             | CONVENTIONS §7.3                    |
| D5  | 语音           | **Web Speech API**（客户端，零成本）                                                                        | PRD F-E3                             |
| D6  | 目标用户       | **取消医学人群细分，面向所有普通人**（2026-10-06 决策）。约束只来自用户自己的忌口、可用时间、可用厨具与口味 | PRD §1.3 / §2 / 模块 D             |
| D7  | 登录方式       | **邮箱 + 密码 + JWT**，不做第三方 OAuth                                                                     | PRD §1.5 / F-A1                     |
| D8  | 画像归属       | **`backend/domain/profiles/`**（domain 是唯一无 IO 层）                                                   | TECH_STACK §2.2                     |
| D9  | 前端目录       | **不用 `src/`**：`app/`、`components/ui/`、`lib/`                                                   | CONVENTIONS §1.2 / §3.3            |
| D10 | 文档命名与路径 | 规范名迁到`docs/`，README 在根目录                                                                              | README 文档索引                      |
| D11 | 接口位置       | 所有 Protocol 集中**`domain/ports.py`**，实现在 `infra/`、`rag/`                                            | ARCHITECTURE §5                     |
| D12 | 工期           | **历史全量计划**为 4-6 周；实际执行为 W1–W3 三周核心 Agent 闭环，现已完成                                   | README 路线图 / PRD §9              |
| D13 | 可观测优先级   | Langfuse + Sentry 属**MVP**，未配置 key 时**自动降级为本地日志**                                      | CONVENTIONS §8.2 / TECH_STACK §2.6 |

- [X] **D14 菜谱数据来源与许可**：已定 —— **HowToCook**，License 为 **Unlicense（公有领域）**，可自由复制/修改/分发/商用，合规无风险。仓库已收录到 `data/raw/howtocook/`（372 道菜 + tips，Markdown 格式）
- [X] **D15 `reference/` 用途**：已定 —— 存放参考资料，**目前尚未开始收集**（目录已可写）
- [X] **D16 营养数据缺口**：已定 —— **放弃人群细分**。HowToCook 只提供预估热量与难度，没有蛋白质/GI/钠，不足以支撑医学约束；改为只展示热量、把「少油少盐低卡」降级为软偏好（PRD 模块 D、F-D4）
- [X] **D17 远程优先 / 本地兜底**：已定（**模型线**）—— Embedding（BGE-M3）与重排（bge-reranker-v2-m3）默认走 SiliconFlow / DeepSeek 等 OpenAI 兼容接口；本地兜底用 Ollama / sentence-transformers；两者都由 `domain/ports.py` 的 Protocol 约束，trace 标注 provider 与降级
  - 供应商与模型已实测确定（2026-10-07）：SiliconFlow `https://api.siliconflow.cn/v1`，embedding `BAAI/bge-m3`（1024 维）、rerank `BAAI/bge-reranker-v2-m3`、chat `deepseek-ai/DeepSeek-V3`；key 已写入 `.env`（不入库）
- [X] **D18 配图策略**：已定 —— **配图随仓库直接提交、保留原图**（108.7 MB，共 354 张），理由是网页端要展示成品图、原图观感更好；`.gitattributes` 已按二进制处理

---

## 2. 历史：开工前准备（不属于当前三周计划）

- [X] **P1 申请 LLM API Key**：DeepSeek（或任何 OpenAI 兼容），确定 `LLM_BASE_URL` / `LLM_MODEL`（`README.md` 环境变量表）
- [X] **P2 确定 Langfuse 形态**：自托管（docker）还是 Cloud，拿到 public/secret key（未配置也能开发，只是降级为本地日志）
- [X] **P3 确认机器资源**：bge-reranker-v2-m3 内存需求 ≥ 8GB；有 GPU 更好
- [X] **P4 解决模型下载**：BGE-M3 + reranker 走 ModelScope 镜像或 Ollama（TECH_STACK §6 避坑）
- [X] **P5 菜谱数据**：HowToCook 已在本地（373 道菜，Markdown），License = **Unlicense（公有领域）**；按 D16 只取预估热量，不做营养推断
- [ ] ~~**P6 部署账号**：Vercel（前端）+ 云服务器（后端）+ 域名/HTTPS（PRD F-H5、§7）~~ → 已从三周范围移出；如恢复产品化交付，作为独立部署任务重新立项。

---

## 3. 历史全量计划：P0 仓库与工程基线（0.5-1 周）

> ⚠️ 以下 §3-§7 是**原 4-6 周全量计划的历史清单**，保留用于追溯任务编号、取舍和决策；它们不是当前看板。
> **当前执行口径只有 §0.5**；本清单里的 `[ ]` 只表示当时的全量规划未交付，绝不表示三周计划遗漏或当前应继续执行。

- [X] ~~**T0.1 建目录骨架**~~（部分完成：`docs/` 已建，`backend/` `frontend/` `data/` 待建）
- [X] **T0.2 文档落地并改名**：已完成 —— `docs/{PRD,TECH_STACK,ARCHITECTURE,CONVENTIONS,UI_STYLE}.md` + 根 `README.md`
- [X] **T0.2b 删除旧目录 `goal/`**：已完成（已确认目录不存在）
- [ ] **T0.3 补齐仓库根文件**：`LICENSE`(MIT)、`.gitignore`（含 `.idea/`）、`.env.example`（`README.md` 环境变量表全量）
- [X] **T0.3a 密钥防泄漏**：`.gitignore`（含 `.env`、`langfuse.txt`、`.idea/`、`HowToCook/`）+ `.env`（真实密钥，已忽略）+ `.env.example` —— 已完成
- [X] **T0.12 Langfuse 可观测接入**：`backend/core/config.py`、`backend/infra/observability.py`、`backend/scripts/trace_smoke.py`；已真实发送并**在 API 侧核验通过**（Observations API v2 读回 6 条观察）
- [X] **T0.13 `AGENTS.md`**：所有 AI 工具的入口约束（阅读顺序 / 边界 / 收尾流程 / 汇报格式），已落地并被本会话加载
- [ ] **T0.4 写 `.cursorrules`**：合并 `TECH_STACK §4`、`ARCHITECTURE §7`、`CONVENTIONS §9.3` 三份约束
- [ ] **T0.5 后端工具链**：`pyproject.toml`（ruff `line-length=120`、`target py311`、`select=["E","F","I","UP","B","SIM"]`；pytest + coverage ≥ 70%）、`uv` 初始化
- [ ] **T0.6 前端工具链**：`package.json`、`tsconfig.json`（strict）、Tailwind v4（CSS-first `@theme`，**不产 `tailwind.config.js`**）、`npx shadcn@latest init`
- [ ] **T0.7 设计系统 token 落地**：把 `docs/UI_STYLE.md` 的自然有机风写进 `frontend/app/globals.css` 的 `@theme`（米色 `#faf6f1`、石棕 `#5c4033`、鼠尾草绿 `#8b9d77`、暖褐 `#d4a373`、`font-serif` 标题、`rounded-[2rem]` 卡片）
- [X] **T0.8 `docker-compose.yml`**：postgres（`pgvector/pgvector:pg16`）+ redis（`redis:7-alpine`）默认启动，均带 healthcheck；backend / frontend 挂 `app` profile。⚠️ **本机未装 Docker，尚未实机验证**（只做了静态检查）
- [X] **T0.9 数据库迁移**：Alembic `0001_initial_schema`（13 张表 / 13 个索引，含 HNSW + GIN + vector 扩展），`downgrade` 可回滚；DSN 从 `.env` 读，`alembic.ini` 保持纯 ASCII。**离线渲染 DDL 已验证**（6.5 KB SQL），但未连真实库执行（本机无 Docker）
- [ ] **T0.10 CI**：`.github/workflows/ci.yml` → 后端 `ruff check . && ruff format --check . && pytest --cov=. --cov-fail-under=70`；前端 `pnpm typecheck && pnpm lint && pnpm build`
- [ ] **T0.11 Git 流程**：`main`（只收 PR）/ `develop` / `feature/xxx` / `fix/xxx`；commit 用 `<type>: <description>`

---

## 4. 历史全量计划：M1 知识库 + 基础 RAG + 前后端骨架（1-1.5 周）

来源：`docs/PRD.md` 模块 B/E、`docs/ARCHITECTURE.md` §3、`docs/TECH_STACK.md` §2.1/2.3

### 4.1 数据层

- [X] **T1.1 建核心表**：12 张业务表已定义在 `backend/infra/tables.py` 并由 Alembic 落库（users / user_profiles / recipes / recipe_steps / ingredients / ingredient_aliases / recipe_ingredients / recipe_embeddings / conversations / messages / feedbacks / shopping_lists）
- [X] **T1.1b 数据入库脚本**：`scripts/seed_recipes.py`，**已对真实库跑通且幂等**（连跑两次数字一致）。**2026-10-11 解析层噪声清理后重灌的当前数字**：recipes 372 / recipe_ingredients **3697** / recipe_steps 3806 / ingredients 115 / ingredient_aliases 294（清理前为 3902 / 3806 / 115 / 294）
- [X] **T0.9 实机验证**：Docker 起来后 `alembic upgrade head` 真跑通（PostgreSQL 16.15 + pgvector 0.8.7，13 表 / 33 索引）；另补迁移 `0002` 放宽两个原文字段
- [X] **T1.2 HowToCook → JSON 入库脚本**：`scripts/import_howtocook.py`，372/372 解析成功、34→38 个单测全绿。三种用量语法（`名称 400 g` / `名称 = 2 斤` / `名称 15g*份数`）已覆盖；86 条上游没给数字的用量按「不编造」留原文
- [X] **T1.2b 菜谱模型加 images 字段**：`Recipe.images`（数据集内相对路径，346 张，0 缺失）+ `Recipe.external_images`（2 条外链）；含括号文件名（`石凉粉(冰粉)成品1.jpg`）已正确处理
- [X] **T1.3 食材归一化**：`data/ingredients/aliases.yaml`（115 个标准食材 / 294 个别名）+ `domain/ingredients.py`（纯逻辑）+ `infra/ingredient_dict.py`（加载）。`Ingredient` 落 `canonical` / `category`。**2026-10-11 解析层噪声清理后**：命中率 **75.3%**（2784/3697 条），未收录 **748** 种进 `import_report.json` 的 `unmapped_top`（清理前为 73.5%、2867/3902、856 种）。**词表未新增任何词**——提升全部来自「不再把说明文字当食材」
- [ ] **T1.3b 词表扩充** `[P1]`：按 `unmapped_top` 频次继续补（当前头部是冷门香料与地方食材，长尾收益递减）
- [X] **T1.4 热量字段处理** `[MVP]`：缺失即标注「未知」，**不可编造**；不做蛋白质 / GI / 钠推断
- [X] **T1.5 索引** `[MVP]`：HNSW(`m=16, ef_construction=64`) + `gin(tsv)` + `recipes(time_minutes)` + `gin(tags)`

### 4.2 RAG

- [X] **T1.6 双层切分** `[MVP]`：卡片级 + 步骤级分别索引；单条上下文 ≤ 模型窗口 60%（PRD F-B2）。落地：`rag/chunking.py`（卡片=菜名+简介+食材 / 步骤=原文）+ `scripts/build_index.py`；372 卡片 + 3806 步骤全量向量（1024 维）与 tsv 入库，SiliconFlow 远程批量
- [X] **T1.7 Embedding / Rerank 双通道**：`domain/ports.py`（Protocol）+ `infra/embedding_client.py` / `infra/rerank_client.py`（Remote SiliconFlow / Local sentence-transformers / Fallback）。**真连 SiliconFlow 验证**：`BAAI/bge-m3` 输出 1024 维、`bge-reranker-v2-m3` 把「西红柿炒鸡蛋」排在「红烧肉」之前；104 个单测 + 3 个真实集成测试通过
  - 本地兜底已用**真模型**验证（T1.8 之前的空白补上）：本地/远程向量余弦 **0.9999**，降级后 `provider=local` 且向量仍是 1024 维；一键自查 `python -m scripts.check_model_clients`
- [X] **T1.8 混合检索** `[MVP]`：向量 Top50 + BM25(rank-bm25 + jieba) Top50 → RRF → Top10（PRD F-B3）。落地：`rag/retriever.py`（HybridRetriever，实现 `Retriever` Protocol）+ `rag/corpus.py`（CardCorpus，与向量共用同一卡片文档）；真实冒烟 3 查询 Top10 语义合理；`scripts/smoke_retrieval.py` 可复跑
- [X] **T1.9 重排** `[MVP]`：bge-reranker-v2-m3，Top10 延迟 ≤ 500ms（PRD F-B4）。落地：`rag/reranker.py`（`rerank_candidates`，失败降级回 RRF 顺序并标记 degraded）+ `HybridRetriever` 可选 `reranker` 参数；真远程冒烟稳态 342–438ms 达标
- [X] **T1.10 硬约束下推** `[MVP]`：时间/厨具/忌口下推到 SQL WHERE 或向量过滤，**禁止检索后再过滤**（PRD F-B5）。已构造独立 SQL 允许 ID 集合，向量与 BM25 各自在允许集合内召回；未知耗时在设置时间上限时严格排除
- [X] **T1.11 引用与防幻觉** `[MVP]`：每条推荐附真实 `recipe_id`；引用准确率 ≥ 95%（PRD F-B6）。已新增 `Recommendation` 与纯领域引用校验：候选 ID/权威名称必须精确匹配，拒绝未知、重复或冲突引用
- [X] **T1.12 建索引脚本** `[MVP]`：`scripts/build_index.py`（幂等可重跑；`--layer card|step|all` / `--limit` 支持；含向量维度断言与 tsv 写入）
- [X] **T1.13 接口先行** `[MVP]`：在 `domain/ports.py` 定义 `RecipeRepository` / `Retriever` / `LLMClient`。`RecipeRepository` 与 `LLMClient` 已采用 async Protocol；另有 `EmbeddingClient` / `RerankClient`

### 4.3 前后端骨架

- [X] **T1.14 FastAPI 入口与分层** `[MVP]`：`main.py` + `api/v1/*` 薄路由 + `api/deps.py`
- [X] **T1.15 配置外置** `[MVP]`：`core/config.py` 用 pydantic-settings 读 `.env`，dev/prod 分离
- [X] **T1.16 异常/日志** `[MVP]`：`core/exceptions.py`、`core/logging.py` 结构化日志
- [X] **T1.17 前端骨架** `[MVP]`：`frontend/` 落地（Next.js 14 App Router，不带 `src/`）。路由组 `(auth)/login` + `(main)/dashboard`，另有 `/`、`loading.tsx`、`error.tsx`；`app/layout.tsx` 保持 Server Component，`components/providers.tsx` 是唯一客户端边界；Natural Organic token 写在 `app/globals.css` 的 `@theme`（不生成 `tailwind.config.js`）。**`pnpm typecheck && pnpm lint && pnpm build` 三项 exit 0**，4 条路由全部预渲染；`pnpm start` 后 `/`、`/dashboard`、`/login` 实测 HTTP 200
- [X] **T1.18 前端数据层** `[MVP]`：`lib/api.ts`（`fetchHealth` / `fetchVersion` + `ApiError`，字段用类型守卫校验、8s 超时、错误消息不泄露响应体）、`lib/query-client.ts`、`lib/hooks/use-system-status.ts`（TanStack Query）、`lib/stores/ui.ts`（Zustand 只存 UI 状态）、`components/status-panel.tsx`（加载 / 错误 / 重试 / 紧凑模式）。**已真启动 FastAPI 验证契约**：`/health`、`/version` 字段与类型逐项一致；`api.ts` 编译产物对真实后端跑通「正常 / 网络不可达 / 非 2xx」三条路径
- [ ] **T1.17b 前端自动化测试基线** `[P1]`：已有 4 项状态序列化纯函数测试；`lib/api.ts` 其他守卫、`StatusPanel` 分支与浏览器点击流仍缺自动化覆盖。**前置：先定组件/浏览器测试框架选型**（`TECH_STACK` 未列此类框架）。详见 `docs/failed-features.md` F5/F6

### 4.4 历史 M1 验收（已被三周实际证据替代）

- [X] **A1.1 历史目标已废止**：Recall@5 ≥ 85% 没有测量依据，不能作为交付门槛。三周实际交付改为 40 条评估集与三组消融；纯向量 Recall@5 实测 63.75%，差距与局限已如实记录。
- [X] **A1.2 历史目标已废止**：重排 nDCG@5 +10% 并非实测支持的结论。当前证据显示重排只在 Recall@10 有确定收益，头部 nDCG 未改善。

---

## 5. 历史全量计划：M2 规则引擎 + LangGraph Agent + 评估集（1.5-2 周）

来源：`docs/PRD.md` 模块 C/D、`docs/CONVENTIONS.md` §4、`docs/ARCHITECTURE.md` §2

### 5.1 规则引擎（domain 层，纯逻辑、零 IO）

- [ ] **T2.1 `Rule` Protocol + 注册表** `[MVP]`：`domain/rules/{base,registry}.py`
- [ ] **T2.2 规则 YAML 化** `[MVP]`：`data/rules/*.yaml`（hard_constraints 过滤 / soft_preferences 降权）
- [ ] **T2.3 规则实现** `[MVP]`：allergen / time_limit / tools（硬）+ taste（软）
- [ ] **T2.4 规则优先级** `[MVP]`：冲突时 忌口/过敏 > 时间与厨具 > 口味偏好（PRD §4.4）
- [ ] **T2.5 无解放宽** `[MVP]`：硬约束无解 → 返回「无匹配 + 放宽建议」，**绝不返回违规菜谱**
- [ ] **T2.6 规则单测** `[MVP]`：每条规则覆盖正反用例，覆盖率 ≥ 70%
- [ ] **T2.7 新增约束零代码** `[MVP]`：加 1 条 rules YAML 即可

### 5.2 通用约束集（无人群细分）

- [ ] **T2.8 忌口/过敏硬过滤** `[MVP]`：食材级，含同义词命中（PRD F-D1）
- [ ] **T2.9 时间与厨具过滤** `[MVP]`：下推到检索层（PRD F-D2）
- [ ] **T2.10 口味软偏好** `[MVP]`：辣度/清淡/菜系，YAML 可配（PRD F-D3）
- [ ] **T2.11 热量展示与轻负担偏好** `[P1]`：展示 HowToCook 预估热量，不做数值门槛（PRD F-D4）
- [ ] **T2.12 规则集与路由** `[MVP]`：规则集加载失败回落默认并告警（PRD F-D5）
- [ ] **T2.13 画像驱动的规则集选择** `[MVP]`：错误率 ≤ 5%（PRD F-D5）
- [ ] **T2.14 画像 CRUD** `[MVP]`：引导可跳过（默认 general）、编辑立即生效（PRD F-A2）
- [ ] **T2.15 注册/登录** `[MVP]`：**邮箱 + 密码 + JWT**（注册/登录/登出/刷新）、bcrypt、多用户数据隔离（PRD F-A1）

### 5.3 LangGraph Agent

- [ ] **T2.16 State 定义** `[MVP]`：TypedDict、扁平、累积字段用 reducer（CONVENTIONS §4.1）
- [ ] **T2.17 七个节点** `[MVP]`：parse → clarify → search → filter → rank → reflect → output（PRD F-C6）
- [ ] **T2.18 条件边** `[MVP]`：信息不足→澄清；检索为空→放宽；校验失败→重试
- [ ] **T2.19 持久化** `[MVP]`：`PostgresSaver`，`thread_id` ≤ 255 字符，禁 `MemorySaver`
- [ ] **T2.20 查询理解** `[MVP]`：Pydantic schema 校验，失败重试 ≤ 2 次，抽取准确率 ≥ 90%（PRD F-C1）
- [ ] **T2.35 Embedding/Rerank 双通道** `[MVP]`：远程优先（SiliconFlow/DeepSeek OpenAI 兼容）+ 本地兜底（Ollama/sentence-transformers），trace 标注 provider 与降级（D17）
- [ ] **T2.21 澄清追问** `[MVP]`：缺关键约束才追问，≤ 2 轮，可跳过（PRD F-C2）
- [ ] **T2.22 推荐生成** `[MVP]`：固定 3 道，含理由/缺失食材/替代/耗时，JSON 可直接渲染（PRD F-C3）
- [ ] **T2.23 反思校验** `[MVP]`：过敏原/时间/厨具/热量四类；重试 ≤ 2 次后降级（PRD F-C4）
- [ ] **T2.24 工具注册表** `[MVP]`：5 个工具 + docstring + 超时兜底，新增工具 = 新文件 + 注册（CONVENTIONS §4.4）
- [ ] **T2.25 温度与引用** `[MVP]`：温度 0.1，强制引用 `recipe_id`
- [ ] **T2.26 多轮对话** `[P1]`：上下文 ≥ 10 轮、指代消解（PRD F-C7）

### 5.4 菜谱与反馈

- [ ] **T2.27 菜谱详情 + 份量缩放** `[MVP]`：1-8 人，服务端二次校验（PRD F-E1）
- [ ] **T2.28 食材替代** `[MVP]`：≥ 30 组，标注口味/口感影响（PRD F-E2）
- [ ] **T2.29 反馈四类** `[MVP]`：点赞/踩/收藏/做过，写入记忆（PRD F-G1）
- [ ] **T2.30 历史记录** `[MVP]`：推荐 + 烹饪历史、短期不重复推荐（PRD F-G2）

### 5.5 评估体系

- [ ] **T2.31 标注评估集** `[MVP]`：100 条（PRD §8）
- [ ] **T2.32 评估脚本** `[MVP]`：`scripts/eval.py`，Recall / nDCG / 约束满足 + 同步 Langfuse
- [ ] **T2.33 RAGAS** `[MVP]`：Faithfulness / Answer Relevancy / Context Precision / Context Recall
- [ ] **T2.34 消融实验** `[MVP]`：纯向量 / 混合 / +重排 / +反思 四组，结果写 README 与简历

---

## 6. 历史全量计划：M3 购物清单 / 烹饪模式 / 部署 / 可观测（1-1.5 周）

来源：`docs/PRD.md` 模块 F/G/H

- [ ] **T3.1 购物清单** `[MVP]`：合并、按超市分区、勾选/删除/导出、单位统一（PRD F-F1）
- [ ] **T3.2 烹饪指导模式** `[P1]`：大字分步 + 计时器 + Web Speech + Wake Lock（PRD F-E3）
- [ ] **T3.3 一周菜单** `[P1]`：7 天 ±15%、食材复用率 ≥ 40%（PRD F-F2）
- [ ] **T3.4 食材库存** `[P1]`：录入、临期优先（PRD F-F3）
- [ ] **T3.5 限流与成本** `[MVP]`：20 次/小时、Redis 缓存、超时降级、单次 ≤ ¥0.05（PRD F-H4）
- [ ] **T3.6 可观测** `[MVP]`：Langfuse 链路 + Sentry + 结构化日志（**key 缺失时优雅降级**）（PRD F-H3）
- [ ] **T3.7 部署** `[MVP]`：Docker Compose 一键起、Vercel + 云服务器（PRD F-H5）
- [ ] **T3.8 合规** `[MVP]`：免责声明、隐私政策、数据导出/删除、来源标注（PRD F-H6）
- [ ] **T3.9 页面清单全部落地** `[MVP]`：`/` `/login` `/register` `/onboarding` `/recommend` `/chat` `/recipe/[id]` `/shopping` `/history` `/profile` `/legal`（PRD §5）
- [ ] **T3.10 评估看板** `[P1]`（PRD F-G3）
- [ ] **T3.11 长期记忆** `[P1]`（PRD F-A3）
- [ ] **T3.12 图片识别 / T3.13 成本估算 / T3.14 A/B 实验** `[P2]` → 写入 README「未来工作」

---

## 7. 历史全量计划：M4 交付打磨（0.5-1 周）

- [ ] **T4.1 README 定稿**：启动命令、架构图、消融结果、Demo 视频、指标表
- [ ] **T4.2 架构图**：分层依赖 + RAG 管线 + Agent 状态机
- [ ] **T4.3 Demo 视频**：首次推荐 → 菜谱详情 → 烹饪模式 → 购物清单
- [ ] **T4.4 `docs/API.md`**：由 FastAPI OpenAPI 导出
- [ ] **T4.5 性能压测** `[MVP]`：P95 ≤ 3s，Locust 100 并发
- [ ] **T4.6 安全** `[MVP]`：JWT、HTTPS、SQL 注入防护、安全扫描
- [ ] **T4.7 简历打磨**：RAG 牌 / Agent 牌 / 工程牌
- [ ] **T4.8 文档迭代日志**：`ARCHITECTURE §6`、`CONVENTIONS §10` 每次变更登记

---

## 8. 历史全量计划的通用 DoD

- [ ] 后端：`ruff check . && ruff format --check .` 通过；类型注解完整；IO 全 `async`
- [ ] 后端：`pytest` 覆盖率 ≥ 70%，单测不碰真实 DB
- [ ] 后端：分层单向 `api → services → domain/agents/rag → infra`；`domain` 零 IO；路由 ≤ 10 行
- [ ] 数据：UUID 主键、`TIMESTAMP WITH TIME ZONE`、JSONB、向量 1024、HNSW
- [ ] 前端：`pnpm typecheck && pnpm lint && pnpm build` 通过；禁 `any`、禁 `@ts-ignore`
- [ ] 前端：服务端状态用 TanStack Query，客户端状态用 Zustand，两者不混
- [ ] 页面：响应式、加载/空/错误态齐全、关键操作二次确认、无控制台报错、Lighthouse ≥ 80
- [ ] UI：严格套 `docs/UI_STYLE.md` 的 Natural Organic token
- [ ] UI 禁止项：无 `bg-blue-*` / `bg-purple-*` / `bg-cyan-*` / `text-black` / `rounded-none` / `rounded-sm` / `shadow-lg|xl` / `bg-gradient-to-r`；无纯黑、无冷色主色、无玻璃态、无嵌套卡片、动效带 `prefers-reduced-motion`
- [ ] 工程：不引入技术栈清单外的依赖；换 LLM 供应商 ≤ 1 天；新功能 ≤ 3 文件改动
- [ ] 提交：功能分支 + `<type>: <description>`，PR 前 pytest/ruff 全绿

---

## 9. 冲突处理记录（已全部统一）

| #  | 原冲突                                                    | 统一结论                                                      | 改动落点                                                     |
| -- | --------------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------ |
| ① | 儿童人群 P1 vs`[MVP]`；M2 只说「3 人群」                | **已升级为产品决策：整块取消医学人群细分**（D6 / D16）  | PRD §1.3 / §2 / 模块 D；README 全局约定                    |
| ② | `profiles/` 层级位置不一致                              | 统一到`domain/profiles/`                                    | TECH_STACK §2.2/§4；PRD F-H1/§6；ARCHITECTURE §1/§2/§7 |
| ③ | 前端`src/` 前缀不一致                                   | 统一「不用`src/`」                                          | CONVENTIONS §1.2/§3.3/§9.3；TECH_STACK §2.5              |
| ④ | README 引用不存在的`docs/*.md`；`ARCH.md` 名实不符    | 文档按规范名迁到`docs/`，`ARCH.md` → `TECH_STACK.md`   | 全部文件已迁移                                               |
| ⑤ | Langfuse 标 P1 却又是 MVP                                 | 按 MVP，但 key 缺失时降级为本地日志                           | CONVENTIONS §8.2；TECH_STACK §2.6；README 全局约定         |
| ⑥ | 工期 5-8 周 vs 4-6 周                                     | 统一 4-6 周并配平里程碑                                       | README 路线图；PRD §9                                       |
| ⑦ | 规范内部`src/components/ui/` 与 `components/ui/` 并存 | 统一`components/ui/`                                        | CONVENTIONS §3.3                                            |
| ⑧ | 环境变量清单两处不一致（缺 model / Sentry）               | 以 README 表为准，CONVENTIONS 补齐并标注可留空                | CONVENTIONS §8.2；README 环境变量表                         |
| ⑨ | UI 文档内部「禁止完美圆形」vs「按钮必须`rounded-full`」 | 明确 pill 形状是允许的例外                                    | UI_STYLE 配套实现约定                                        |
| ⑩ | 字体自检禁用 Inter/Roboto/Geist，但 Next 默认就用         | 指定`font-serif`（Noto Serif SC）+ 系统/Noto Sans SC 正文栈 | UI_STYLE 配套实现约定                                        |

---

## 10. 历史全量计划的风险与范围控制

| 风险     | 应对                             |
| -------- | -------------------------------- |
| 数据版权 | 只用开源/授权数据，标注来源      |
| 内容合规 | 免责声明 + 非医疗建议 + 数据可删 |
| LLM 幻觉 | 引用强制 + 规则校验 + 反思重试   |
| 范围膨胀 | 严格按 MVP/P1/P2 分级            |
| 成本失控 | 限流 + 缓存 + 降级               |
| 时间不足 | 优先保 MVP，P1 可延后            |

**范围红线**：约束做扎实 > 功能堆砌；P1 只挑 2-3 个做深；P2 全部写「未来工作」。

---

## 11. 历史：建议的第一批动作（不再执行）

1. **T0.2b**：删掉 `goal/` 旧目录（我这边沙箱不允许删除该目录）。
2. **T0.3-T0.7**：根文件 + `.cursorrules` + 前后端工具链 + 设计 token（1-2 天）。
3. **T0.8/T0.9**：起 `docker-compose`（PG + pgvector + Redis），Alembic 建第一版表（1 天）。
4. **最小闭环**：一条菜谱入库 → 建向量 → 检索返回，证明管线通（1-2 天）。
5. 然后才进入 M1 的规模化（200 道 + 混合检索 + 重排）。

> 依据：M1 的验收全部挂在检索质量（Recall@5 ≥ 85%）上，**检索管线早跑通比多写页面重要**。

---

## 附：本次统一的操作记录

- 文档迁移：`goal/{PRD.md, 技术栈.md, 架构草案.md, 规范.md, website.md, PROJECT.md}` → `docs/{PRD,TECH_STACK,ARCHITECTURE,CONVENTIONS,UI_STYLE}.md` + 根 `README.md`（内容全部保留并统一修改）。
- 权限修复（Windows 文件权限挡住沙箱读写）：
  - `D:\Allcode\MealCompass` 与 `D:\Allcode\MealCompass\goal` 各补了一条当前用户的完全控制权限；备份与回滚脚本在 `D:\Allcode\acl-recovery\`。
  - `goal/` 目录虽已修好权限，但沙箱进程仍无法在其中写入/删除，故采用「复制到 `docs/` 后由你删旧目录」的方式。
- 版本：`README.md` / `PRD` / `TECH_STACK` 标 v1.1；`ARCHITECTURE` 标 v0.2；`CONVENTIONS` 迭代日志加 v1.1 行。
