# MealCompass 待办清单

> 文档来源：`README.md`、`docs/PRD.md`、`docs/TECH_STACK.md`、`docs/ARCHITECTURE.md`、`docs/CONVENTIONS.md`、`docs/UI_STYLE.md`
> 更新：2026-10-13 ｜ 状态：**三周核心 Agent 闭环计划已完成（见 §0.5）**。本文件中旧 P0/M1/M2/M3/M4 的未勾选项均为历史全量计划或未来范围，**不是当前待办**；实测数字见 `README.md` 的「评估结果」。
> 标记：`[MVP]` 必须做 ｜ `[P1]` 时间允许必做 ｜ `[P2]` 写入「未来工作」

---

## 0.5 三周聚焦计划（2026-10-11 起，**当前唯一口径**）

> **背景**：原计划是 4-6 周的全量产品（7 节点 Agent、5 个工具、11 个页面、鉴权、购物清单……）。
> 评估结论：**核心 Agent 链路当时一行代码都没有**，而检索链路已经做扎实。
> 对「Agent 后端实习」这个目标来说，**一条能讲透的完整链路 + 可测量的证据**远比页面数量值钱。
> 因此收敛范围：**砍掉一切外围，只做 Agent 闭环 + 评估 + 一个能演示的页面。**

**优先级**：核心 Agent 闭环 > 评估与可观测 > 最小演示 > 外围功能。

| 周 | 目标 | 出口条件（可验证） | 状态 |
| --- | --- | --- | --- |
| **W1** | 评估与安全基线 | 40 条人工核验评估集落盘；纯向量 / 混合 / 混合+重排三组消融**实测数字**；引用校验接入闭环 | ✅ 已完成 |
| **W2** | Agent 后端闭环 | `parse → search →（无解短路）→ generate → validate` 真机跑通；无解显式返回；降级路径有测试 | ✅ 已完成 |
| **W3** | 演示、证据与求职材料 | `/recommend` 页面可用；README 数字全部可复现；`docs/INTERVIEW.md` 面试问答方案 | ✅ 已完成 |

**范围内（必须做）——全部完成，逐项打勾并附证据**

- [X] **W1.1 评估集**：`data/eval/queries.yaml`（40 条 = 5 类 × 8 条，标注均为库里真实菜名；`--validate-only` 40/40 通过）
- [X] **W1.2 评估脚本**：`backend/scripts/eval.py`（537 行，`--mode vector|hybrid|hybrid_rerank|weight|all` + `--validate-only`），Recall@5 / Recall@10 / MRR@10 / nDCG@5 + 延迟，指标函数 31 项单测
- [X] **W1.3 消融实验**：三组真实数字写入 README（纯向量 63.75% / 混合 61.25% / 混合+重排 64.17% R@5），**并追加 6 档权重敏感性消融**
- [X] **W1.4 引用校验接入**：`domain/citations.py` 从"死代码"变成闭环里的真实节点（`node_validate` 丢弃编造 `recipe_id`）
- [X] **W2.1 `LLMClient` 实现**：`infra/llm_client.py`（OpenAI 兼容 + 指数退避 + 代码块围栏容错，26 项单测）
- [X] **W2.2 最小 LangGraph 闭环**：`backend/agents/`（`state.py` / `nodes.py` 453 行 / `graph.py`）
- [X] **W2.3 接口**：`POST /recommend`、`POST /recipes/search`（薄路由 + `RecommendService` 编排）
- [X] **W2.4 降级与无解**：LLM 解析失败 → 规则降级；硬约束无候选 → 显式 `no_solution_reason`（真机复现 **2.0–2.2 s** 短路返回，三轮稳定；对比生成路径 9–12 s）
- [X] **W3.1 前端推荐页**：`/recommend`（表单 + 结果 + 无解 + 降级态，`pnpm build` 5 条路由全过）
- [X] **W3.2 口径诚实化**：README 全部改为"状态 + 证据"，删除未测量的「Recall@5 ≥ 85%」目标值
- [X] **W3.3 工程门禁**：`.github/workflows/ci.yml`（ruff + pytest 覆盖率 ≥ 70% + 前端三检查），7 条命令本地实跑
- [X] **W3.4 面试材料**：`docs/INTERVIEW.md`（简历三版本 + 自我介绍三时长 + 分主题深挖 Q&A + 承认答不上来的对照表）
- [X] **W3.5 数据质量收尾（本次追加）**：解析层噪声清理（章节标题 / 说明句 / 缩放规则 / 工具分流 / 并列写法拆分），归一化率 73.5% → 75.3%，待确认用量 86 → 25 条；重灌 + 重建双层索引（372 卡片 + 3,806 步骤）；重跑三组评估确认结论未变
- [X] **W3.6 覆盖率补强（当时记录）**：补齐 `infra/db.py`（64% → **100%**，`create_async_engine` 惰性故无需真库）、`infra/observability.py`（75% → **94%**，注入假 langfuse 模块覆盖启用路径）、`api/deps.py`（80% → **100%**，装配链 + 关闭失败分支）。当时生产代码覆盖率 93% → **96%**，测试 456 → **547 passed / 4 skipped**；当前基线以 W3.19 后的 589 passed / 4 skipped / 95% 为准。过程中踩到并修掉「用例间 `os.environ` 污染导致单跑绿、全量 6 红」，登记在 `docs/mistakes.md`
- [X] **W3.7 证据入库与端到端复现（本次追加）**：新增 5 个入库脚本（`e2e_probe` / `e2e_latency_summary` / `summarize_eval_reports` / `channel_attribution` / `rerank_variance`）与 28 项针对它们纯函数的单测；原始输出与前后报告统一入库到 `docs/evidence/`（3 轮端到端 + 聚合区间表 + 评估摘要含 SHA256 + 抖动 + 归因 + 清理前/后 `import_report`），**含那次字段写死的误报留档** `e2e_run1_OLD_PROBE_field_bug.txt`；README 端到端表由单值改为**多轮区间 + 极差**，并如实写明 `degraded` 在三轮中会翻转
- [X] **W3.8 数字对账进 CI（本次追加）**：新增 `backend/scripts/check_docs_consistency.py` + 28 项单测，把「正文数字必须能追到 `docs/evidence/`」从**靠人自觉**变成**跑一条命令就知道**——① README 评估表每个指标格对账 `eval_reports_summary.json`；② `hybrid_rerank` 的区间格子必须**恰好等于** `rerank_variance.txt` 的跨轮极差（手写一个"差不多"的区间会被抓）；③ README 引用的每个证据路径必须真实存在。已作为独立步骤进 CI。**并做了篡改自检**：把 R@5 改成 99.99% → exit 1；引用不存在的证据文件 → exit 1。测试数 519 → **547 passed / 4 skipped**

- [X] **W3.10 浏览器跨域修复（2026-10-12）**：FastAPI 增加 CORS 来源白名单配置，覆盖 JSON POST 预检、状态接口及错误响应；12 项回归测试；真实 HTTP 推荐返回 3 条且含跨域响应头。Windows Docker 引擎未就绪排障说明同步到 README。
- [X] **W3.11 推荐卡片 UI 打磨（2026-10-12）**：`recipe_id` 从卡片主视觉层移入 `<details>` 披露入口（可展开复制，剪贴板不可用时退化为手动选中）；新增 `docs/UI_STYLE.md`「技术性标识必须折叠」约定
- [X] **W3.12 完整菜谱卡片（2026-10-12）**：推荐响应补充原文明示时长、难度、热量、原料份量、工具、步骤、附加说明、来源和真实图片；图片受限静态端点仅允许读取菜谱图片；卡片详情折叠展示，无图/读取失败有明确状态。时长审计 372 道：367 条保守提取，5 条留待人工确认；未做模型估算、未重灌数据库。
- [X] **W3.13 一键启动脚本（2026-10-12）**：`start_mealcompass.bat` + `scripts/start_mealcompass.ps1`，双击即自检环境、起前后端、就绪后打印可点击网址；子命令 `check` / `status` / `stop` / `open` / `reload`。自检覆盖依赖、端口占用（打印占用进程）、数据库 TCP 可达（连不上尝试 `docker compose up -d postgres`）、上次残留进程；日志被占时自动换时间戳文件名；`next dev` 的 `spawn EPERM` 自动降级为生产模式；后端 `--reload` 改为 opt-in（具名管道受限环境会失败）。实测：pwsh 7.6 与 PowerShell 5.1 下 `check` 均 exit 0，真实启动 4 个网址全 HTTP 200，`stop` 后端口释放。
- [X] **W3.14 演示前体验修复（2026-10-12）**：① 修复"不要南瓜"却推荐山药南瓜炖鸡汤——根因是食材词表缺"南瓜"+别名（小南瓜≠南瓜），补 aliases.yaml 并 DB 回填 ingredient_id；② HardFilters/RecommendRequest 加 `category` 字段并 SQL 下推，前端加 8 个中文分类快捷按钮；③ 删厨具选择 UI 与"所需工具"区块（上游 tools 恒为空，类型保留）；④ 删"按烹饪时长筛选（暂不可用）"占位块；⑤ 卡片 reason 不再暴露"混合检索第 N 名"系统术语，GENERATE prompt 改为"必须恰好 N 条"减少 shortfall；⑥ 热量标签去掉"（HowToCook 预估）"后缀；⑦ logging.py 加 RotatingFileHandler（5MB×3）；⑧ DEGRADATION_LABELS 补 recommendation_shortfall 中文释义。后端 580 passed、前端 typecheck/lint/build 全绿。
- [X] **W3.15 忌口跨名称漏网修复（2026-10-13）**：针对猪肉 trace `ac1136dd07eb2d66abe1de9435397fc1` 和南瓜 trace `4a1f9a8ca618906c7db30ce21bea9630`，确认解析已提取忌口、漏点在检索允许 ID 集合。SQL 下推增加菜名检查和词典同义名展开，覆盖五花肉条等未映射原料、番茄酱/番茄膏等衍生产物及西红柿写法；上游原文已明确土豆的炸薯条也通过词典关联名排除。真实数据库回归覆盖事故菜谱，并断言「不要猪肉」保留牛里脊菜。无需重灌或重建向量。
- [X] **W3.16 忌口事故面试复盘（2026-10-13）**：`docs/INTERVIEW.md` Q3.2 记录猪肉/南瓜 trace 的定位证据、精确等值→局部 LIKE→检索前多字段+同义名判定的修复过程、牛里脊误伤反例与真库回归；Q6.2 区分保守入库归一化与忌口匹配语义，并删除已过期的「仍待修」说法及绝对安全承诺。
- [X] **W3.17 推荐卡片与独立菜谱详情（2026-10-13）**：移除「还缺的食材」栏目、菜谱 ID 折叠入口与配图说明；ID 置于卡片右上角，菜名和完整菜谱入口均导航至 `/recipe/[id]`；`GET /recipes/{recipe_id}` 支持直接访问和刷新，详情展示原料、可用工具、步骤、附加说明及图片。
- [X] **W3.18 推荐页状态与外观设置（2026-10-13）**：同标签页 `sessionStorage` 保留表单草稿、最后一次请求和推荐结果，详情页返回/前进不重复调用 Agent，新搜索替换旧结果；右上角外观面板可调字体、字号、舒展双列/单列阅读排版、三套自然暖色主题，偏好保存在 `localStorage`。前端状态序列化 4 项 Node 内置测试进入 CI。
- [X] **W3.19 用户反馈回归：分类、附加说明与原料清单（2026-10-13）**：
  - [X] 饮品分类不再出现菜肴：修复 Agent 合并硬约束时丢失显式 `category`；解析成功和失败均保留分类。真实 `category=drink` 请求返回“百香果橙子特调、海边落日、可乐桶”。
  - [X] “海边落日”附加说明不再显示 `###` 和 `![...](...)` 原文：按结构渲染 Markdown 标题，并只映射该菜谱已收录的本地配图，浏览器确认图片加载成功。
  - [X] 完整菜谱原料使用可勾选清单：去掉项目符号和“用量未注明”，名称、已知用量及备注用空格分隔；浏览器确认勾选状态可切换。
  - [X] 回归：后端 589 passed / 4 skipped；前端 6 项单测、typecheck、lint、build 均通过。

**明确不做（三周内）**：注册登录、购物清单、一周菜单、烹饪指导模式、语音、长期记忆、多智能体、A/B 实验、付费。

> **完成判定**：W1–W3 的出口条件均已满足。本项目后续若恢复开发，应先从 `docs/failed-features.md` 选择一项重新立项；不得把下方历史清单的未勾选项直接当作当前任务。

> 这些不是"失败"，是**主动推迟**。状态登记见 `docs/failed-features.md`。

---

## 0. 怎么用这份清单

- 文档间冲突已在 §1 定稿，并写入 `README.md` 的「全局约定（唯一口径）」——**以后所有文档、代码、AI 生成内容以那一节为准**。
- 顺序原则（三周实际范围）：**约束做扎实 > 功能堆砌；评估与可复现证据不可省。** 部署属于后续产品化任务，不倒灌为当前待办。
- 每个任务都标了来源文档，方便回头对验收标准（DoD）。

---

## 后续开发入口

- 当前三周计划已完成，完成度为 **100%**。
- 尚未实现、受环境限制或需要产品取舍的功能，统一登记在 [`docs/failed-features.md`](./docs/failed-features.md)。后续开发先从其中选择一项建立新的任务与验收标准。
- 三周聚焦前的 4–6 周完整产品设想、旧任务和旧 DoD 已移至 [`docs/HISTORICAL_FULL_PLAN.md`](./docs/HISTORICAL_FULL_PLAN.md)，仅供追溯，不显示为待办。
