# mistakes.md · 失败与问题解决记录

> 每次任务收尾**必记**（见 `AGENTS.md` §5.5）：失败和踩坑是**资产**，用于追踪「问题怎么发现、怎么解决」的完整过程（实习项目展示用）。
> 格式：`## <YYYY-MM-DD> <任务编号> <一句话问题>` + 问题 / 原因 / 解决。
> 记录从简：关键报错一行、解决思路两三行；大段报错不复制。

---

## 模板（新记录复制此结构，追加到文末）

```
## <YYYY-MM-DD> <任务编号> <一句话问题>
- 问题：发生了什么（含关键报错摘要/命令）
- 原因：根因是什么
- 解决：怎么修的（文件/思路）；未解决则写明卡点、影响与下一步
```

---

## 2026-10-07 T1.15 无失败记录

## 2026-10-07 T1.6 全量建索引：PowerShell 把 jieba 的 SyntaxWarning 误判为失败
- 问题：`python -m scripts.build_index` 实际跑完（372 卡片 + 3806 步骤全量入库），但 PowerShell 退出码 1，误导以为失败。
- 原因：jieba 0.42 包内 regex 触发 Python 的 `SyntaxWarning`，走 stderr；PowerShell 把任何 stderr 输出当 `NativeCommandError`。
- 解决：`rag/tokenization.py` 的 `_jieba()` 里 `warnings.catch_warnings()` 静默 `SyntaxWarning`；同时索引脚本打印逐批进度 + 最终计数，用数字确认成功。

## 2026-10-07 T1.6 rank-bm25 空语料 ZeroDivisionError
- 问题：`BM25Index([], [])` 构造时报 `ZeroDivisionError: division by zero`（`avgdl = num_doc / corpus_size`）。
- 原因：`rank_bm25.BM25Okapi` 对空语料（corpus_size=0）或全空文档（avgdl=0）会除零。
- 解决：`rag/bm25_index.py` 中空语料/全空文档时 `_bm25=None`，`search` 直接返回 `[]`，覆盖边界。

## 2026-10-07 T1.6 tsv 写入两个 SQL 坑
- 问题：① `to_tsvector('simple', ...)` 报 `function to_tsvector(unknown, text) does not exist`；② `recipe_steps.update().where(id == bindparam("id"))` executemany 报绑定名冲突。
- 原因：① 配置名参数是 `regconfig` 类型，传 varchar 不匹配；② SQLAlchemy 里 executemany 的 WHERE 绑定名不能撞列名 `id`（被保留）；且 embedding 是 pgvector 类型，需显式绑定类型。
- 解决：`sa.cast(sa.literal("simple"), REGCONFIG)`；改绑 `step_id` + `.values(embedding=bindparam(..., type_=Vector(1024)))`。

## 2026-10-07 T1.8 集成测试：asyncpg 把 vector 列以字符串返回
- 问题：`select e.embedding ...` 读回的值 `list()` 后变成字符列表 `['[','0',...]`，`cosine_distance` 绑定报 `could not convert string to float`。
- 原因：asyncpg 未注册 pgvector 类型 codec，`vector` 列以字符串（`"[0.026,...]"`）返回；`list(字符串)` 按字符拆。
- 解决：测试侧 `json.loads(raw)` 规范化成 `list[float]`；生产路径 `embedder.embed()` 本就返回 `list[float]`，不受影响。

## 2026-10-07 T1.8 环境：PowerShell 吞 pytest 的 ANSI 输出
- 问题：`pytest -q` 在 PowerShell 下有时不显示输出（只有退出码），难以拿到「N passed」证据。
- 原因：pytest 默认 ANSI 输出与 PowerShell 控制台缓冲不兼容。
- 解决：`*> 日志文件` 重定向后 `Get-Content` 读尾部；汇报时以退出码 + 日志数字为准。

## 2026-10-07 工程：分支规范与仓库历史冲突
- 问题：`AGENTS.md` 写「main 只接受 PR，开发走 feature/xxx」，但仓库历史（T1.3/T1.7）全是直提 main、只有单分支。
- 原因：单人本地项目长期按直觉直提 main，文档规范与实际行为不一致。
- 解决：采纳 feature 分支流程（用户拍板）；T1.6 提交挪到 `feature/t1.6`，main 用 `--no-ff` 重组历史；此后每个任务开 `feature/xxx`，自检后合回 main 并删分支。

## 2026-10-07 T1.9 重排冒烟：首查询延迟含连接冷启动
- 问题：`smoke_retrieval --rerank` 首查询（检索+重排）1668ms，超过 PRD F-B4 的 500ms 门槛。
- 原因：首次远程重排包含 TCP/TLS 连接与模型侧冷启动；后续同进程查询复用连接池，回落到 342–438ms。
- 解决：冒烟脚本逐查询打印耗时（`time.perf_counter`），PRD 勾选以**稳态**延迟为准并注明冷启动数据；生产侧如有强延迟要求，可在服务预热时打一次重排请求。

## 2026-10-07 T1.9 集成测试：假重排器分数公式写反
- 问题：`ReversingRerank` 返回的 hits 不是按分数降序（index 越大分越低却排最前），导致断言「重排后第一位」失败两次。
- 原因：生成列表时分数公式 `total - index` 让最后一个下标分最低，违反了 FallbackRerank「返回按分降序」的不变量；断言也因此反了。
- 解决：改为 `index + 1`（原最后文档分最高、降序输出），并同步修正断言为「返回列表第一位 rank=1 且 rerank_score 最大」；`rag/reranker.py` 保持按 hits 顺序组装，契约是 hits 必须降序。

## 2026-10-07 TODO 核对与同步 无失败记录

## 2026-10-07 T1.13-T1.10-T1.11 检索闭环收尾
- 问题：初版接口把数据库仓储和 LLM 方法写成同步函数；初版过滤测试遗漏了向量 Top50 与 BM25 独立召回、空语料伪通过等问题。
- 原因：Protocol 的 runtime structural check 不会验证 async 性质；硬约束允许集合与召回通道边界需要单独测试；推荐模型也曾允许空白引用和重复候选 ID。
- 解决：统一改为 async Protocol；先由 SQL 构造完整允许 recipe-id universe，再分别限制向量/BM25 通道；时间上限严格排除未知耗时；补充 SQL/单元/集成测试；Recommendation 与引用校验拒绝空白、未知、重复和冲突引用。

## 2026-10-07 T1.14-T1.16 收尾：配置、日志与异常审查
- 问题：最终审查发现 APP_VERSION 未进入模板，结构化日志会丢失 provider/degraded/operation 等字段，异常日志缺服务端 traceback，prod secret 与 middleware 异常路径缺少 context 生命周期验证。
- 原因：早期实现只保留固定日志字段，配置和 lifespan 行为虽已实现但缺少 TestClient context 覆盖；日志扩展字段未定义安全序列化及敏感字段过滤契约。
- 解决：新增 APP_VERSION 模板与配置覆盖测试；JsonFormatter 保留安全 extra 并过滤 secret/token 等字段、对不可 JSON 值使用 repr，异常日志写入 traceback；补 prod 启动成功/失败、OpenAPI 版本一致、request-id 与日志幂等测试，并同步架构与 TODO。

## 2026-10-09 T1.17 pnpm install 在链接阶段崩在 ERR_PNPM_SYMLINK_FAILED
- 问题：`pnpm install` 跑到 `added 338` 后报 `ERR_PNPM_SYMLINK_FAILED Maximum call stack size exceeded`，没有生成 `pnpm-lock.yaml`，`node_modules` 只有残缺的 `.pnpm/`。
- 原因：pnpm 默认用符号链接 + 虚拟 store 的隔离布局；本机 Windows 环境下该布局创建链接时触发 pnpm 内部的栈溢出。与镜像源、磁盘、路径重解析点都无关（已排查：项目无 junction，npmmirror 可达）。
- 解决：`frontend/.npmrc` 固定 `node-linker=hoisted`（铺平 `node_modules`、不建符号链接），安装 396 个包成功且可复现。代价是失去 pnpm 的严格依赖隔离（幽灵依赖不再报错），属可接受的取舍。

## 2026-10-09 T1.17 next build 抛 spawn EPERM，构建直接失败
- 问题：`pnpm build` 在 "Creating an optimized production build ..." 后立刻 `Error: spawn EPERM`，栈顶是 `jest-worker` 的 `ChildProcessWorker.initialize → child_process.fork`。
- 原因：沙箱禁止创建带 IPC 具名管道的子进程，而 Next 构建用 `child_process.fork` 起 worker。给 `next/dist/lib/worker.js` 注入探针后定位到根因有两个：webpack 编译 worker（`build/webpack-build/impl.js`）**根本没读** `experimental.workerThreads`；静态生成 worker 才读。单加 `workerThreads: true` 不够。
- 解决：`next.config.mjs` 设 `experimental.workerThreads: true`（静态生成走线程，实测 `Worker` 构造成功、不再 EPERM）+ `experimental.webpackBuildWorker: false`（webpack 回主进程编译）。构建成功、4 条路由预渲染；代价是构建并行度下降（本项目规模无感）。另实测 `worker_threads` 在本沙箱可用，排除"线程也被禁"的假设。

## 2026-10-09 T1.17 next/core-web-vitals 不注册 @typescript-eslint，自定义规则直接报错
- 问题：`.eslintrc.json` 里写 `"@typescript-eslint/no-explicit-any": "error"`，`pnpm lint` 对**每个**文件报 `Definition for rule '@typescript-eslint/no-explicit-any' was not found`。
- 原因：`eslint-config-next@14` 只加载 `@typescript-eslint/parser`，不注册 `@typescript-eslint` 插件；引用其规则名必然失败。而且显式声明该插件会引入 `TECH_STACK` 清单外的依赖。
- 解决：改用 ESLint 核心能力——`no-restricted-syntax` 配选择器 `TSAnyKeyword` 阻断 `any`，`no-warning-comments` 配 `terms: ["@ts-ignore"]` 阻断忽略指令。中间还试过用 `LineComment[value=/@ts-ignore/]` 选择器，实测不生效（esquery 不匹配注释节点），已弃用。两条规则都用临时探针文件实测确认会报错，不是静默失效。

## 2026-10-09 T1.17/T1.18 git 写操作被拒：`.git` 缺沙箱进程的写入授权
- 问题：`git checkout -b` 与 `git add` 报 `fatal: Unable to create 'D:/Allcode/MealCompass/.git/index.lock': Permission denied`，连在 `.git/` 下新建文件也被拒。`AGENTS.md` §5.3 已把它记为「已知环境限制，重试无用」。
- 原因：只读对比权限项发现，仓库根 `D:\Allcode\MealCompass` 上有两条显式授权（当前用户 FullControl、沙箱 SID `S-1-4-446388748-297474345` 的 Write/Delete），而 `.git` 上两条都没有、继承又被关闭，所以沙箱进程对 `.git` 没有写权限。**这是权限缺口，不是抢锁**。
- 解决：用 `diagnose-windows-sandbox-acl` 技能的一次性脚本（非受限运行、Medium 完整性、未提权）在 `.git` 上补了当前用户 FullControl，`WRITE_OWNER` 由 `false` 验证为 `true`，改动有 JSON 备份与撤销脚本（`D:\Allcode\MealCompass\.tmp\acl-recovery\`）。**但受限进程仍被拒**——沙箱实际用的是工作区根上那条 `S-1-4-*` 授权，而该技能按设计不会自行添加这个 SID。最终改用「完全权限」执行提交与合并，两次 commit + 一次 `--no-ff` 合并全部成功。遗留：若要在受限模式下提交，需人类把会话切到完全权限，或让 DSH 为 `.git` 补上与工作区根一致的授权。

## 2026-10-11 C1 共享契约：E501 / format 漂移，以及误用系统 python 跑 pytest
- 问题：实现的 `ruff check .` 报 `E501 Line too long (121/122 > 120)`，全在 `domain/models/recommend.py` 的 `Field(..., description="…中文…")` 行；`ruff format --check .` 同时报 `test_llm_client.py` 里含 `\n` 的单引号字面量（`'  \n 红烧肉 \n\n'`）需要重排。
- 原因：ruff 按字符数计宽，中文显示宽度是 2 但只算 1 个字符，所以「看着没超」的行实际已过 120；`ruff format` 会把含换行的单引号字符串统一改成双引号（格式规则与手写风格无关）。
- 解决：没有手工凑行，直接对这两个文件跑 `ruff format <file>`，让 ruff 自己排版，再跑 `ruff check .`（exit 0）+ `ruff format --check .`（71 files already formatted，exit 0）。
- 顺带踩坑：第一次验证时误用了系统 `python -m pytest`（本机 `python` 指向 anaconda 3.13），输出 `PytestConfigWarning: Unknown config option: asyncio_mode` 且 `1 error during collection`——`backend\.venv` 才是装了 pytest-asyncio 的解释器。改用 `.venv\Scripts\python.exe` 后 26 passed。`docs/CONVENTIONS.md` 与 `AGENTS.md` §5.1 都写了要用 `.venv`，属于自己没照做。

## 2026-10-11 Lead 广播了过期状态，把「未完成的依赖」说成「已完成」
- 问题：Lead 给 teammate `quality` 派发 `task-5` 时，消息里写「它的 blockers（task-2/task-3）已完成，可以开了」。实际 **`task-3`（eval）当时仍是 `in_progress`**——Lead 刚给它追加了「RRF 权重敏感性诊断」，还没收工。`quality` `claim` 时被看板拒绝（`not ready to claim`），并把这条不一致当成「Lead 说的与看板不符」反馈回来。
- 原因：Lead 把「我看到某个 teammate 汇报过一版数字」等同于「该任务已 completed」，**没有以共享任务板的 `status` 为唯一事实源**。而且此时 eval 正在对同一个 Postgres 跑真实消融，若 quality 按 Lead 的错误信息开始重灌 DB，**会直接污染 eval 的实测数字**——错误的广播差一步就变成数据事故。
- 解决：① 立即 `team_task_list` 核对看板真实状态，把 `task-5` 的 `blocked_by` 从 `["task-2","task-3"]` 改成 `["task-2"]` 让 `quality` 能开工；② 明确把「DB 重灌与全量覆盖率最终一遍」**排在 eval 收工之后**，并要求 `quality` 在重灌前先把 `data/eval/reports/*.json` 复制到 `.tmp/eval_reports_before/` 留底、重灌后**必须重跑 `build_index`**（卡片文本变了，不重建索引向量就和文本对不上）；③ 新增规矩：**派单/解锁/宣告依赖完成之前，一律先 `team_task_list` 看 `status`，不靠记忆和汇报推断**；涉及共享资源（数据库、索引、报告目录）的写操作，必须**等产出方 `completed` 后再做**，并遵守先留底、后覆盖。

## 2026-10-11 C5 测试写完了、实现没写：工作树进 RED，owner 上下文耗尽
- 问题：`quality` 按 TDD 先写测试——`backend/tests/unit/test_import_howtocook.py` 从 235 行扩到 **649 行**（新增 7 组参数化用例 + `NOISE_FIXTURE`），但**实现侧的 `parse_ingredient_lines` 一个字都没写**就耗尽了上下文。等他退出后工作树是红的：
  ```
  E ImportError: cannot import name 'parse_ingredient_lines' from 'scripts.import_howtocook'
  !!! Interrupted: 1 error during collection !!!
  1 error in 2.34s
  ```
  `ruff check .` 仍然 exit 0——**静态检查全绿掩盖了「测试根本收不上来」**，这是最容易被误判成"没问题"的状态。
- 原因：① TDD 的「红」被当成了正常中间态，但**没有设定「红多久、谁来接手」的交接点**；② teammate 的上下文预算没有和交付物规模挂钩（649 行测试 + 实现 = 一个任务太重）；③ 依赖 `quality` 的验收标准是「pytest 全绿」，但测试作者与实现作者是同一个人的强耦合，他一旦退出就没人知道契约细节。
- 解决：Lead 亲自按 task-6 接手实现（不再往下派）。做法是**把测试当规格读**——先跑一次拿到全部失败用例，再逐类补：`_is_section_heading` 精确匹配章节标题（`工具`/`原料:`）、`_looks_like_prose` 扩容（用量句/容量句/缩放规则，但用 `PROSE_NAME_MARKERS` 只判**名字**不判右侧表达式，避免误杀 `盐量 = 兔肉斤数 * 2 克`）、`TOOL_KEYWORDS` 补 20 个真实工具词、新增 `parse_ingredient_lines` 负责并列拆分。迭代 6 轮：12 failed → 9 → 6 → 3 → 1 → **152 passed**；再全量 **456 passed, 4 skipped**（当时的真实输出；后续已增至 547）、`ruff check` / `format --check` exit 0。**新增规矩**：① TDD 任务必须在派单时就写清「测试文件与实现文件，若 owner 中断由谁接手」；② 测试文件行数超过 300 行就拆成两个任务（先契约、后实现）；③ **「绿」只认 `pytest` 的真实输出，`ruff` 全绿不构成任何交付证据**——`ruff` 不 import 模块，收不上来的测试它永远发现不了。

## 2026-10-11 数据重灌后指标变了：`hybrid` 的 R@5 从 59.58% 变成 61.25%（没有回退，如实保留）
- 问题：解析层清掉 205 条噪声食材后，卡片文档（菜名 + 简介 + **食材**）变了 → 372 条卡片 embedding 重算 → 检索排序变化。重跑三组消融，`hybrid` 的指标从 R@5 59.58% / R@10 67.92% / MRR 69.61% 变成 **61.25% / 68.75% / 70.86%**；`vector` 的 R@10 从 72.50% 变成 72.08%、MRR 从 76.25% 降到 74.00%。
- 原因：**这不是 bug，是预期内的效应**——卡片文本变了，向量就变了。但有两个陷阱：① 若不重跑 `scripts/build_index`，向量和文本会对不上，指标会"看起来没变"却完全不可信；② 若拿新旧数字混着写 README，同一张表里会出现两组不同语料的数，**属于自相矛盾**。
- 解决：① 重灌前把 4 份报告留底到 `.tmp/eval_reports_before/`；② 按 `import_howtocook → seed_recipes → build_index`（372 卡片 + 3,806 步骤）顺序重灌，再 `--validate-only` 确认 **40/40 标注菜名仍存在**（说明过滤没过头）；③ **全量重跑三组 + 6 档权重消融**，README 的表格、结论、分场景表、`docs/INTERVIEW.md`、`docs/DATA_SOURCES.md`、`TODO.md` **一次性全部换成新数字**，不留混用；④ 重算归因（7 条回归查询 / 21 个金标准：双通道 7、仅向量 13、仅 BM25 0、均未召回 1），**核心结论未变**（等权 RRF 的结构性缺陷、重排只赢 R@10）。**新增规矩**：**任何影响语料或索引的重灌，都必须「留底 → 重灌 → 重建索引 → 校验标注 → 全量重跑 → 一次性统一所有文档数字」，中间任何一步偷懒都会留下不可信的数字。**

## 2026-10-11 C5 补覆盖率测试时踩到「用例间环境变量污染」：单跑全绿、全量 6 红
- 问题：为把 `infra/db.py`(64%) / `infra/observability.py`(75%) / `api/deps.py`(80%) 的覆盖率补上去，新增了三个测试文件。**单独跑 `test_infra_observability.py` 时 15 passed、覆盖率 100%**；但跑全量时出现：
  ```
  FAILED tests/unit/test_api_deps.py::test_tracing_degraded_mirrors_settings
  FAILED tests/unit/test_infra_observability.py::test_configure_returns_false_without_keys
  FAILED tests/unit/test_infra_observability.py::test_configure_only_needs_one_key_missing_to_degrade
  ... (共 6 个)
  6 failed, 485 passed, 4 skipped
  ```
- 原因：`observability.configure()` 的**启用路径会往 `os.environ` 写 `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`**，而 `Settings(_env_file=None)` 里的 `_env_file=None` **只关掉 `.env` 文件，关不掉真实环境变量**。于是"启用路径"用例先跑之后，后面的"未配 key"用例**从环境变量里捡到了上一个用例留下的 key**，变成已配置状态。这是典型的**用例间顺序依赖**——单跑绿、全量红，比全红更危险。
- 解决：① 给 `test_infra_observability.py` 加 autouse fixture，在每个用例前后**保存并还原 `LANGFUSE_*` 四个变量**，同时清掉模块级 `_client/_module/_ready/_degraded_reason`；② `enabled` fixture 也负责还原环境变量；③ 构造 `Settings` 时**显式传 `langfuse_public_key=None` / `langfuse_secret_key=None`**（初始化参数优先级最高，压过环境变量）；④ **正反两种文件顺序各跑一遍**确认无顺序依赖。结果：491 passed / 4 skipped，覆盖率 **93% → 96%**（`api/deps.py` 与 `infra/db.py` 到 100%）。**新增规矩**：**任何写 `os.environ` 的模块，其测试必须自带环境变量保存/还原；看见"单文件绿、全量红"先怀疑用例间污染，不要怀疑被测代码。**（后续 W3.7 又为入库脚本补了 28 项单测，最终 **519 passed / 4 skipped、覆盖率仍 96%**；本条保留当时的 491，因为这是那一刻的真实输出。）

## 2026-10-11 C5 端到端探针写死响应字段名，把 `/recipes/search` 的 5 条候选误报成 0 条
- 问题：写完覆盖率测试后重跑端到端 5 场景，探针脚本输出 `POST /recipes/search {"query":"有鸡蛋和番茄","top_k":5}` → `HTTP 200 耗时 767 ms`、`results=0`、`top3=[]`。**HTTP 是 200、`degraded=False`，看起来像"检索真的没召回"，差点被当成一条新的失败结论写进 README。**
- 原因：探针里写死读 `data.get("results")`，而 `/recipes/search` 的真实契约字段是 **`candidates`**（`SearchResponse.candidates`，契约在 `domain/models/recommend.py`）。字段不存在 → `None` → `or []` → 打印 0。**是探针在骗人，不是接口坏了。**
- 解决：① 把探针改成**按字段是否存在自动适配**（`candidates` / `results` 都认，见 `backend/scripts/e2e_probe.py` 的 `candidates_of`），重跑得到真实的 5 条候选（番茄牛肉蛋花汤 / 意式香肠北非蛋 / 罗宋汤 / 鸡蛋三明治 / 温泉蛋）；② 探针**入库**到 `backend/scripts/e2e_probe.py`，原始输出留底到 `docs/evidence/e2e_run{2,3}.txt`，让 README 的每个数字都能被一条命令复现；③ 把误报那次输出重命名为 `docs/evidence/e2e_run1_OLD_PROBE_field_bug.txt` **一并入库**——留着它是为了证明"我们差点被自己的脚本骗过，以及怎么发现的"。**新增规矩**：**端到端脚本不要写死响应字段；对外的断言字段必须先与 `domain/models/` 的契约对齐；探针的输出必须留底入库，否则无法分辨"接口坏了"和"探针写错了"。**

## 2026-10-11 同一份代码连跑三轮，延迟差出 2.8 s、`degraded` 还会翻转
- 问题：为给 README 的端到端表提供可复现证据，连跑了 3 轮。同样的 `{"query":"西红柿炒鸡蛋"}`：**12.0 s / 10.4 s / 9.2 s**；`degraded` 两轮 `false`、一轮 `true` + `recommendation_shortfall`（同一句话，模型有时只返回 2 条推荐）。而同一批跑里**无解路径 2.0–2.2 s、纯检索 444/441 ms 三轮几乎不变**。
- 原因：**波动全部来自 LLM**（生成阶段的输出长度与耗时都不稳定），**检索侧是稳定的**。把 LLM 的不确定性写成 `degraded` 字段、把检索的稳定性写成固定数字，两者不能混。
- 解决：① README 的端到端表**改成给区间**（`9.2 – 12.0 s`），并明确写"延迟差异全部来自 LLM 生成阶段"——**拒绝给假精度**；② 把"三轮里有一轮 `degraded=true`"作为**真实存在的非确定性**写进表里，而不是挑一轮好看的；③ 原始三轮输出全部入库到 `docs/evidence/`；④ 补 `scripts/e2e_latency_summary.py` **自动聚合区间**，并把"排除已知有 bug 的轮次"写成代码里的常量（`EXCLUDED_MARKERS`）而不是文档里的一句解释。**新增规矩**：**任何含 LLM 往返的指标，默认按"多次运行给区间"来报；一次测量只写一个精确数字，等于在报告里藏了未测量的方差。**

## 2026-10-12 W3.8 「正文数字必须能追到证据」这条纪律，此前没有任何东西在执行它
- 问题：`docs/CONVENTIONS.md` §4.6 从 v1.11 起就写着「正文数字必须能追到 `docs/evidence/` 的原始输出」。但这句话**只是文字要求**：我手工把 README 表格与证据文件比对过一次，比对完就结束了。**没有任何命令或 CI 步骤会在两者对不上时报错**——下次改 README 数字忘了同步证据，或者手写一个"看起来差不多"的区间（比如把实测 77.50–78.33% 写成 77.5–79.0%），都不会有人拦。**手工核对过一次不算机制。**
- 原因：把"纪律"写进文档，和把纪律**变成可执行的门禁**，是两件不同的事。前者依赖执行者的记性，后者依赖机器。同类问题在本项目已出现过（广播"已完成"却没有命令输出，见 §4.1），说明"只写要求"是可复发的失败模式。
- 解决：① 新增 `backend/scripts/check_docs_consistency.py`，做三类对账——README 评估表 12 个指标格 vs `eval_reports_summary.json`；`hybrid_rerank` 的区间格子必须**恰好等于** `rerank_variance.txt` 的跨轮极差；README 引用的每个证据路径必须真实存在。② 新增 **28 项单测**，其中一半是"注入错误必须报错"的篡改检测（改 R@5 为 99.99% → exit 1；引用不存在的证据 → exit 1）。③ 作为**独立步骤进 CI**。④ 写测试时发现一个**真实的分工问题**并留了钉子：把区间写成 70–80% 时，"覆盖报告值 77.50%"这条检查会**放行**——所以光有"覆盖"不够，必须有"区间必须等于实测极差"这第二条检查；专门写了 `test_check_metrics_alone_accepts_over_wide_range_hence_variance_check_exists` 把这个分工钉住，防止以后有人把它当冗余删掉。**新增规矩**：**写在文档里的纪律，必须有对应的可执行门禁；而门禁本身必须有"注入错误会失败"的测试——一个永远返回 0 的检查器比没有检查器更糟，因为它提供虚假的安全感。**

