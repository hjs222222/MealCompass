# 未完成功能与环境受限项登记（failed-features）

> **用途**：如实登记「还没做 / 没验证 / 被环境挡住」的东西，避免文档或界面假装它们可用。
> **维护规则**：新增未完成能力、或跳过某项验证时，必须在下表补一行，并写清证据、影响与承接任务。
> **当前阶段**：三周聚焦计划 W1-W3（评估基线 → Agent 闭环 → 演示与求职材料）｜最后更新：2026-10-13
> **配套**：任务进度见 [`../TODO.md`](../TODO.md)，踩坑过程见 [`mistakes.md`](./mistakes.md)。本文件只记录「状态」，不复述踩坑细节。

## 一、总览

| # | 项目 | 状态 | 影响 | 承接任务 |
| --- | --- | --- | --- | --- |
| F1 | 注册 / 登录 / JWT | 未实现（**主动推迟**） | `/login` 只有禁用占位表单，无鉴权，全部接口假定匿名 | W4+ |
| F2 | 推荐 Agent 闭环 | ✅ **已完成**（原登记项已关闭） | `parse → search → generate → validate` 真机跑通，见 `README.md` | 已交付 |
| F3 | 菜谱详情与烹饪模式 | **部分完成** | `/recipe/[id]` 已可按 ID 看原料和做法；`/cook/[id]` 与份量缩放未实现 | W4+ |
| F4 | 购物清单 / 一周菜单 / 历史 / 画像 | 未实现（**主动推迟**） | 无对应页面 | W4+ |
| F5 | 前端自动化测试 | 部分实现 | 4 项状态序列化测试进入 CI；组件交互和浏览器点击流仍无自动化覆盖 | 待选型 |
| F6 | 浏览器内运行时验证 | **手动验证，未自动化** | 已验证一次真实搜索→详情→浏览器前进/后退→返回；仍无自动化浏览器回归 | 待引入 Playwright |
| F7 | shadcn/ui 组件库 | 未初始化 | `components/ui/` 为空；当前全部为手写 Tailwind 组件 | W4+ |
| F8 | 视觉与无障碍实测 | 未执行 | 未测 Lighthouse ≥ 80、未做真机 / 屏幕阅读器检查 | W4+ |
| F9 | 多轮对话 / 会话持久化 | 未实现（**主动推迟**） | 表和 `langgraph-checkpoint-postgres` 依赖已就位，图未挂 checkpointer；无记忆 | W4+ |
| F10 | `any` / `@ts-ignore` 的运行时兜底 | 部分覆盖 | ESLint 已阻断；新增状态解析测试，但组件交互仍缺运行时兜底 | F5 |
| **F11** | **生成侧评估（RAGAS 四项）** | **未实现** | 只评了检索侧；Faithfulness / Answer Relevancy 无数据 | W4+ |
| **F12** | **`recipes.time_minutes` 全为 NULL** | **解析遗漏与链路固化假设** | 设 `max_time_minutes` 会**排除全部菜谱**，必然返回无解 | 见 F12 说明 |
| **F13** | **评估集规模与标注质量** | **已知局限** | 40 条、单人标注、二值相关度 → 只能做相对比较 | W4+ |
| **F14** | **`/recommend` 端到端延迟 8–12 s** | **已知欠账** | parse 与 generate 两次 chat **串行**；纯检索仅 **0.37–0.44 s** | W4+ |
| **F15** | **混合检索未超过纯向量（RRF 负贡献）** | **实测负面结论** | 见 `README.md`「结论二」；增益全部来自重排（+8.75pp R@10） | W4+ |
| **F16** | **规则引擎 YAML 化（`data/rules/`）** | 未实现 | 约束只能由请求参数直接给，无 YAML 热更新 | W4+ |
| **F17** | **Redis 的使用** | 已起容器、代码未用 | 限流与缓存均未接 | W4+ |
| **F18** | **Sentry 接入** | 未实现 | 配置项已留，异常只进本地日志 | W4+ |
| **F19** | **`generate` 补齐文案的两套模板不一致** | 已知不一致 | shortfall 补齐无后缀、`generate_fallback` 有后缀，用户可见 | W4+ |
| **F20** | **`node_parse` 遇到 JSON 数组静默取末项** | 已知边界、无单测 | 不会崩也不降级，但会取到数组最后一项的字段 | W4+ |
| **F21** | **步骤级向量索引已建但未接入检索** | **建了索引 ≠ 用上了** | `recipe_steps.embedding` 3,806 条真实存在，但 `retriever.py`/`agents/` 全都不读它，对排序零影响 | W4+ |

> **F1/F4/F9/F16 以及 F3 的烹饪模式、份量缩放都是「主动推迟」，不是失败。** 三周聚焦的取舍理由见 `TODO.md` §0.5；
> 对 Agent 后端实习这个目标，**一条能讲透、能测量、有降级路径的链路 > 页面数量**。

## 二、逐项说明

### F1 注册 / 登录 / JWT —— 未实现（主动推迟）

- **现状**：`frontend/app/(auth)/login/page.tsx` 存在，但表单全部 `disabled`，页面上写明「登录（未实现）」。
- **证据**：登录页不发任何请求；全站无鉴权头。
- **影响**：全部接口按匿名用户工作；多用户数据隔离无法验证。
- **为什么推迟**：鉴权是**通用后端能力**，写出来是 CRUD，对「Agent 后端」这个方向的信息增益低。
- **下一步**：邮箱 + 密码 + JWT（bcrypt），接口层加 `Depends(get_current_user)`。

### F3 菜谱详情与烹饪模式 —— 详情已实现，其余主动推迟

- **现状**：`/recipe/[id]` 通过 `GET /recipes/{recipe_id}` 展示原料、做法、图片；无 `/cook/[id]`，未实现份量缩放。
- **证据**：`frontend/app/(main)/recipe/[id]/page.tsx` 与 `backend/api/v1/recipe.py`；后端接口回归测试见 `backend/tests/unit/test_recipe_page_api.py`。
- **影响**：可看完整菜谱，但仍没有逐步烹饪模式和份量调节。
- **下一步**：份量缩放（纯函数适合放 `domain/`）与烹饪模式。

### F4 购物清单 / 一周菜单 / 历史 / 画像 —— 未实现（主动推迟）

- **现状**：均无路由与界面。
- **证据**：`frontend/app/(main)/` 下已有 `dashboard/`、`recommend/`、`recipe/`，仍无购物清单、一周菜单、历史、画像页面。
- **影响**：M3 阶段的界面全部缺失。
- **下一步**：购物清单合并（可按标准名聚合，与食材归一化天然衔接）。

### F5 前端自动化测试 —— 部分实现

- **现状**：`pnpm test:unit` 使用 Node 内置运行器验证推荐快照和外观设置解析/序列化，4 项测试已进 CI；尚无组件交互测试框架。
- **证据**：`frontend/tests/*.test.mjs`、`frontend/package.json` 与 `.github/workflows/ci.yml`。
- **影响**：状态快照的损坏数据有回归保护，但表单点击、跳转、水合和完整 API 守卫仍缺浏览器自动化覆盖。
- **下一步**：确定浏览器测试框架后补一条推荐→详情→返回的点击流。

### F6 浏览器内运行时验证 —— 手动验证，未自动化

- **现状**：此前已用 `pnpm start` 抓取主要页面的 HTTP 200，也把 `lib/api.ts` 编译后用 Node 直连 FastAPI 验证正常、无解和网络不可达。2026-10-13 又通过真实浏览器操作验证：提交「番茄意面」后渲染 3 条推荐、trace `01135c39e972a09c36167835ee0c5983`；打开第一道菜的独立页、浏览器后退/前进以及页面内返回后，原输入、3 条卡片和同一 trace 均保持；字体与暖色主题切换在页面上可见。原始观察摘录见 `evidence/browser_return_state_2026-10-13.txt`。
- **未覆盖**：浏览器点击流尚未进入 CI；跨浏览器、控制台日志及无障碍检查仍未做。
- **影响**：已有一次真实点击证据，但后续改动尚不能自动回归该路径。
- **下一步**：引入 Playwright 覆盖提交 → 详情 → 返回 → 状态保留。

### F7 shadcn/ui —— 未初始化

- **现状**：未执行 `npx shadcn@latest init`，`components/ui/` 不存在。
- **证据**：`frontend/components/` 下是 `providers.tsx`、`status-panel.tsx`、`recommend-form.tsx`、`recommend-results.tsx`。
- **影响**：按钮 / 输入框为手写 Tailwind，与 `docs/UI_STYLE.md` 的 token 已对齐，但缺少 shadcn 的可访问性封装。
- **实际做法**：本次手写了 `aria-invalid` / `aria-describedby` / `role="alert"` / `aria-live="polite"` / 字段级错误，部分弥补。

### F8 视觉与无障碍实测 —— 未执行

- **现状**：未跑 Lighthouse，未做移动端真机与屏幕阅读器检查。
- **证据**：只做了静态检查（Tailwind 类名不含禁止项、状态不靠颜色单独表达、焦点环已定义、`useId` 关联 label）。
- **影响**：`TODO.md` §8 的「Lighthouse ≥ 80」「响应式稳定」两条 DoD 尚未取得证据。
- **下一步**：引入浏览器自动化后一并测（F6）。

### F9 多轮对话 / 会话持久化 —— 未实现（主动推迟）

- **现状**：`conversations` / `messages` 表已建，`langgraph-checkpoint-postgres` 依赖已装，但 `build_graph()` 以 `checkpointer=None` 编译，**API 层不传 `thread_id`**。
- **证据**：`backend/agents/graph.py` 的 `build_graph(deps, *, checkpointer=None)`；CONVENTIONS §4.2 禁止 `MemorySaver`，所以没有偷懒用内存 saver。
- **影响**：每次请求都是独立的单轮，无追问、无指代消解、无历史。
- **下一步**：`compile(checkpointer=PostgresSaver(...))` + API 层透传 `thread_id`；表已就位，工作量小。

### F10 `any` / `@ts-ignore` 的运行时兜底 —— 部分覆盖

- **现状**：`frontend/.eslintrc.json` 用 `no-restricted-syntax`（选择器 `TSAnyKeyword`）阻断 `any`，用 `no-warning-comments`（terms `@ts-ignore`）阻断忽略指令；已用临时探针文件实测会报错。
- **未覆盖**：没有前端测试框架，无法运行时兜底；若有人绕过 `pnpm lint` 直接提交，也没有 pre-commit 钩子拦截。
- **下一步**：`.github/workflows/ci.yml` 已把 `pnpm lint` 设为必过门禁（本次已落地）。

### F11 生成侧评估（RAGAS 四项） —— 未实现

- **现状**：`RAGAS` **未安装**，代码里没有任何引用。
- **证据**：`backend/pyproject.toml` 无 `ragas`；本次只实现了检索侧指标（Recall@5/10、MRR@10、nDCG@5）。
- **影响**：**「引用防幻觉」有单测与领域层校验，但没有量化的幻觉率数字**；`docs/TECH_STACK.md` 曾把 RAGAS 写成已选技术栈，已在 README 中改标为「已规划未引入」。
- **下一步**：需要标注参考答案（40 条不够，建议扩到 200+ 条再做）。

### F12 `recipes.time_minutes` 全为 NULL —— 解析遗漏与推荐链路固化假设

- **现状**：当前结构化时长全空。原文并非完全没有时长：`aquatic/鳊鱼炖豆腐/鳊鱼炖豆腐.md` 明确写「从备料到完成约需 40 分钟」，JSON 和数据库 description 都保留此句。
- **根因**：`import_howtocook.parse_recipe_markdown` 固定写 `time_minutes=None`，`agents.nodes` 生成及校验也强制清空。此前「上游不提供」的归因错误，数据库为空不能证明原文缺失。
- **影响**：后端时间硬约束仍排除 NULL；自然语言若被解析成时间约束，仍可能无解。历史场景类评估数字保留，不把修正文档当成已重测指标。
- **用户最终决定（2026-10-12，W3.12）**：保留推荐卡片时长，只展示简介中可明确辨认的原文时长及约值/区间；不做模型估算、不把单步时长当总时长。详情读取时实时提取原文文本，数据库结构化字段尚未回填。
- **剩余缺口**：时间硬约束依赖结构化 `time_minutes`，仍排除全 NULL；前端不应提供一个会必然无解的时间筛选控件。尚不能声称所有菜谱都已自动提取成功。

### F13 评估集规模与标注质量 —— 已知局限

- **现状**：`data/eval/queries.yaml`，**40 条**查询（5 类 × 8 条），标注 1~3 个相关菜谱。
- **已做的保障**：`eval.py --validate-only` 会校验**每一条标注的菜名都真实存在于库中**（防止用不存在的菜名虚高指标）。
- **局限（必须主动说）**：
  1. **单人标注**，无标注者间一致性（Kappa）数据；
  2. **40 条是小样本**，只能做**相对比较**（哪组更好），不能当绝对质量结论；
  3. **相关度二值**（相关/不相关），nDCG 里都按 1 计，导致 nDCG 与 Recall 高度相关、信息量重叠。
- **下一步**：扩到 200+ 条 + 双人标注 + 分级相关度。

### F14 `/recommend` 端到端延迟 8–12 s —— 已知工程欠账

> 数字为 2026-10-11 数据重灌后的实测（3 轮连跑聚合，原始输出入库在 [`docs/evidence/e2e_run2.txt`](./evidence/e2e_run2.txt) / [`e2e_run3.txt`](./evidence/e2e_run3.txt) / [`e2e_run4.txt`](./evidence/e2e_run4.txt)，区间表在 [`e2e_latency_summary.txt`](./evidence/e2e_latency_summary.txt)）。

- **现状**：真机实测三轮 `{"query":"西红柿炒鸡蛋"}` = **9.2 – 12.0 s（极差 2.8 s）**；`{"query":"清淡的汤，不要辣"}` = 7.6–9.2 s；而无解路径稳定 **2.1–2.3 s（极差 0.2 s）**、纯检索稳定 **0.37–0.44 s（极差 70 ms）**。**同一份代码同一份语料，生成阶段就能差出 2.8 s，而检索阶段只差 70 ms**——这本身就是"延迟不可给精确值、且波动来自 LLM 而非检索"的直接证据。
- **根因（已定位）**：`parse` 与 `generate` 是**两次串行 chat 调用**，合计 ≈ 10 s。检索不是瓶颈。
- **影响**：作为演示可接受，作为产品不可接受。
- **下一步（三选一，都属产品取舍）**：① 把 parse 换成规则/更小的模型；② 两者并发（但 generate 依赖 parse 的结果，只能并发"预取候选"）；③ 合并成一次调用（用一个 prompt 同时产出约束与推荐）。**本次没有自作主张改，因为会改变产品语义。**

### F15 混合检索未超过纯向量（RRF 负贡献） —— 实测负面结论

> **数字已按 2026-10-11 数据重灌后的最新一轮全量评估更新**（重灌前的旧值为 R@5 0.596 vs 0.638）。

- **现状**：40 条评估集上，`hybrid`（向量 Top50 + BM25 Top50 → RRF）**全面差于**纯向量：Recall@5 **0.6125** vs **0.6375**、Recall@10 **0.6875** vs **0.7208**、MRR@10 **0.7086** vs **0.7400**、nDCG@5 **0.5982** vs **0.6309**。
- **已定位的根因（已推翻早期猜测）**：早期我写的是「BM25 把字面相似但不相关的菜顶进头部」，**这个猜测被逐条三元组分析否定了**。真实机制是**纯结构性的不等式**：等权 RRF 下，**单通道项上界 `1/(60+1)=0.016393`** 严格小于**双通道项下界 `2/(60+50)=0.018182`**——所以**只要一道菜两路都进 Top50，它必然排在所有单通道候选之前**，哪怕两路都排第 50。7 条回归查询的 21 个金标准里，「仅向量召回」的有 **13** 个，它们的向量名次极好（`西红柿炒鸡蛋` 向量 #1 → RRF 第 22；`戚风蛋糕` 向量 #1 → RRF 第 21），却因 BM25 未召回而被整体降级。
- **权重敏感性实验（新增，6 档共用同一候选池）**：`w_bm25 = 0.0 / 0.25 / 0.5 / 1.0`，以及两档「各通道只取 Top10」。**没有任何权重能让所有指标都赢过纯向量**：`0.0` 拿下 R@5 / MRR / nDCG 三项；`0.25` 是唯一在 R@10 上更好的（0.7417 vs 0.7208）。**唯一严格单调的量是 Top10 里双通道共识项占比：52.0% → 73.3% → 85.3% → 87.3%。** 按召回深度截断（两个 Top10 档）**压低了共识占比但 R@5 完全没变**（都是 0.6125），代价是踢掉 26 个金标准。
- **唯一的正收益来自重排**：`hybrid_rerank` Recall@10 = **0.7750**（相对 `hybrid` **+0.0875**，即 +8.75pp），说明增益**全部来自 reranker**，RRF 那一步是净负贡献。
- **为什么保留这个结论**：**这是本次评估最有价值的产出**。它证明了「混合检索不一定更好」，也说明消融实验的必要性——只看最终数字会误以为两路都在贡献。
- **下一步**：把默认权重从 `w_bm25 = 1.0` 改成有证据的取值（主指标用 `0.0`；必须保留关键词通道则用 `0.25`）。**本轮没做**——这是 `rag/fusion.py` 的行为变更，且当前默认值已被明确登记为「已知的、有证据的次优值」，比未经测量就"优化"更诚实。

### F16 规则引擎 YAML 化（`data/rules/`） —— 未实现

- **现状**：`data/rules/` 目录**不存在**。硬约束（忌口/时间/厨具）目前只能由**请求参数**直接给出，没有 YAML 规则文件。
- **影响**：`README.md`「全局约定」里写的「YAML 文件（`data/rules/`），不入库，可版本控制」**当前是空头承诺**，已在 README 中改标为「🚧 目录尚未创建」。
- **下一步**：把「忌口 → 需要排除的食材别名」「厨具别名归并」这类映射外置成 YAML。

### F17 Redis —— 已起容器、代码未用

- **现状**：`docker-compose.yml` 起了 `redis:7-alpine` 且 healthy，但**代码里没有任何 Redis 引用**。
- **影响**：无限流、无缓存；`REDIS_URL` 配置项形同虚设。
- **下一步**：先做 LLM 调用限流（按会话），因为 LLM 是成本与延迟的主要来源。

### F18 Sentry —— 未实现

- **现状**：配置项（`sentry_dsn` 之类）已留，但没有任何 SDK 调用。
- **影响**：异常只进本地结构化日志，无聚合与告警。
- **下一步**：与 `core/exceptions.py` 的错误信封对接。

### F19 `generate` 补齐文案的两套模板不一致 —— 已知不一致

- **现状**：同为「规则生成的推荐理由」，**shortfall 补齐**的那条是 `命中你的需求「{query}」的混合检索第 {rank} 名结果`（`nodes.py:240-245`，**无后缀**）；而 `node_generate` 的整段规则兜底会在同一模板后**再加一句**「（未启用 LLM 润色，由规则兜底生成）」（`nodes.py:336`）。用户能看出文案差异。
- **影响**：不影响正确性，但属于「同一件事两套说法」的体验不一致。
- **为什么没修**：发现它时 `agents/` 已冻结，且这是行为变更（会改变对外文案），登记而非擅自改。
- **下一步**：抽一个 `render_rule_reason(query, rank, *, fallback: bool)` 统一两处。

### F20 `node_parse` 遇到 JSON 数组会静默取末项 —— 已知边界、无单测

- **现状**：`node_parse` 用 `extract_json_object`，其包络算法是「第一个 `{` → **最后一个** `}`」（`jsonx.py` 用 `rfind`）。若模型返回 `[{"max_time_minutes":30},{"max_time_minutes":5}]`，`json.loads` 得到的是**只含最后一个元素**的片段 → 结果 `{"max_time_minutes": 5}`。
- **影响**：**不会崩、不会降级**（只判 `payload is not None`），所以会**静默**取到末项字段且**不打 `parse_intent_failed` 标签**。真机未观测到该形态（SiliconFlow 实际都返回对象），因此**无单测覆盖**。
- **对照组**：`node_generate` 的解析器**显式支持裸数组**，并有单测 `test_node_generate_accepts_bare_array_payload`。**即 generate 这条链路有覆盖、parse 这条漏了。**
- **下一步**：`node_parse` 在 `extract_json_object` 返回 `None` 时再试 `extract_json_array(...)` 取首个元素；补一条单测。

### F21 步骤级向量索引已建但未接入检索 —— 「建了索引」≠「用上了」

- **现状**：`recipe_steps.embedding` 里**3,806 条 1024 维向量真实存在**（`count(embedding) = 3806`，`vector_dims = 1024`，无 NULL），确实是"双层索引"的字面事实。**但没有任何生产代码读它**：`rag/retriever.py`、`rag/corpus.py`、`rag/bm25_index.py`、`agents/*`、`services/*`、`api/*` 对 `recipe_steps` 的引用数**全为 0**（唯一引用在 `scripts/build_index.py` 的写入侧和 `rag/chunking.py` 的注释）。
- **影响**：**这一层对线上排序的贡献是零。** `docs/PRD.md` F-B2 设计的「按技法/细节精取（如『怎么勾芡』）」**没有实现**——目前只有卡片级单层召回。所以 README 里「双层索引」这四个字**只能读作"两层索引都建好了"，不能读作"两层都参与检索"**。这是本次全仓库复核新发现的**文档口径风险**，已同步修正 README L24 与 `chunking.py` 的模块注释。
- **为什么是"未接入"而不是"没建"**：这两件事在文档里极易混为一谈，而它们的工程含义完全不同——"没建"是缺数据，"没接入"是缺一次检索改造。如实登记为两者中的后者。
- **为什么保持现状**：接入步骤层需要改 `retriever.py` 的召回与融合逻辑（多一路召回 + 融合权重），属**行为变更**，且会改变 README 里四组实测数字的有效性；当前正处于"求职材料已定稿"的冻结期，登记而非擅自改。
- **下一步**：`_vector_search` 增加一条步骤层通道（`recipe_steps` join `recipes`），把"步骤命中 → 上卷到菜谱"作为第三路召回进 RRF；然后用 `scripts/eval.py` 重跑四组，看 R@5/R@10 是否真的变好。**注意**：这很可能又是一次负结论（步骤级召回的噪声通常更大），但那才是有价值的实测。

## 三、被环境限制而跳过的验证（与代码无关）

| 项目 | 限制 | 现状 |
| --- | --- | --- |
| `pnpm install` 默认布局 | Windows 符号链接导致 `ERR_PNPM_SYMLINK_FAILED` | 已用 `frontend/.npmrc` 的 `node-linker=hoisted` 绕过，安装可复现 |
| `next build` 默认 worker | 沙箱禁止带 IPC 具名管道的子进程（`spawn EPERM`） | 已用 `workerThreads: true` + `webpackBuildWorker: false` 绕过，构建可复现 |
| `.pytest_cache` | 沙箱内无法创建 | 一律带 `-p no:cacheprovider` |
| 系统临时目录 | 沙箱拒写 `C:\Windows\Temp` | 跑测试/脚本前把 `$env:TEMP` 指到 `<仓库>\.tmp`；不使用 `tmp_path` fixture |
| sqlite 的 `json1` 扩展 | 本机 sqlite 编译时未带 `json1` | 集成测试依赖真 PG，不用 sqlite 模拟 |
| 浏览器自动化 | 环境未提供（无 Playwright/Puppeteer/jsdom） | 见 F6 |
| 本地兜底模型 | `sentence-transformers` **未安装**于当前 venv | 远程优先路径全部实测通过；`ENABLE_LOCAL_FALLBACK=true` 时本地兜底**未验证** |

> 这七条都不是代码缺陷，处理方式与代价记录在 [`mistakes.md`](./mistakes.md)。

## 四、本次（2026-10-11 三周聚焦）由「未完成」转为「已完成」的项

| 原登记 | 现状 | 证据 |
| --- | --- | --- |
| F2 推荐 Agent 闭环 | ✅ 已交付 | `backend/agents/` 5 个文件；真机 `POST /recommend` 返回 3 条推荐，`node_path=[parse,search,generate,validate]` |
| 引用校验是死代码 | ✅ 已接入 | `domain/citations.py` 的 `validate_recommendations` 成为 `node_validate` 的核心逻辑 |
| `LLMClient` 无实现 | ✅ 已实现 | `backend/infra/llm_client.py`（`RemoteLLM` + `strip_code_fence` + 指数退避），26 项单测 |
| 无评估脚本 / 无评估集 | ✅ 已实现 | `backend/scripts/eval.py`（537 行）+ `data/eval/queries.yaml`（40 条）+ 三组真实报告 |
| 无 CI | ✅ 已实现 | `.github/workflows/ci.yml`（后端 4 步 + 前端 3 步，覆盖率门禁 70%，只统计生产代码） |
| 无 LICENSE（README 却挂了 MIT badge） | ✅ 已补 | 根目录 `LICENSE`（MIT + HowToCook Unlicense 归属说明） |
| README 声称「Recall@5 ≥ 85%」但无任何测量 | ✅ 已改 | README 改为**实测数字**，并明确写出「混合检索没有赢」的负面结论 |
| 前端 0 推荐页面 | ✅ 已交付（构建级验证） | `/recommend` 页面 + 表单 + 三态结果；**但浏览器内水合未验证（F6）** |
| 解析层把说明文字当食材（`unmapped_top` 里全是噪声） | ✅ 已修 | 章节标题 / 说明句 / 缩放规则 / 工具分流 / 并列写法拆分五类过滤，新增 152 项导入器测试；归一化率 73.5% → **75.3%**，待确认用量 86 → **25** 条，噪声条目在 `unmapped_top` 里**全部消失** |
| 数据重灌后评估数字失效风险 | ✅ 已处理 | 重灌前留底 4 份报告 → 重灌 → **重建双层索引**（372 卡片 + 3,806 步骤）→ `--validate-only` 40/40 → 全量重跑三组 + 权重消融，README / INTERVIEW / DATA_SOURCES / TODO 一次性统一 |
