# MealCompass · 饭点罗盘

> 基于混合检索与 LangGraph 的多约束菜谱推荐 Agent
> 根据你的食材、时间、厨具、忌口，推荐今天做什么，并提供可独立打开的完整菜谱。
>
> **文档版本 v1.2（2026-10-11）**：README 口径改为「以实测证据为准」，未测量的一律标注。全局口径见 [全局约定（唯一口径）](#-全局约定唯一口径)。

[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-14-black)](https://nextjs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2-orange)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-336791)](https://www.postgresql.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](./LICENSE)

---

## 📌 当前状态（先读这一节）

这个项目**还在开发中**，下面每一行都不是路线图，而是**当前的真实状态**：

| 能力 | 状态 | 证据 |
| --- | --- | --- |
| 菜谱知识库（372 道 / 3,697 条食材 / 3,806 个步骤） | ✅ 已入库并实测 | `data/recipes/import_report.json` |
| 双层向量索引（卡片级 + 步骤级，1024 维，HNSW） | ⚠️ **两层都已建；但只有卡片级参与检索** | 库里 372 + 3,806 条向量都真实存在（`count(embedding)` 可查）；**`retriever.py` 只读卡片层**，步骤层未接入，见 F21 |
| 混合检索（向量 Top50 + BM25 Top50 → RRF → 重排） | ✅ 已实现并实测 | `backend/rag/retriever.py`、`scripts/smoke_retrieval.py` |
| 硬约束**下推**到检索层（忌口 / 时间 / 厨具） | ✅ 已实现（SQL 层） | `backend/rag/retriever.py`、`tests/unit/test_retriever_filters.py` |
| 引用校验（拒绝 LLM 编造 `recipe_id`） | ✅ 已实现并接入 | `backend/domain/citations.py` |
| LangGraph 最小闭环（parse → search → generate → validate） | ✅ 已实现 | `backend/agents/` |
| `POST /recommend`、`POST /recipes/search` 接口 | ✅ 已实现 | `backend/api/v1/recommend.py` |
| 混合检索消融实验（纯向量 / 混合 / 混合+重排） | ✅ **已实测**，数字见 [评估结果](#-评估结果) | `data/eval/`、`backend/scripts/eval.py` |
| 前端推荐页 `/recommend` | ✅ 已实现 | `frontend/app/(main)/recommend/`；返回详情后保留本标签页的输入与结果，浏览器点击证据见 `docs/evidence/browser_return_state_2026-10-13.txt` |
| 规则引擎 YAML 化（`data/rules/`） | 🚧 未实现 | 目录不存在；当前约束由请求参数直接给 |
| 澄清追问 / 反思重试 / 多轮对话 | 🚧 未实现 | 无 `MemorySaver`/`PostgresSaver` 会话持久化接线 |
| 注册登录（邮箱 + JWT） | 🚧 未实现 | `/login` 仍是禁用占位表单 |
| 菜谱详情 `/recipe/[id]` | ✅ 已实现 | `GET /recipes/{recipe_id}` 按 ID 读取原料、步骤与配图；购物清单 / 一周菜单仍未实现 |
| 前端自动化测试 | ⚠️ 部分实现 | 4 项状态序列化测试已进入 CI；浏览器点击流仍未覆盖 |

> 未完成、未验证、被环境挡住的东西，逐项登记在 [`docs/failed-features.md`](./docs/failed-features.md)——**不假装可用**。
> 踩坑与解决过程登记在 [`docs/mistakes.md`](./docs/mistakes.md)。

---

## 📖 项目简介

MealCompass 面向**所有做饭的普通人**：不只是一个"今天吃什么"的随机转盘，而是先用**硬约束**把你明显做不了或不能吃的菜剔掉，再用**混合检索**找近似菜谱，最后让 **LLM 只负责解释与取舍**，并且任何推荐都必须指向知识库里真实存在的 `recipe_id`。

**核心设计取舍**：

- 🧩 **能确定的不交给 LLM**：忌口、时间、厨具是硬约束，**下推到 SQL 检索层**，LLM 不参与判定——它只负责把自然语言查询翻译成约束、把候选菜谱翻译成人话。
- 🔍 **混合检索而不是纯向量**：BGE-M3 稠密向量 + BM25 关键词 + RRF 融合 + bge-reranker 重排。四段各自有单测与消融数据（见 [评估结果](#-评估结果)）。
- 🤖 **最小可讲的 Agent 闭环**：LangGraph 状态机 `parse → search →（无解则短路）→ generate → validate`。**刻意不做**七节点编排——先把一条链路做扎实、可测量。
- 🛡️ **防幻觉是硬校验不是提示词**：`domain/citations.py` 在领域层校验每个 `recipe_id` 必须精确命中候选，编造的引用会被丢弃。
- 🏗️ **接口先行**：所有 Protocol 集中在 `backend/domain/ports.py`，实现在 `infra/`、`rag/`；`domain` 零 IO。
- 📊 **可观测与可复现**：Langfuse 链路追踪（观察名是契约常量），未配 key 时自动降级为本地结构化日志。

---

## ✨ 核心功能

状态口径：`✅ 已实现并实测` / `🚧 开发中` / `📋 已规划未开始`

| 模块 | 功能 | 状态 |
| --- | --- | --- |
| 知识库与 RAG | 372 道结构化菜谱、双层索引（**步骤层未接入检索，见 F21**）、混合检索、重排、引用防幻觉 | ✅ 已实现并实测（步骤层除外） |
| Agent 推荐 | 最小闭环（查询理解 → 检索 → 生成 → 引用校验）、无解显式返回 | ✅ 已实现并实测 |
| 约束引擎 | 忌口 / 时间 / 厨具**硬过滤下推到检索层** | ✅ 已实现（SQL 层） |
| 约束引擎 | 口味软偏好、YAML 规则热更新 | 🚧 开发中 |
| Agent 推荐 | 澄清追问、反思重试、多轮对话、工具调用 | 🚧 开发中 |
| 用户与画像 | 邮箱 + JWT、画像 CRUD | 🚧 开发中 |
| 菜谱与烹饪 | 详情、份量缩放、食材替代、烹饪指导模式 | 🚧 开发中 |
| 购物与规划 | 购物清单、一周菜单、库存 | 📋 已规划未开始 |
| 反馈与迭代 | 点赞 / 收藏 / 做过、历史记录 | 📋 已规划未开始 |
| 系统与运维 | 分层架构、配置外置、Langfuse、Docker、CI | ✅ 已实现 |
| 评估 | 40 条人工核验评估集 + 三组消融 + Recall/nDCG 复现脚本 | ✅ 已实现并实测 |

> 完整功能列表与验收标准（DoD）见 [`docs/PRD.md`](./docs/PRD.md)。

---

## 📊 评估结果

**这些数字由 `backend/scripts/eval.py` 真实跑出，可一键复现**（40 条人工核验查询，真连本机 PostgreSQL + SiliconFlow）：

```bash
cd backend
.venv\Scripts\python.exe -m scripts.eval --mode all
```

**实测环境**：本机 Docker Postgres 16 + pgvector（372 道菜、372 卡片向量、3,806 步骤向量）+ SiliconFlow `BAAI/bge-m3` / `BAAI/bge-reranker-v2-m3`（`provider_stats` 中 `degraded_calls = 0`，即**全部走远端、无降级污染**）。三组统一取 **Top50 候选池**，指标只在前 5 / 前 10 上截断。**⚠️ 但下表的排序完全由卡片级单层召回决定**——3,806 条步骤向量虽已建好，检索路径不读它（F21）。

| 模式 | Recall@5 | Recall@10 | MRR@10 | nDCG@5 | 延迟中位数 | P95 |
| --- | --- | --- | --- | --- | --- | --- |
| 纯向量 | **63.75%** | 72.08% | **74.00%** | **63.09%** | 152 ms | 859 ms |
| 混合（向量 + BM25 + RRF） | 61.25% | 68.75% | 70.86% | 59.82% | 151 ms | 446 ms |
| 混合 + 重排 | 64.17% | **77.50–78.33%** | 67.40–67.81% | 59.29–59.54% | 765 ms | 985 ms |

> 📌 表中**带区间的格子就是连跑 3 次的极差**（`hybrid_rerank` 的 R@10 / MRR / nDCG）；R@5 与另外两行是确定值，所以给单值。

> ⚠️ **`vector` 与 `hybrid` 两行是确定值（同输入必得同结果，中间没有非确定性组件）；只有 `hybrid_rerank` 与所有延迟会抖。**
> **原因**：远端 bge-reranker 的服务端打分对同一输入并非逐位确定。**同一语料、同一脚本连跑 3 次**的实测极差为
> R@5 **0.00pp**、R@10 **0.83pp**、MRR **0.0042**、nDCG@5 **0.0025**（R@10 在 77.50% / 78.33% / 78.33% 之间跳）；
> 40 条里有 **12 条的 Top10 顺序被改写**（集合基本不变），其中 2 条的指标真的变了。
> 所以重排那一行请读作 **R@5 64.2% / R@10 77.5–78.3%**，**不要把小数位当精度**。
> 原始逐查询比对留底：[`docs/evidence/rerank_variance.txt`](./docs/evidence/rerank_variance.txt)，可复现脚本 `backend/scripts/rerank_variance.py`。
> 延迟更要当心：n=40 时 **P95 基本由单个离群点决定**（`vector` p95 859 ms 就是某一条 956 ms 拉出来的，
> 它的中位数只有 152 ms）。所以延迟**只用于三组之间的相对比较**，不要当 SLA。
> 复现时请检查报告的 `provider_stats.degraded_calls`：若不为 0，说明该次跑被降级污染，数字不可比。

> ⚠️ **这里最重要的结论是「混合检索没有赢」——而且我们把它原样写出来，没有为了简历去调参凑一个更好看的数。**

### 结论一：重排只在 Recall@10 上有确定收益

`hybrid_rerank` 相对 `hybrid`：**Recall@10 +8.75 to +9.58pp**（68.75% → 77.50%–78.33%）。**重排确实把真正相关的菜从池子中后段捞进了前 10。**

但要说全：它在 Recall@5（64.17% vs 63.75%，仅 +0.42pp）、MRR@10（67.4–67.8% vs 74.00%）、nDCG@5（59.3–59.5% vs 63.09%）上**仍然不如纯向量**。所以准确表述是「**重排修好了召回广度，但没有修好头部精度**」，而且 **MRR / nDCG 的落后幅度远大于 R@10 的领先幅度**——它不是一次全面升级。

### 结论二：等权 RRF 是个结构性缺陷，不是「BM25 有噪声」（**负面结论，也是本次最有价值的发现**）

`hybrid` 比纯向量**全面更差**（R@5 −2.50pp、R@10 −3.33pp、MRR −3.14pp、nDCG@5 −3.27pp）。

**根因（已用逐条三元组定位，不是猜测）**：我一开始以为是「BM25 把垃圾顶进头部」，**这个猜测被数据否定了**。真实机制是一个**纯结构性的不等式**：

```
等权 RRF，k = 60，候选池 Top50
  单通道项上界 = 1/(60+1)  = 0.016393   ← 只被一路召回，哪怕它排第 1
  双通道项下界 = 2/(60+50) = 0.018182   ← 两路都召回，哪怕两路都排第 50
  0.018182 > 0.016393  ⇒  恒成立
```

**只要一道菜两路都进了 Top50，它必然排在所有单通道候选之前**——哪怕它两路都排第 50，也压过某一路的第 1 名。

**7 条回归查询、21 个金标准条目的通道来源**：**双通道 7 / 仅向量 13 / 仅 BM25 0 / 两路均未召回 1**。拉开差距的正是**「仅向量」那 13 个**：向量明明把它们排得很靠前，却因为 BM25 没召回它们，被整片「双通道共识集合」压到后面：

| 查询 | 金标准 | 向量名次 | BM25 名次 | RRF 名次 | R@5 变化 |
| --- | --- | --- | --- | --- | --- |
| 家里只剩鸡蛋和番茄 | 西红柿炒鸡蛋 | **1** | 未召回 | **22** | 0.667 → 0.000 |
| 家里只剩鸡蛋和番茄 | 西红柿鸡蛋汤 | **2** | 未召回 | **23** | |
| 想吃川菜，要麻辣一点 | 麻婆豆腐 | **3** | 未召回 | **17** | 0.667 → 0.333 |
| 想用烤箱做点甜点 | 戚风蛋糕 | **1** | 未召回 | **21** | 0.333 → 0.000 |
| 第二天想带饭，做个凉拌菜 | 凉拌莴笋 | **2** | 未召回 | 4 | 0.667 → 0.333 |

7 条回归查询的 Top10 里 **62/70（88.6%）是双通道共识项**；全量 40 条的 Top5 里双通道占 **92.5%**、Top10 占 **86.5%**（而 BM25-only 全程只贡献了 11/400 个位置）。

**所以准确的结论是**：混合检索的伤害**不是**「BM25 把垃圾顶上来」，而是 **「RRF 只用名次、完全不看通道可靠性」**——BM25 任何一次命中都会把该菜**升格为「共识项」并获得永久优先权**，于是向量单独召回的真值被整体降级。**在 BM25 召回率本就低的语料上，这等价于系统性惩罚向量通道。**

**这是本次评估最有价值的产出**：它证明了「混合检索听起来更高级，但在具体语料上不一定更好」，也说明了**为什么消融实验是必要的**——如果只看「混合 + 重排」的最终数字（Recall@10 最高），会误以为两路都在贡献；拆开才知道**增益全部来自重排，RRF 那一步是负贡献**。

分场景看（Recall@5）：

| 查询类型 | 纯向量 | 混合 | 混合+重排 |
| --- | --- | --- | --- |
| 直接菜名（8 条） | 100.0% | 100.0% | 100.0% |
| 食材组合（8 条） | 89.6% | 81.3% | **100.0%** |
| 场景/耗时（8 条） | **20.8%** | 16.7% | **25.0%** |
| 口味/菜系（8 条） | **50.0%** | 50.0% | 41.7% |
| 工具/做法（8 条） | **58.3%** | 58.3% | 54.2% |

### 结论三：权重敏感性实验——没有任何权重能全指标翻盘

在评估脚本里本地实现加权 RRF（`w_vec/(k+r) + w_bm25/(k+r)`，`w_bm25=1.0` 时与 `rag.fusion.reciprocal_rank_fusion` 输出等价，有单测断言），6 个配置共用同一份候选，横向可比：

| 配置 | Recall@5 | Recall@10 | MRR@10 | nDCG@5 | Top10 双通道占比 |
| --- | --- | --- | --- | --- | --- |
| `w_bm25 = 0.0`（= 纯向量） | **63.75%** | 72.08% | **0.7400** | **0.6309** | 52.0% |
| `w_bm25 = 0.25` | 62.08% | **74.17%** | 0.7127 | 0.6082 | 73.3% |
| `w_bm25 = 0.50` | 62.92% | 71.67% | 0.6935 | 0.6034 | 85.3% |
| `w_bm25 = 1.0`（**当前实现**） | 61.25% | 68.75% | 0.7086 | 0.5982 | 87.3% |
| `w_bm25 = 0.25` + 各通道只取 Top10 | 61.25% | 72.08% | 0.7325 | 0.6091 | 31.5% |
| 等权 + 各通道只取 Top10 | 61.25% | 69.58% | 0.7132 | 0.5980 | 31.5% |

**唯一严格单调的量是「Top10 里双通道共识项占比」：52.0% → 73.3% → 85.3% → 87.3%**——即 BM25 权重越大，头部越被「两路都命中」的菜占满，而向量单独召回的真值越靠后。


**但必须诚实说：指标本身并不严格单调。** 例如 R@5 在 `w=0.5`（62.92%）反而略高于 `w=0.25`（62.08%），MRR 在 `w=0.5`（0.6935）反而低于 `w=1.0`（0.7086）。**40 条样本下 1pp 级别的跳动不能当结论**，所以这里只主张两件有把握的事：

1. **没有一个权重能让所有指标都赢过纯向量。** `w=0.0` 拿下 R@5 / MRR / nDCG 三项；`w=0.25` 只在 R@10 上更好（74.17% vs 72.08%，+2.09pp），代价是 R@5 −1.67pp、MRR −2.73pp。
2. **等权（`w=1.0`，也就是当前实现）在四个指标上有三个是最差的**，且头部被共识项占比最高的 87.3%，**没有任何理由保留它**。

**另外两个反直觉的发现（都有数据支撑）**：

1. **按召回深度归一（各通道只取 Top10）救不了场**：它把双通道集合从 349 项砍到 126 项、共识占比从 87.3% 压到 31.5%，**但 R@5 仍然是 61.25%，一点没变**；代价是把 26 个金标准踢出了候选池（`gold_not_recalled_in_top_n` 从 12 涨到 26），R@10 反而从 68.75% 升到 69.58% 又被截断吃掉。**结论：截断尾部换来的精度收益，被截断掉的召回损失完全抵消了**——想修 RRF 的头部，靠调召回深度是没用的，必须改融合公式。
2. **`w_bm25 = 0.25` 是唯一在 R@10 上胜过纯向量的配置**。所以：**若产品必须保留关键词通道（精确菜名、生僻词兜底），0.25 是有依据的取值；若只追主指标，纯向量最好。**

**当前代码仍用 `w_bm25 = 1.0`（等权），这是已知的、有证据的次优默认值**——改它属于 `rag/fusion.py` 的行为变更，登记在 [`docs/failed-features.md`](./docs/failed-features.md) F15，不在本轮范围内。**我没有为了简历好看去改这个默认值再重跑。**

### 结论四：场景/耗时类查询是三组共同的短板（16.7%–25.0%）

即使最好的配置也只有 Recall@5 = 25.0%。当次评估数据库里 `recipes.time_minutes` **372 行全为 NULL**，`recipes.tools` 只有 82 行非空，结构化时间过滤因此无法工作。**需要修正原因归属**：至少有菜谱简介明确写了总时长（鳊鱼炖豆腐「约需 40 分钟」），解析器却固定写空；简介本身参与卡片检索，所以不能说语料完全没有时间信号。以上是历史评估结果的解释修正，指标数字未重测。

**这条正好说明消融的另一个价值**：它把「算法问题」和「数据问题」分开了。

### 为什么 Recall@5 只有 63.75%，离 85% 差 21pp？

**如实说：目标没达到，而且差距的主要来源不是排序算法。** 按贡献排序：

1. **金标准集不完整（最大项）**：每条查询只标 1–3 个相关菜，而库里存在大量同样满足约束的合法答案。启发式估算显示 Top10 里「未标注但按查询自身约束看确实合法」的占比很高（若标注完整，precision@10 约为 54.6% / 56.2% / 65.8%），**所以 Recall 被系统性低估**。换言之：**指标偏低有一部分是标注问题，不是系统问题**——这是必须承认的方法论局限。
2. **scene / taste 类缺结构化元数据**：见结论四。
3. **剩下的才是排序算法问题。**

**我们没有为了接近 85% 而调参或改标注。** 这份 README 早期版本曾写「Recall@5 ≥ 85%」——那是**没有测量支撑的目标值**，现已改成实测值加差距归因。

### 复现与局限（必须同时说）

- 复现命令与数据结构见 [`data/eval/queries.yaml`](./data/eval/queries.yaml)；报告（含每条查询的 `evidence_top10` / `channel_sources` / `latency_ms`）在 `data/eval/reports/*.json`。
- **金标准已用脚本校验**：`python -m scripts.eval --validate-only` 会确认每一条标注的菜名都真实存在于库中（当前 40/40 通过；库中 372 行 / 371 个不同菜名，刻意排除同名重复的 `陈皮排骨汤`）。
- **40 条是小样本**，只能做**相对比较**（哪组更好），不能当绝对质量结论；单条差异即可造成 1–2pp 波动。
- **单人标注**，无标注者间一致性（Kappa）数据。
- **相关度是二值**（相关 / 不相关），nDCG 里相关度都按 1 计，所以 nDCG 与 Recall 高度相关、信息量有重叠。
- 未做显著性检验（小样本 + 单标注，做不了）。
- 延迟在**本机 + Docker + 公网 SiliconFlow** 上测得，含网络往返；换机器 / 换网关数字会变。
- ⚠️ **本表数字的"有效期"绑定在语料上**：改解析器 / 改切分 / 换 embedding 模型都会改变卡片文本 → 向量 → 排序。**每次重灌必须重跑 `scripts/build_index` 并全量重跑评估**，流程写在 [`docs/CONVENTIONS.md`](./docs/CONVENTIONS.md) §4.6。**本次数字就是重灌后的结果**（重灌前 `hybrid` R@5 是 59.58%，现在是 61.25%——不是回退，是卡片文本变干净了）。

**证据在哪（不只在 gitignore 的 `.tmp/` 里）**：`data/eval/reports/*.json` 是可重建产物、不入库（4 份合计 ~920 KB），所以关键结论都有一份**入库的原始证据 + 可复现脚本**：

| 结论 | 入库证据 | 复现脚本 |
| --- | --- | --- |
| 三组指标 / 延迟 / 分场景 | [`docs/evidence/eval_reports_summary.json`](./docs/evidence/eval_reports_summary.json)（含报告 SHA256 前 16 位，可逐字段对账） | `scripts.eval --mode all` + `scripts.summarize_eval_reports` |
| 重排跑间抖动（R@10 77.50–78.33%） | [`docs/evidence/rerank_variance.txt`](./docs/evidence/rerank_variance.txt) | `scripts.rerank_variance` |
| 通道归因（双通道 7 / 仅向量 13 / 仅 BM25 0 / 未召回 1） | [`docs/evidence/channel_attribution.txt`](./docs/evidence/channel_attribution.txt) | `scripts.channel_attribution` |
| 端到端 5 场景（含误报留档） | [`e2e_run2.txt`](./docs/evidence/e2e_run2.txt) / [`e2e_run3.txt`](./docs/evidence/e2e_run3.txt) / [`e2e_run1_OLD_PROBE_field_bug.txt`](./docs/evidence/e2e_run1_OLD_PROBE_field_bug.txt) | `scripts.e2e_probe` |
| 解析噪声清理前后 | [`import_report.before.json`](./docs/evidence/import_report.before.json) / [`import_report.after.json`](./docs/evidence/import_report.after.json) | `scripts.import_howtocook` |

> 连那次**「探针写死字段名把 5 条候选报成 0 条」的误报输出**也留在仓库里（`e2e_run1_OLD_PROBE_field_bug.txt`）——它比删掉更有价值，因为它记录了"我们差点被自己的脚本骗过"。

指标口径：

- **Recall@k**：标注的相关菜谱里，有多少出现在 Top-k。
- **MRR@10**：第一条命中的倒数排名均值。
- **nDCG@5**：按位置折损的相关度增益，标注相关度视为 1。
- **延迟**：单条查询的检索端到端耗时（含 embedding 与重排网络往返），**计时前各通道预热 1 次**（所以是热路径，不含连接池 / HTTP 建连）。用中位数与 P95 而非平均值——检索延迟是右偏分布，平均值会被长尾拉偏。

### 端到端接口实测（`POST /recommend`，真机）

**下表是 2026-10-11 数据重灌 + 重建索引后的实测**，延迟为**连跑 3 轮的真实 min–max**（聚合脚本：`backend/scripts/e2e_latency_summary.py`；原始输出：[`e2e_run2.txt`](./docs/evidence/e2e_run2.txt) / [`e2e_run3.txt`](./docs/evidence/e2e_run3.txt) / [`e2e_run4.txt`](./docs/evidence/e2e_run4.txt)；可复现：`backend/scripts/e2e_probe.py`）：

| 场景 | 延迟（3 轮 min–max，极差） | 结果 |
| --- | --- | --- |
| `{"query":"西红柿炒鸡蛋"}` | **9.2 – 12.0 s**（极差 2.8 s） | 3 条推荐（西红柿炒鸡蛋 / 西红柿鸡蛋挂面 / 西葫芦炒鸡蛋），`node_path=[parse,search,generate,validate]` |
| `{"query":"20 分钟能搞定的家常菜"}` | **2.1 – 2.3 s**（极差 0.2 s） | `recommendations=[]`，`no_solution_reason="no_candidates_under_constraints"`，`node_path=[parse,search,no_solution]`（3 轮完全一致） |
| `{"query":"清淡的汤，不要辣"}` | **7.6 – 9.2 s**（极差 1.6 s） | 3 条推荐（金针菇汤 / 生汆丸子汤 / 朱雀汤），`degraded=true`，`degradations=["recommendation_shortfall"]`（3 轮都触发） |
| `POST /recipes/search {"query":"有鸡蛋和番茄","top_k":5}` | **0.37 – 0.44 s**（极差 70 ms） | 5 条候选（番茄牛肉蛋花汤 / 意式香肠北非蛋 / 罗宋汤 / 鸡蛋三明治 / 温泉蛋），`degraded=false`（3 轮结果完全一致） |
| `{"query":""}` | **3 – 18 ms** | 422 + 统一错误信封（`query` 有 `min_length=1`） |

**延迟为什么给区间而不是一个数**：同一份代码、同一份语料，`西红柿炒鸡蛋` 三轮跑出 9.2 / 12.0 / 11.5 s——**2.8 s 的极差全部来自 LLM 生成阶段**（同一批跑里纯检索三轮只差 70 ms）。给一个三位小数的"精确值"是假精度，所以这里给区间。同理，**`degraded` 也不稳定**：三轮里两轮 `degraded=false`、一轮 `degraded=true` + `recommendation_shortfall`——因为模型有时只返回 2 条推荐，触发补齐。这是**真实存在的非确定性**，不是 bug，也正因如此我们才把 `degraded` / `degradations` 做成响应字段而不是只写日志。

> 上面「清淡的汤」那行的第 3 条 `reason` 是个**真实可讲的细节**：`命中你的需求「清淡的汤，不要辣」的混合检索第 3 名结果`。它暴露了两条不同的生成路径——LLM 正常返回的理由是人话，补齐的那条是规则模板。这正是 `degraded=true` 想传达的信息，而不是把它藏起来（登记为 `docs/failed-features.md` F19）。

> ⚠️ **延迟 8–12 s 是当前实现最大的工程欠账**：`parse` 与 `generate` 是两次**串行** chat 调用（合计 ≈ 8–11 s）。这不是检索慢（纯检索 0.4 s），而是 LLM 往返慢 + 串行。压到 3 s 内的做法（管道化、或把 parse 换成规则/小模型）属于产品取舍，**当前没有做**，登记在 [`docs/failed-features.md`](./docs/failed-features.md) F14。

> 📌 表里**每一行都带极差**，而不是只有一行带区间——因为读者需要知道**哪些数字可比、哪些不可比**。

---

## 🧱 技术栈

只列**实际在用**的（`pip`/`npm` 里装了、代码里调了）：

| 层级 | 技术 | 实际用途 |
| --- | --- | --- |
| **AI 编排** | LangGraph 1.2 + langchain-core | `backend/agents/` 的状态机闭环 |
| **后端** | FastAPI 0.115+ + Pydantic v2 | 分层 API + 配置 + 错误信封 |
| **数据库** | PostgreSQL 16 + pgvector 0.8 | 13 张表、HNSW 向量索引、GIN tsv 索引 |
| **Embedding** | BAAI/bge-m3（SiliconFlow / 本地兜底） | 1024 维，卡片级 + 步骤级 |
| **重排** | BAAI/bge-reranker-v2-m3 | RRF 之后二次排序，失败降级回 RRF |
| **LLM** | DeepSeek-V3（OpenAI 兼容） | 查询解析 + 推荐理由生成，温度 0.1 |
| **ORM / 迁移** | SQLAlchemy 2.x（async）+ Alembic | `infra/tables.py` 是 schema 唯一事实源 |
| **中文检索** | jieba + rank-bm25 | tsv 与 BM25 共用同一分词入口 |
| **可观测** | Langfuse（Cloud，日本区） | 观察名是契约常量；key 缺失降级为本地日志 |
| **前端** | Next.js 14 App Router + TS strict + Tailwind v4 | Natural Organic token 写在 `@theme`，无 `tailwind.config.js` |
| **前端状态** | TanStack Query（服务端状态）+ Zustand（UI 状态） | 两者严格分离，不混用 |
| **容器化** | Docker Compose | `postgres` + `redis` 默认起；`app` profile 挂前后端 |

**已规划但尚未引入**（写在前面的技术栈清单里、代码里还没用，不计入"在用"）：

| 技术 | 计划用途 | 现状 |
| --- | --- | --- |
| RAGAS | 生成侧四项指标（Faithfulness / Answer Relevancy / Context Precision / Context Recall） | 未安装、未使用 |
| Sentry | 异常上报 | 配置项已留，未接入 |
| Redis | 限流与缓存 | 容器已起，代码未用 |
| shadcn/ui | 组件库 | 未初始化，当前是手写 Tailwind |
| PostgresSaver | 会话状态持久化 | 表和依赖已就位，图未接线 |

> 完整技术栈清单与 AI 编码约束见 [`docs/TECH_STACK.md`](./docs/TECH_STACK.md)。

---

## 🧭 全局约定（唯一口径）

> 跨文档冲突已在本节统一。任何文档、代码或 AI 生成内容与此处不一致时，**以本节为准**。

| 议题 | 统一结论 |
| ---- | -------- |
| **登录** | 邮箱 + 密码 + JWT（注册 / 登录 / 登出 / 刷新）；**不做第三方 OAuth**。🚧 未实现 |
| **目标用户** | **面向所有普通人，不做医学人群细分**（GI / 钠 / 蛋白质等医学营养数据不可得）。约束只来自用户自己的忌口、时间、厨具与口味 |
| **画像归属** | `backend/domain/profiles/`（`domain` 是唯一无 IO 层） |
| **接口定义** | 所有 Protocol 集中在 `domain/ports.py`（`RecipeRepository` / `LLMClient` / `EmbeddingClient` / `RerankClient` / `Retriever`），实现在 `infra/`、`rag/` |
| **前端目录** | 不使用 `src/` 前缀：`app/`、`components/ui/`、`lib/` 直接放在 `frontend/` 下 |
| **渲染策略** | 推荐 / 对话 / 购物清单 = CSR（client + TanStack Query）；落地页 / 菜谱详情 / legal = Server Component（SSR） |
| **样式** | Natural Organic（`docs/UI_STYLE.md`）；Tailwind v4 CSS-first，token 定义在 `app/globals.css` 的 `@theme`，不生成 `tailwind.config.js`。右上角可调字体、字号、页面排列与暖色主题，设置保存在浏览器本地 |
| **数据源** | 菜谱来自 HowToCook（Unlicense / 公有领域，可自由分发与商用）。372 道菜谱 + 354 张成品配图收录进 `data/raw/howtocook/` 并随仓库提交；上游完整 clone（623 MB）不入库 |
| **模型调用** | **远程优先、本地兜底**：Embedding / Rerank 默认走 SiliconFlow 等 OpenAI 兼容接口，失败或离线时回落本地推理；实现在 `infra/`，接口在 `domain/ports.py`，trace 里标注实际走的是哪条路。⚠️ 本地兜底需装 `sentence-transformers`，**当前环境未安装** |
| **硬约束归属** | 忌口 / 时间 / 厨具**下推到检索层**（SQL WHERE / 向量过滤），禁止「先检索再过滤」；LLM 不参与硬约束判定。忌口按食材本质处理：标准名、同义名及含该名称的部位/衍生产物均排除；SQL 同时检查菜名、原料原文与已映射食材，不能只依赖入库时的归一化。跨食材有歧义的短别名不做宽泛包含匹配（如「里脊」不能因此把牛里脊算猪肉） |
| **无解语义** | 硬约束下无候选时，**显式返回 `no_solution_reason`**，绝不返回违规菜谱、绝不编造 |
| **时长的现状** | ⚠️ 当前 `recipes.time_minutes` 全为 NULL，是解析器固定写空且推荐校验强制清空的结果，**不能据此声称上游没有时长**。例如鳊鱼炖豆腐简介明确写「从备料到完成约需 40 分钟」。仅步骤时长不能当总时长。推荐卡片保留明示的原文时长、难度、预估热量和真实图片；完整原料、工具、步骤与附加说明在独立菜谱详情页展示。结构化时间筛选尚未恢复，后端显式时间约束仍严格排除 NULL。详见 F12 |
| **会话存储** | `PostgresSaver` 是会话状态唯一事实源；Redis 只做缓存与限流。🚧 未接线 |
| **规则** | YAML 文件（`data/rules/`），不入库，可版本控制。🚧 目录尚未创建 |
| **可观测** | Langfuse Cloud 免费版（日本区，Python SDK v4.17+）；未配置 key 时自动降级为本地结构化日志；**读取 trace 走 `/api/public/v2/observations`**（旧 `/api/public/traces` 对新组织返回 410） |
| **评估** | `scripts/eval.py` 手动跑；稳定后再入 CI。**指标只写实测值，不写目标值** |
| **语音** | Web Speech API（客户端）。📋 未开始 |
| **工期** | 原计划 4-6 周；**2026-10-11 起收敛为 3 周聚焦核心 Agent 闭环**（详见 [路线图](#-路线图)） |

**文档地图**：`README.md`（本文件）· `docs/PRD.md` · `docs/TECH_STACK.md` · `docs/ARCHITECTURE.md` · `docs/CONVENTIONS.md` · `docs/UI_STYLE.md` · `docs/DATA_SOURCES.md` · `docs/INTERVIEW.md`（面试深挖问答）· `TODO.md` · `docs/failed-features.md` · `docs/mistakes.md`

---

## 🏗️ 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                      前端 (Next.js)                      │
│      / (落地页)    /recommend (推荐)    /dashboard       │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP / JSON
┌──────────────────────────▼──────────────────────────────┐
│                    API 层 (FastAPI)                      │
│        /health  /version  /recommend  /recipes/search   │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                   Service 层 (业务编排)                   │
│              RecommendService（根 trace）                │
└───────┬──────────────────┬──────────────────┬───────────┘
        │                  │                  │
┌───────▼──────┐  ┌────────▼────────┐  ┌─────▼──────────┐
│   Domain     │  │     Agents      │  │      RAG       │
│ 引用校验      │  │  LangGraph 闭环  │  │  混合检索+重排  │
│ 食材归一化    │  │  parse/search/  │  │  切分/索引      │
│ 领域模型      │  │  generate/      │  │  RRF 融合       │
│              │  │  validate       │  │                │
└───────┬──────┘  └────────┬────────┘  └─────┬──────────┘
        │                  │                  │
┌───────▼──────────────────▼──────────────────▼───────────┐
│              Infra 层 (DB / LLM / 观测)                  │
│  PostgreSQL + pgvector | LLMClient | Embedding | Rerank │
│                Langfuse | 配置 | 结构化日志              │
└─────────────────────────────────────────────────────────┘
```

**分层依赖规则**：`api → services → domain / agents / rag → infra`，单向不可逆，`domain` 不依赖任何层。

**Agent 闭环（当前实现的最小版）**：

```
START → parse ──▶ search ──┬─(0 候选)─▶ no_solution ─▶ END
                           └─(有候选)─▶ generate ─▶ validate ─▶ END
```

- `parse`：LLM 把自然语言翻译成硬约束；**解析失败降级为"用原查询、不加约束"**，不中断。
- `search`：硬约束下推到 SQL，向量与 BM25 各自在允许集合内召回，RRF 融合，可选重排。
- `generate`：LLM 只从候选里挑，输出 JSON；**解析失败降级为规则模板生成**。
- `validate`：`domain/citations.py` 校验每个 `recipe_id` 必须精确命中候选，不符的丢弃。

> 详细架构说明见 [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md)。

---

## 📁 目录结构

```
mealcompass/
├── backend/
│   ├── api/                  # 路由层（薄路由，≤10 行）
│   ├── services/             # 业务编排
│   ├── domain/               # 领域层（模型、引用校验、食材归一化、Protocol）
│   ├── agents/               # LangGraph 状态机与节点
│   ├── rag/                  # 检索、重排、切分、融合、分词
│   ├── infra/                # DB、LLM/Embedding/Rerank 客户端、观测
│   ├── core/                 # 配置、日志、异常
│   ├── scripts/              # 导入、入库、建索引、评估、冒烟
│   ├── tests/                # 单测 + 集成测试
│   ├── migrations/           # Alembic
│   └── main.py
├── frontend/
│   ├── app/                  # Next.js App Router
│   ├── components/           # UI 组件
│   └── lib/                  # API 客户端、query client、hooks、stores
├── data/
│   ├── raw/howtocook/        # 上游原始 markdown + 配图（只读）
│   ├── recipes/              # 解析产物（gitignore，可重建）
│   ├── ingredients/          # 食材归一化词典
│   └── eval/                 # 评估集与报告
├── docs/                     # PRD / 技术栈 / 架构 / 规范 / UI / 面试问答
├── docker-compose.yml
└── README.md
```

---

## 🚀 快速开始

### 前置要求

- Docker & Docker Compose
- Python 3.11+ 与 [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+ 与 `pnpm`
- 一个 OpenAI 兼容的 API Key（推荐 [SiliconFlow](https://siliconflow.cn)，本项目的 embedding / rerank / chat 都在它上面实测过）

### 一键启动依赖 + 建库 + 灌数据

```bash
# 1. 起依赖（postgres + redis）
docker compose up -d

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 LLM_API_KEY 等（不填也能跑，只是没有 LLM 与 trace）

# 3. 后端依赖
cd backend
uv sync --extra dev

# 4. 建表
.venv/Scripts/python.exe -m alembic upgrade head     # Windows
# .venv/bin/python -m alembic upgrade head           # macOS / Linux

# 5. 解析原始数据并灌库（幂等，可重复跑）
.venv/Scripts/python.exe -m scripts.import_howtocook  # markdown → JSON
.venv/Scripts/python.exe -m scripts.seed_recipes      # JSON + 食材词典 → PostgreSQL
.venv/Scripts/python.exe -m scripts.build_index       # 双层向量索引（372 卡片 + 3806 步骤）

# 6. 起后端
.venv/Scripts/python.exe -m uvicorn main:app --reload
```

访问：

- 后端 API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

### 前端

```bash
cd frontend
pnpm install
pnpm dev
```

访问 http://localhost:3000 ，推荐页在 `/recommend`。

后端默认允许 `http://localhost:3000` 与 `http://127.0.0.1:3000` 跨域访问。若前端换了端口或域名，在根环境配置中设置 `CORS_ALLOW_ORIGINS` 为 JSON 数组（例如 `CORS_ALLOW_ORIGINS=["http://localhost:3001"]`），重启后端后生效。这里填的是**浏览器前端地址**，`NEXT_PUBLIC_API_BASE_URL` 填的是**后端地址**。

遇到 `OPTIONS /recommend 405` 或状态接口显示 `network_error, status=0` 时，检查跨域配置并重启后端；仅在终端访问 `/health` 成功不能证明浏览器可跨域读取。Windows 下若 Docker 报 `dockerDesktopLinuxEngine ... The system cannot find the file specified`，先启动 Docker Desktop 并等待 Linux 引擎就绪，再执行 `docker compose up -d`；用 `docker compose ps` 确认 postgres / redis 为 `healthy`。`/health` 仅报告应用进程状态，不代表数据库已就绪。

### 一键启动（Windows，日常最省事）

不想每次手敲两条命令，直接双击仓库根目录的 **`start_mealcompass.bat`**：它会自检环境 → 起后端 + 前端 → 等两个服务真正就绪 → 在终端打印下面这些可直接点击的网址。

```
  推荐页面   http://localhost:3000/recommend
  首页       http://localhost:3000
  后端 API   http://localhost:8000/docs
  健康检查   http://localhost:8000/health
```

命令行里也可以带子命令：

| 命令 | 作用 |
| --- | --- |
| `start_mealcompass.bat` | 启动前后端并打印网址（默认） |
| `start_mealcompass.bat check` | 只做自检，不启动任何服务 |
| `start_mealcompass.bat status` | 看两个端口与本脚本启动记录的状态 |
| `start_mealcompass.bat stop` | 停止上一次由它启动的服务 |
| `start_mealcompass.bat open` | 启动并自动打开浏览器 |
| `start_mealcompass.bat reload` | 启动并开启后端热重载（默认关闭，见下） |

**它会自动排查的常见问题**（每条都会打印「可能原因与修复建议」，并把日志尾巴贴出来）：

- 缺后端虚拟环境 / 缺依赖 / 缺 `frontend/node_modules` / 没装 Node 或 pnpm；
- 端口被别的程序占用（打印占用进程，提示换端口或 `stop`）；
- 数据库连不上（用 TCP 直连判定，连不上会尝试 `docker compose up -d postgres`）；
- 上一次启动的残留进程（自动清理；清理不掉就保留 `pids.json` 下次再试）；
- 日志文件被上一次的进程占着（自动改用带时间戳的日志名，不会因此启动失败）；
- 起不来时按关键字匹配日志并给出修复建议（端口占用 / 缺依赖 / 数据库 / 具名管道被拒 / 配置格式等）。

日志写在 `.tmp\launch\`。停止服务：窗口里按 `Ctrl+C`、直接关闭窗口，或 `start_mealcompass.bat stop`。

**关于热重载**：后端 `--reload` 依赖 multiprocessing 具名管道，在受限环境（沙箱 / 部分安全软件）会被直接拒绝、反而起不来，所以**默认关闭**；需要热重载时用 `start_mealcompass.bat reload`。前端 `next dev` 自己就带热重载；若该环境连 `next dev` 的 fork 都拒绝（`spawn EPERM`），脚本会自动降级为 `pnpm build` + `next start` 生产模式，功能一致、只是没有热重载。

### 跑评估（三组消融）

```bash
cd backend
.venv/Scripts/python.exe -m scripts.eval --mode all
```

---

## 🔧 环境变量

| 变量 | 说明 | 示例 |
| --- | --- | --- |
| `DATABASE_URL` | PostgreSQL 连接串 | `postgresql+asyncpg://mealcompass:mealcompass@localhost:5432/mealcompass` |
| `REDIS_URL` | Redis 连接串（当前代码未使用） | `redis://localhost:6379/0` |
| `LLM_API_KEY` | LLM / Embedding / Rerank 的 API Key | `sk-...` |
| `LLM_BASE_URL` | OpenAI 兼容接口基址 | `https://api.siliconflow.cn/v1` |
| `LLM_MODEL` | Chat 模型名 | `deepseek-ai/DeepSeek-V3` |
| `EMBEDDING_MODEL` | Embedding 模型（须为 1024 维） | `BAAI/bge-m3` |
| `RERANKER_MODEL` | 重排模型 | `BAAI/bge-reranker-v2-m3` |
| `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` | 可选：embedding / rerank 单独走别的网关 | — |
| `ENABLE_LOCAL_FALLBACK` | 是否启用本地兜底（需装 `sentence-transformers`） | `true` |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | Langfuse 凭证（可留空，自动降级） | — |
| `JWT_SECRET` | JWT 密钥（`APP_ENV=prod` 时必填，否则启动即失败） | — |
| `NEXT_PUBLIC_API_BASE_URL` | 前端访问的后端基址（唯一暴露给浏览器的变量） | `http://localhost:8000` |

> 完整变量见 `.env.example` 与 `frontend/.env.example`。

---

## 🧪 测试

```bash
# 后端：Lint + 格式化 + 测试（覆盖率只统计生产代码）
cd backend
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider \
  --cov=domain --cov=rag --cov=infra --cov=core --cov=api \
  --cov=agents --cov=services --cov=main --cov-fail-under=70

# 前端：类型检查 + Lint + 构建
cd frontend
pnpm typecheck && pnpm lint && pnpm test:unit && pnpm build
```

**覆盖率口径说明**：只统计生产代码（`domain/rag/infra/core/api/agents/services/main.py`），**不把 `tests/` 与 `scripts/` 算进去**——否则覆盖率会被测试自身稀释。门禁 `--cov-fail-under=70`。

**当前本机基线（2026-10-13）**：

```
$ .venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --cov=domain --cov=rag --cov=infra \
    --cov=core --cov=api --cov=agents --cov=services --cov=main --cov-report=term
TOTAL                              1890     93    95%
589 passed, 4 skipped in 60.84s
$ .venv\Scripts\python.exe -m ruff check .          → All checks passed!
$ .venv\Scripts\python.exe -m ruff format --check . → 94 files already formatted
$ .venv\Scripts\python.exe -m scripts.check_docs_consistency
[OK] README 与 docs/evidence 全部一致
     对账报告 4 份：ablation_weight.json(49de57b9eb18f383), hybrid.json(60cacb548cedb9d8),
                    hybrid_rerank.json(012b3a433c992ddc), vector.json(e637d1eaba54bb1b)
     指标格 12 个全部覆盖；区间格子与跨轮极差一致；来源标注全部存在
```

覆盖率**当前最低的三个模块也一并说清，不藏**：

| 模块 | 补齐前 | 现在 | 说明 |
| --- | --- | --- | --- |
| `infra/recipe_details.py` | — | **52%** | 独立详情页新增后，数据库读取成功路径已有覆盖，真实 SQL 映射分支仍需后续集成测试补强 |
| `infra/rerank_client.py` | — | **88%** | 远端和本地模型客户端的异常分支仍有少量环境相关缺口 |
| `agents/jsonx.py` | — | **89%** | 脏 JSON 解析已经覆盖常见边界，复杂嵌套异常文本仍留有分支缺口 |

> `4 skipped` 是**环境性跳过**（本地兜底模型 `sentence-transformers` 未安装、真远程 smoke 需 key），不是失败；每一条的跳过原因写在测试里。

沙箱环境跑测试的两条规矩：`$env:TEMP` 指到仓库内、不要用 `tmp_path` fixture（见 `AGENTS.md` §5.1）。

---

## 🗺️ 路线图

**2026-10-11 起收敛为 3 周聚焦**（原 4-6 周全量计划见 `docs/HISTORICAL_FULL_PLAN.md`）：

| 周 | 目标 | 出口条件 |
| --- | --- | --- |
| **Week 1** | 评估与安全基线 | ✅ 40 条评估集 + 三组消融实测数字；✅ 引用校验接入闭环 |
| **Week 2** | Agent 后端闭环 | ✅ `parse → search → generate → validate` 真机跑通；✅ 无解显式返回；✅ 降级路径有测试 |
| **Week 3** | 演示、证据与求职材料 | ✅ `/recommend` 页面可用；✅ README 数字全部可复现；✅ 面试问答方案（`docs/INTERVIEW.md`） |

**明确不做**（三周内）：注册登录、购物清单、一周菜单、烹饪模式、语音、长期记忆、多智能体、付费。

> 依据：Agent 后端实习岗最看重的是"**一条能讲透的完整链路 + 可测量的证据**"，而不是页面数量。

---

## 📚 文档索引

| 文档 | 说明 |
| --- | --- |
| [`docs/PRD.md`](./docs/PRD.md) | 产品需求文档（功能列表、验收标准） |
| [`docs/TECH_STACK.md`](./docs/TECH_STACK.md) | 技术栈清单与 AI 编码约束 |
| [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) | 架构（分层、模块、数据模型、接口） |
| [`docs/CONVENTIONS.md`](./docs/CONVENTIONS.md) | 开发规范（分层 / 测试 / CI / Git） |
| [`docs/UI_STYLE.md`](./docs/UI_STYLE.md) | 前端 UI 风格（Natural Organic） |
| [`docs/DATA_SOURCES.md`](./docs/DATA_SOURCES.md) | 数据来源、字段与许可 |
| [`docs/INTERVIEW.md`](./docs/INTERVIEW.md) | **面试深挖问答方案**（每个技术点的问题、答案、与代码位置） |
| [`docs/failed-features.md`](./docs/failed-features.md) | 未完成功能与环境受限项登记（不假装可用） |
| [`docs/mistakes.md`](./docs/mistakes.md) | 踩坑与解决过程记录 |
| [`TODO.md`](./TODO.md) | 当前三周计划与后续立项入口 |
| [`docs/HISTORICAL_FULL_PLAN.md`](./docs/HISTORICAL_FULL_PLAN.md) | 三周聚焦前的完整产品计划归档（不计入当前进度） |

---

## 🤝 贡献指南

1. Fork 本仓库
2. 创建功能分支 `git checkout -b feature/xxx`
3. 提交前确保 `ruff`、`pytest`、`pnpm typecheck && pnpm lint && pnpm test:unit && pnpm build` 全绿
4. 提交 PR，描述变更内容与原因
5. 行为变更必须同步更新文档与 `docs/mistakes.md`

---

## 📄 许可证

本项目代码采用 [MIT](./LICENSE)。
菜谱数据来自 [HowToCook](https://github.com/Anduin2017/HowToCook)，其许可为 **Unlicense（公有领域）**，可自由分发与商用。

---

**⚠️ 免责声明**：MealCompass 提供的推荐仅供参考，不构成医疗或营养建议。有特殊饮食需求者请咨询专业人士。
