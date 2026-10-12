![1791806298254](image/AGENTS/1791806298254.png)

# AGENTS.md・MealCompass 的 AI 协作规范

> **本文件是所有 AI 编码工具（Cursor / Claude Code / Codex / DSH / Copilot 等）在本仓库工作的第一入口。**
> 人类贡献者请先读
>
> [README.md](./README.md)
>
> 与
>
> [docs/CONVENTIONS.md](./docs/CONVENTIONS.md)
>
>
> 本文件若与
>
> `docs/`
>
> 冲突，以
>
> `README.md`
>
> 的「全局约定唯一口径）」为准；发现冲突
>
> **先修文档再写代码**
>
> 。

---

## 0. 三条铁律

1. **先读文档，再动代码。** 不许凭记忆实现；动手前按 §1 的清单把相关文档读完。
2. **口径只有一个。** `README.md` → 「全局约定（唯一口径）」是唯一事实源，任何文档 / 代码与它不一致都以它为准。
3. **每次修改必须自动收尾。** 跑测试 → 同步文档与 TODO → 记录 `docs/mistakes.md` → `git commit` → 按 §5.4 格式汇报。**没做收尾的改动视为未完成。**

---

## 1. 动手前的阅读顺序

| 顺序 | 文件                                                | 什么时候必读                                   |
| ---- | --------------------------------------------------- | ---------------------------------------------- |
| 1    | [README.md](./README.md) → 「全局约定（唯一口径）」 | **每次任务开始必读**                     |
| 2    | [TODO.md](./TODO.md)                                 | 每次任务开始必读（确认任务编号与验收标准）     |
| 3    | [docs/PRD.md](./docs/PRD.md)                         | 涉及功能范围、验收标准（DoD）时                |
| 4    | [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)       | 涉及目录、模块、数据模型、接口时               |
| 5    | [docs/TECH\_STACK.md](./docs/TECH_STACK.md)          | 引入依赖、选型、版本锚定时                     |
| 6    | [docs/CONVENTIONS.md](./docs/CONVENTIONS.md)         | **写任何代码前必读**                     |
| 7    | [docs/UI\_STYLE.md](./docs/UI_STYLE.md)              | 写任何前端界面时                               |
| 8    | [docs/DATA\_SOURCES.md](./docs/DATA_SOURCES.md)      | 涉及外部数据、新增数据源时                     |
| 9    | [docs/mistakes.md](./docs/mistakes.md)               | **每次任务收尾必读**（先看有没有同类坑） |

> 任务相关但文档没写清楚的，
>
> **先问人，不要猜**
>
> 。

---

## 2. 项目一句话与环境事实

* **做什么**：面向所有普通人的菜谱推荐 Agent —— 混合检索（向量 + BM25 + RRF + 重排）+ LangGraph 编排 + 规则引擎硬约束。
* **技术栈**：Python 3.11+ / FastAPI / Pydantic v2 / PostgreSQL 16 + pgvector / LangGraph / Next.js 14 + TS + Tailwind v4 / Langfuse。
* **当前阶段**：**三周聚焦计划 W1–W3 已完成**（评估基线 → Agent 闭环 → 演示与求职材料），详见 `TODO.md` §0.5；原 4-6 周全量计划（§3-§7）为历史清单，未勾选项属**主动推迟**（登记在 `docs/failed-features.md`）。实测数字见 `README.md` 的「评估结果」。
* **环境约束（Windows 沙箱）**：

  * **只有 Python 能联网**：`curl`、`git clone` 会失败（schannel 凭证问题），下载一律用 Python（`urllib` / `httpx`）。
  * 工作区外的路径、以及在沙箱授权之前就存在的旧目录，可能写入 / 删除被拒 —— 遇到就**如实报告给人类**，不要反复重试。
  * `git` 写操作可能与正在运行的 IDE 抢占 `index.lock`，失败就说明情况。

---

## 3. 不可逾越的边界

* ❌ **不做医学人群细分**，不做 GI / 钠 / 蛋白质等医学营养数值门槛（数据不可得，且不构成医学建议）。
* ❌ 不做第三方 OAuth 登录（MVP 仅邮箱 + JWT）、不做 UGC 社区、不做外卖下单、不做移动端原生 App。
* ❌ 不引入 `docs/TECH_STACK.md` 清单外的依赖。
* ❌ 不在 `api/` 层写业务逻辑，不在 `domain/` 层做 IO，不让 LLM 参与硬约束判定。
* ❌ **不编造数据**：上游没有的字段留 `None` 并保留原文，绝不猜数字。
* ❌ 不提交密钥（`.env` / `langfuse.txt` 已在 `.gitignore`），不把敏感数据写进 trace。
* ❌ 不修改 `HowToCook/` 上游原始文件（只读；要改就改 `data/raw/howtocook/` 副本）。

---

## 4. 写代码时的硬性约定（摘自 `docs/CONVENTIONS.md`）

* **分层**：`api → services → domain / agents / rag → infra`，单向不可逆；`domain` 不依赖任何层。
* **接口先行**：所有 Protocol 集中在 `backend/domain/ports.py`，实现在 `infra/`、`rag/`。
* **模型**：菜谱等领域模型放 `backend/domain/models/`；对外接口一律 Pydantic v2（`model_dump()`，禁 `.dict()`）。
* **类型注解全覆盖**；ruff `line-length=120`、`target py311`、`select=["E","F","I","UP","B","SIM"]`。
* **观察名是契约**：只能取 `backend/infra/observability.py` 的 `SpanName` 常量，禁止在调用点手写字符串；LLM 调用必须记成 `generation` 且带 `model` + `usage_details`。
* **前端**：不用 `src/` 前缀；Tailwind v4 CSS-first（`app/globals.css` 的 `@theme`）；shadcn/ui 主题必须映射到 `docs/UI_STYLE.md` 的 Natural Organic 调色板；禁 `any`、禁 `@ts-ignore`。
* **检索**：硬约束下推到检索层，不在检索后过滤；生成必须引用真实 `recipe_id`。
* **自主交付**：对已明确的任务，AI 应自行判断技术方案与取舍并完成端到端交付；除非存在会改变产品范围、数据安全或不可逆操作的真正歧义，不反复向人类确认中间方案。最终必须同步 `TODO.md`、`docs/mistakes.md` 与本文件要求，运行验证并如实汇报结果。

### 4.1 多智能体协作纪律（2026-10-11 起，**违反即视为未完成**）

> 下面这些不是假想规则，都是本次三周聚焦里**实际踩过的坑**，逐条记录在 `docs/mistakes.md`。

* **共享任务板的 `status` 是唯一事实源。** 派单、解锁、宣告"某个依赖已完成"之前，**必须先 `team_task_list` 核对状态**，禁止靠记忆、印象或某人的一次汇报推断。把 `in_progress` 说成 `completed` 会直接诱发下游的无效劳动甚至数据事故。
* **write scope 对**所有**写者生效，包括 Lead。** 一个文件同时出现在两个 task 的 write scope 里就是冲突；发现自己的改动落在别人 scope 内，**立即停止并交还**，不要在别人的边界里继续叠加。Lead 的越界尤其危险——它同时扮演写者和验收者，冲突不会被自己发现。
* **"已完成 / 可依赖"的广播必须附真实命令输出。** 只贴 `git status` 或口头结论不算证据；必须给出 `ruff` / `pytest` / `pnpm` 的**退出码与关键输出行**。写完没自检就广播 = 把未验证状态当基线传给下游（§5.1 的存在意义就在于此）。
* **共享资源（数据库、向量索引、报告目录）先留底、后覆盖，且必须等产出方 `completed`。** 例：过滤解析噪声后重灌菜谱会改变卡片文本 → **必须重跑 `scripts/build_index`**，并先把 `data/eval/reports/*.json` 复制留底，再对照指标差异。**指标因数据变干净而变化是正常结果，不是要回退的理由。**
* **终审由 Lead 在全员冻结后独立复跑。** 不要边改边审；Lead 的终审结论必须来自自己跑出的命令输出，而不是汇总 teammate 的汇报。

---

## 5. 每次修改后的固定收尾流程（**必须自动执行，不要等人提醒**）

### 5.1 自检（先跑，失败先修）

```
# 在 backend/ 下
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

> 新功能必须
>
> **先写失败测试再实现**
>
> （TDD，见
>
> `docs/CONVENTIONS.md`
>
> §6）。覆盖率目标 ≥ 70%。
> `-p no:cacheprovider`
>
> 是因为沙箱里
>
> `.pytest_cache`
>
> 建不出来。
> **沙箱跑测试的两条硬规矩**
>
> （本机实测，踩过）：
> 跑之前把临时目录指到工作区内：
>
> `$env:TEMP='<仓库>\.tmp'`
>
> ；否则 pytest 会因为写
>
> `C:\Windows\Temp`
>
> 被拒。
> **不要用&#x20;**
>
> `tmp_path`
>
> **&#x20;fixture**
>
> （它同样写系统临时目录）。需要测试数据时，把文件放
>
> `backend/tests/fixtures/`
>
> 下，用
>
> `Path(__file__).resolve().parents[1] / "fixtures" / "xxx.yaml"`
>
> 读取。

```
# 在 frontend/ 下（前端就绪后）
pnpm typecheck && pnpm lint && pnpm build
```

### 5.2 同步文档（改了行为就必须改文档，**文档与代码同一个 PR**）

| 改了什么                      | 必须同步更新                                                    |
| ----------------------------- | --------------------------------------------------------------- |
| 架构 / 目录 / 数据模型 / 接口 | `docs/ARCHITECTURE.md`（**并在 § 六 迭代日志加一行**） |
| 开发规范                      | `docs/CONVENTIONS.md`（**并在 § 十 迭代日志加一行**）  |
| 功能范围 / 验收标准           | `docs/PRD.md`                                                 |
| 技术选型 / 依赖版本           | `docs/TECH_STACK.md`                                          |
| 外部数据 / 数据字段           | `docs/DATA_SOURCES.md`                                        |
| 界面样式                      | `docs/UI_STYLE.md`                                            |
| 任何任务进度                  | `TODO.md`（勾选完成项、补新任务、记录新决策）                 |
| 全局口径变化                  | `README.md` → 「全局约定（唯一口径）」                       |
| 任务失败 / 踩坑 / 解决过程    | `docs/mistakes.md`（**每次任务收尾必记**，见 §5.5）    |

### 5.3 提交

* 分支：`main` 只接受 PR；开发走 `feature/xxx` / `fix/xxx`。
* 提交信息：`<type>: <描述>`，type ∈ `feat|fix|docs|refactor|test|chore`。
* **不要提交**：`.env`、密钥、`.venv/`、`data/recipes/*.json`（解析产物，可重建）、`.tmp/`、`.idea/`。
* 提交前 `git status` 自查一遍，确认没有误加敏感文件。
* 一个逻辑改动一个 commit；不要把人没要求的无关改动混进来。

> ✅ **2026-10-12 更新：本沙箱进程现在可以写 `.git`，AI 必须自己提交，不要再把命令甩给人类。**
>
> 旧记录（已失效）：本机实测 `git add` / `git commit` 会报 `Unable to create '.git/index.lock': Permission denied`，连在 `.git/` 下新建文件都被拒，当时的规矩是"给出可粘贴命令交人类执行"。
> **该限制已解除**：本次会话内 AI 已连续成功提交多次（`git log --oneline` 可查证），工作树保持 clean。
>
> 现在的规矩：
>
> - **AI 直接 `git add` → `git commit`**，照上面的 `<type>: <描述>` 规范走；收尾流程（§5）里"提交"这一步不再需要人类代劳。
> - 真遇到 `index.lock` 报错时，**先确认是不是正在运行的 IDE 抢锁**（这是可重试的，与旧的权限拒绝不同），再决定重试或说明情况。
> - 只有 **`git push` 不由 AI 执行**（无远端凭证）：需要推送时在汇报的「⚠️ 需要你决定 / 操作」里给出一条可直接粘贴的完整命令。
> - `git status` / `git diff` / `git log` 等只读命令一直可用，不受影响。

### 5.4 汇报格式（人类指定）

回复**必须**按下面的骨架，项项可勾选：

```
## 状态：<一句话>
## ✅ 完成了什么      （逐条列，带证据：文件路径 / 命令输出 / 数字）
## ❌ 没成功 / 没做    （逐条列，写清原因与影响，重点是对项目整体的影响）
## ⚠️ 需要你决定/操作  （只列真正需要人类拍板的）
## ▶️ 下一步           （TODO 式，按优先级）
##     对目前项目进度的百分比展示
##     如果有可以增加项目含金量的建议
```

### 5.5 记录失败与解决（`docs/mistakes.md`，**每次任务收尾必记**）

* 实习项目需要展示「怎么发现问题、怎么解决」的完整过程，所以失败和踩坑是

  **资产，不许抹掉**
* **有失败 / 踩坑时**：在 `docs/mistakes.md` 追加一条，格式固定为：

```
## <YYYY-MM-DD> <任务编号> <一句话问题>
- 问题：发生了什么（含关键报错摘要/命令）
- 原因：根因是什么
- 解决：怎么修的（文件/思路）；未解决则写明卡点、影响与下一步;有可能面试会提问，可以设想回答。
```

* **本次没有任何失败或坑**：也追加一行 `## <YYYY-MM-DD> <任务编号> 无失败记录`，保持历史连续。
* 记录从简，不复制大段报错；关键报错一行、解决思路两三行即可。
* 与 §5.2 表格一致：`docs/mistakes.md` 与代码 / 文档同一次提交。
* 严肃注意：只增不删！！！不允许删除之前的mistake记录！！！

---

## 6. 常见任务的入口

| 任务                  | 从哪开始                                                                                                                                                        |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 改菜谱解析            | `backend/scripts/import_howtocook.py` + `backend/tests/unit/test_import_howtocook.py` + `docs/DATA_SOURCES.md`                                            |
| 加 / 改领域模型       | `backend/domain/models/` + `docs/ARCHITECTURE.md` §3.1                                                                                                     |
| 加可观测埋点          | `backend/infra/observability.py` 的 `SpanName` + `docs/CONVENTIONS.md` §4.5                                                                              |
| 改 Embedding / Rerank | `backend/domain/ports.py`（契约）+ `backend/infra/embedding_client.py` / `rerank_client.py`；远程走 SiliconFlow，本地兜底可选                             |
| 本地模型（兜底）      | 下载：`python -m scripts.download_local_models`；自查：`python -m scripts.check_model_clients`；缓存固定在 `<仓库>/.cache`（见 `infra/model_cache.py`） |
| 加 / 改食材词表       | `data/ingredients/aliases.yaml` + `backend/domain/ingredients.py` + `import_report.json` 的 `unmapped_top`                                              |
| 加规则                | `data/rules/*.yaml` + `backend/domain/rules/` + `docs/PRD.md` 模块 D                                                                                      |
| 查 Langfuse 数据      | 用`langfuse` 技能；读取走 **Observations API v2**（旧 `/api/public/traces` 对本组织返回 410）                                                         |
| 复现评估/端到端数字   | 先看[`docs/evidence/`](./docs/evidence/README.md)（入库的原始输出 + 复现脚本），再跑 `scripts.eval` / `scripts.e2e_probe`                                  |

---

**最后更新**：2026-10-12 ｜ 变更：**§5.3 提交限制已解除**——沙箱进程现在可以写 `.git`，AI 必须自己 `git add` / `git commit`，不再把命令甩给人类（旧的「Permission denied，交人类执行」已标注失效；只有 `git push` 因无远端凭证仍由人类执行）。更早的 2026-10-11 变更：**新增「证据入库」纪律**——正文里任何数字都必须能追到 `docs/evidence/` 的原始输出；关键报告（评估摘要、抖动、归因、端到端、清理前后）与**复现脚本**一并入库，连“脚本写死字段名导致误报”的那次输出也留档（`e2e_run1_OLD_PROBE_field_bug.txt`）。同时新增两条来自实际踩坑的规矩：**端到端脚本不得写死响应字段**、**含 LLM 往返的指标默认多次运行给区间**。更早变更：新增 §4.1「多智能体协作纪律」（以共享任务板状态为唯一事实源、write scope 对 Lead 同样生效、广播必须附真实命令输出、共享资源先留底后覆盖、终审由 Lead 独立复跑）——五条规则分别来自本次实际踩过的坑：Lead 越界改 C3 的 `api/deps.py`/`main.py` 卡住链路、Lead 把 `in_progress` 的 task-3 说成已完成导致 `quality` claim 被拒且差点污染 eval 的实测数据。历史：2026-10-07 修复编辑器格式化造成的空行问题、新增 §5.5。
