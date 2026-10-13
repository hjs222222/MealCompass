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

## 2026-10-12 W3.11 推荐卡片把数据库主键直接摆给用户，而且从未登记为待办
- 问题：用户看截图问「旁边有一串字符串是不是没优化」。核对后发现卡片把完整 `recipe_id`（UUID）用 `font-mono` 原样渲染在耗时标签旁（`recommend-results.tsx`）。
- 原因：当初为了证明「引用防幻觉」可肉眼核对而直接展示主键，属实现时的方便选择；但**既没在产品层做取舍，也没登记进 `TODO.md` / `docs/failed-features.md`**——于是它既不算「刻意设计」也不在待办清单里。**这种「无主改动」最容易被漏掉**：状态表没有它的位置，谁都不会在收尾时想起它。
- 解决：① 把 ID 折叠进 `<details>` 披露入口（可展开、可复制，剪贴板 API 不可用时退化为手动选中），卡片主视觉只留耗时标签；② 耗时标签旁补一句「上游 HowToCook 未提供时长」的说明，避免用户把「耗时未知」误读成 bug；③ 在 `docs/UI_STYLE.md` 新增「技术性标识必须折叠」约定，让下一条同类改动有据可依；④ 记入 `TODO.md` W3.11。**新增规矩**：**面向开发者的标识（主键 / UUID / 内部标签）不做产品取舍就不得进入用户界面；凡是用户能看见的东西都要在 `TODO.md` 或 `docs/failed-features.md` 有登记，不允许「无主」。**

## 2026-10-12 W3.10 后端已启动但浏览器报无法连接
- 问题：`OPTIONS /recommend` 返回 405，浏览器 `/health`、`/version` 显示 `network_error, status=0`；早先 Docker 报 Linux 引擎管道不存在。
- 原因：FastAPI 未装配 CORS 中间件；普通 HTTP 调用不执行浏览器跨域校验，因此以前的接口验证遗漏此边界。Docker 管道错误是引擎当时未就绪，排查时 postgres / redis 已 healthy。
- 解决：增加可配置来源白名单及 CORS 中间件，默认允许本机 3000 端口，覆盖预检/正常/错误响应；12 项回归测试，真实 HTTP 推荐返回 3 条。已有 uvicorn 未使用 reload，需重启加载代码。新增 422 测试最初意外装配真实数据库，全量报事件循环关闭，已通过 dependency_overrides 隔离该用例。

## 2026-10-12 W3.9 README 声称"双层索引"，实测步骤层向量 3,806 条全是 NULL
- 问题：用户问"项目现在能跑起来看到前端吗"，我按流程先核验数据库真实状态，结果发现 **`recipe_steps.embedding` 3,806 行全部为 NULL**（`count(*) FILTER (WHERE embedding IS NULL) = 3806`，`count(embedding) = 0`）。而 `README.md` L24 明写「双层向量索引（卡片级 + 步骤级…）✅ 已建，库里 372 + **3,806 条向量**」，L89 也写「3,806 步骤向量」。**README 在这一点上是不准确的。**
- 原因：`scripts/seed_recipes.py:223` 用「先删后插」保证幂等——`delete(recipe_steps)` 会**连同 embedding 一起删掉**，而重插的行只含 `{recipe_id, step_no, content}`（不含 embedding）。所以**每次重灌菜谱，步骤层向量都会被清空**；而 §4.6 的证据链纪律只强调"重灌后要重跑 `build_index`"，没有强调"`seed_recipes` 会破坏步骤层"。10-11 那次重灌后确实重跑过 `build_index`（`.tmp` 里有 `pwsh-76` 的 `--layer step` 作业记录，exit 0），但**之后又跑过一次 `seed_recipes`**（`recipes.created_at` 最新为 `2026-10-07 05:18`，而卡片层 embedding 非空 → 说明卡片层是在 seed 之后单独重建的，步骤层则被 seed 清掉后**没再补**）。**"跑过重建"不等于"当前数据库里还有向量"**——这是一次典型的"把执行记录当成当前状态"。
- 解决：① **先补数据**：`python -m scripts.build_index --layer step --batch-size 8`（默认 `--batch-size 64` 会撞 SiliconFlow 读超时 `httpx.ReadTimeout`，33 s 后失败；降到 8 后 364.9 s 跑完 3,806 条）→ 复核 `step_vectors = 3806 / null = 0 / vector_dims = 1024`。② **修正文档口径**：核实后发现这一层**根本没接入检索**（`retriever.py`/`agents/`/`services/` 对 `recipe_steps` 的引用数全为 0），所以真正该写的不是"已建"而是"**两层都建了，但只有卡片级参与检索**"——已同步修正 README L24 / L64 / L89 与 `rag/chunking.py` 模块注释，并登记为 `docs/failed-features.md` **F21**。③ **新增两条规矩**：**「跑过重建」≠「当前库里还有向量」——报状态前必须查一次数据库，不能引用执行记录**；**「建了索引」≠「索引在用」——README 写技术能力前，必须确认有生产代码真的读它（`grep` 引用数）**。

## 2026-10-12 W3.12 把结构化空值误判为上游缺失
- 问题：数据库 `recipes.time_minutes` 全为 NULL，之前据此宣称 HowToCook 没有时长；实际鳊鱼炖豆腐原文明确写「从备料到完成约需 40 分钟」。
- 原因：导入解析器把 `time_minutes` 固定写成 `None`，推荐生成/校验又沿用了全空假设；description 虽保留原文，却未提取结构化展示值。
- 解决：新增原文明示总时长提取与全量审计（372 道，367 条保守提取，5 条留待人工确认），详情读取时展示原文文本；不做模型估算、不把单步时间冒充总时长。另补齐详情、步骤、原料、图片和安全图片端点。

## 2026-10-12 W3.12 多智能体中断后的恢复
- 问题：前端与时长审计子任务曾中断，工作区留下部分未联调改动。
- 原因：共享任务板状态与工作区改动需要由 Lead 重新核对，不能只依赖中断前的汇报。
- 解决：按任务板确认两个任务均 completed，Lead 独立运行 580 passed / 4 skipped、Ruff 和真实数据库详情读取，完成剩余集成。

## 2026-10-12 工程：docs/mistakes.md 被误删到只剩 2 条，从 HEAD 恢复
- 问题：docs/mistakes.md 被误操作清空，工作区只剩 W3.12 两条新记录，31 条历史（模板 + T1.6 起 29 条）整体消失；git diff 显示 160 行删除。
- 原因：误删发生在未提交的工作区（W3.12 两条尚未入库），文件也没有编辑器本地历史 / 备份副本可回滚（VSCode History 里查无此文件）。
- 解决：以 HEAD:docs/mistakes.md 为基线恢复（29 条历史一字未改），再把误删时残留的两条 W3.12 记录逐字追加回文末；核对 git diff --numstat 为 9 0（纯新增、零删除），并留底当前稿于 .tmp/mistakes-recovery/。**新增规矩**：docs/mistakes.md 属于"只增不删"的资产，任何"清空 / 重写"操作前先 git show HEAD:docs/mistakes.md 留底。

## 2026-10-12 W3.13 一键启动脚本：连踩 5 个只靠"看代码"发现不了的坑
- 问题：写 `start_mealcompass.bat`（双击起前后端并打印网址）时，最省事的两条命令（`uvicorn --reload`、`next dev`）在受限环境里**根本起不来**；把日志重定向到固定文件、用 `taskkill /T` 停服务，也各有各的坑，逐个实测才暴露。
- 原因（5 个坑，都实测过）：
  1. `next dev` 必定 `fork` 一个带 IPC 具名管道的子进程（`next-dev.js:213`），沙箱 / 安全软件直接 `spawn EPERM`，且**没有配置开关**；`next start` 同进程启动，不受影响。
  2. `uvicorn --reload` 的 reloader 走 multiprocessing 具名管道，同样 `PermissionError [WinError 5]`，报一屏 `resource_sharer` traceback。
  3. 本机 pwsh 7.6 下 `Start-Process -PassThru -NoNewWindow` 返回的 Process **`ExitCode` 恒为空**（实测 `cmd /c exit 7` 读回空），会让"构建是否成功"这类判断静默失效；`-WindowStyle Hidden` 与 .NET `ProcessStartInfo` 才拿得到 7。
  4. 日志写死成 `backend.out.log` 时，**上一次没退干净的进程一直占着这个文件**，`cmd` 的 `>` 重定向失败、命令以 1 立即退出——表现成"新启动的后端秒退"，很容易误判成代码坏了。
  5. `taskkill /PID <cmd包装进程> /T /F` 未必带走真正占端口的 `node`；而且旧版脚本**不看 taskkill 结果就报"已停止"**，还顺手删掉了 `pids.json`，残留进程就此失联。
- 解决：① 前端 dev 失败且命中 `spawn EPERM` → 自动降级 `pnpm build` + `next start`（已有 `.next` 就跳过构建）；② 后端热重载改成**opt-in**（`start_mealcompass.bat reload`），默认不带 `--reload`；③ 统一改用 .NET `ProcessStartInfo`（`UseShellExecute=false`，保留控制台继承）拿 `ExitCode`；④ 启动前试探日志文件能否独占写入，写不了就换带时间戳的文件名，绝不因日志被占而启动失败；⑤ `pids.json` 同时记录**端口所有者进程**与 cmd 包装进程，`stop` 先杀服务再杀包装进程，并**校验 taskkill 结果**——杀不掉就打印可粘贴的 `taskkill /PID x /T /F` 并把记录留下次重试，不再谎报成功。验证：`check` 在 pwsh 7.6 与 Windows PowerShell 5.1 下均 exit 0；真实启动后 4 个网址全部 HTTP 200（推荐页 20,173 字节）；`stop` 后端口确实释放。
- 面试可能会问的点：
  - 「你怎么保证这个脚本不是"能跑就行"？」→ 答：所有关键分支都跑过真实进程来验证，而不是读代码猜；第 3 条（`ExitCode` 恒空）就是"看起来对、实际静默失效"的典型，是实测才抓到的。
  - 「为什么不直接 `next dev`？」→ 答：先尝试 dev（保留热重载这个开发体验），失败且错误特征明确时才降级到生产模式，并且明确告知用户"已降级、无热重载"，不做静默妥协。
  - 「为什么 kill 进程这么麻烦？」→ 答：Windows 上占端口的是子进程而不是包装进程，所以按**端口所有者**记录 PID；并且任何 kill 都要检查返回码，"报成功"与"真停掉"是两件事。
## 2026-10-12 体验修复 不要南瓜却推荐南瓜菜 + 前端冗余文案清理
- 问题：用户输入"不要南瓜"，推荐第 2 名仍是"山药南瓜炖鸡汤"；卡片里反复出现"命中你的需求「xxx」的混合检索第 N 名结果""用户想吃番茄，这道菜以西红柿为主要食材"等机械文案；每次查询都弹"本次走了降级路径 recommendation_shortfall"。
- 原因：
  1. 食材词表（aliases.yaml）里根本没有"南瓜"这个标准食材，别名表里也没有"小南瓜"→"南瓜"的映射。山药南瓜炖鸡汤的食材原文写的是"小南瓜"，硬约束 SQL 用精确等值匹配 
ame_raw = '南瓜'，"小南瓜" ≠ "南瓜"，NOT EXISTS 不命中，这道菜漏过了过滤。对比"清蒸南瓜"（name_raw 就是"南瓜"）反而被正确排除——证明 SQL 逻辑本身没错，是词表缺失。
  2. 规则兜底 reason 模板写死了"命中你的需求「{}」的混合检索第 N 名结果"，LLM 一旦条数不够走兜底，这句机械话就直接展示给用户。
  3. GENERATE_SYSTEM_PROMPT 要求"最多输出 3 条"，top_k=3 时 LLM 经常只给 2 条，validate 阶段发现数量不足就补候选，每次都触发 recommendation_shortfall。
  4. 前端 DEGRADATION_LABELS 没登记 recommendation_shortfall 的中文释义，直接原样显示英文标签。
- 解决：
  1. aliases.yaml 加"南瓜"标准食材 + [小南瓜, 金瓜, 倭瓜, 番瓜, 南瓜块, 南瓜泥] 别名；直接在 DB 里 INSERT ingredients + ingredient_aliases，并 UPDATE recipe_ingredients 把 name_raw 命中别名的行回填 ingredient_id（不重跑 build_index，避免重建 embedding）。验证：所有菜名含"南瓜"的菜现在都被 NOT EXISTS 正确排除。
  2. _rule_recommendation 模板改成"根据你的需求检索到这道菜"，不再暴露"混合检索第 N 名"系统术语。
  3. GENERATE_SYSTEM_PROMPT 把"最多输出 3 条"改成"必须输出恰好 N 条，一条都不能少"，并在 user message 里明确条数。
  4. DEGRADATION_LABELS 补 recommendation_shortfall = "模型给出的条数不足，已用剩余候选补齐到你要的数量"。
  5. 顺带：热量标签去掉"（HowToCook 预估）"后缀；删除"按烹饪时长筛选（暂不可用）"占位块；隐藏厨具选择 UI（数据上游不含 tools，类型保留）；加菜谱分类快捷按钮（breakfast/soup/staple 等→中文，后端 HardFilters+SQL 已下推 category 列）；logging.py 加 RotatingFileHandler（5MB×3 滚动）。
- 面试可能会问：
  - 「硬约束下推为什么还会漏？」答：SQL 逻辑对，但匹配是精确等值；食材写法有别名差异（小南瓜≠南瓜）时，词表没覆盖就漏了。根因是数据不是代码——同义词表要持续补，不能假设上游食材名规范。
  - 「为什么每次都 shortfall？」答：prompt 写"最多 3 条"模型就给 2 条；改成"必须恰好 N 条"后预期缓解。这是 prompt 工程的典型坑：上界指令被模型理解为下界。

## 2026-10-12 忌口硬约束系统性漏网：不要番茄却推荐番茄红酱、不要土豆却推荐炸薯条
- 问题：修完"南瓜"后用户复测发现更广的漏网——"不要番茄"推荐了番茄红酱，"不要土豆"推荐了炸薯条。不是个例，是系统性问题。
- 原因（三层叠加，探针实测证据见 .tmp/probe_excluded_systematic.py）：
  1. **食材粒度断层**：词表里番茄（蔬果）和番茄酱（调料）是两个独立标准食材，无父子层级。番茄红酱的食材是"番茄酱"→canonical=番茄酱，SQL 找 canonical=番茄 精确等值匹配不上。同理土豆淀粉→canonical=淀粉。
  2. **解析层噪声泄漏**：炸薯条的 recipe_ingredients 表只有 '-'、'作为主食，'、'作为小食，' 三条噪声，真正的土豆根本没进食材表，SQL 无从过滤。
  3. **SQL 精确等值太死**：ri.name_raw = '番茄' 不匹配小番茄（未归一化）、'土豆两三个'（已映射但 name_raw 本身不是"土豆"）。
- 解决：本次只记录排查路径，未改代码。待用户拍板"不要番茄时番茄酱算不算番茄"后，再决定是加 LIKE 兜底、修解析层、还是加食材父子层级。
- 面试可讲的点：
  - 「硬约束 SQL 写对了为什么还漏？」答：SQL 逻辑对，但忌口可靠性取决于数据归一化完备度——食材表是空的（炸薯条）、或归到了另一个标准食材（番茄酱≠番茄），SQL 再正确也漏。这是数据工程问题不是查询问题。
  - 「怎么系统性排查这类漏网？」答：写脚本对每个 canonical 食材模拟"不要 X"，然后检查菜名含 X 但仍在 allowed_ids 里的菜——一次扫出所有漏网组合，不只是 case by case。

## 2026-10-13 W3.15 `LIKE` 修复后仍推荐猪肉菜
- 问题：trace `ac1136dd07eb2d66abe1de9435397fc1` 的解析观察已输出 `excluded_ingredients=["猪肉"]`，检索候选仍含香煎五花肉、回锅肉、猪肉烩酸菜等；真实数据库回归先红（上述事故菜谱仍在允许集合）。
- 原因：已有 `LIKE` 只检查原料表及关联的标准名/别名。库中「五花肉条」「五花肉」等原料没有 `ingredient_id`，而菜名没有参与 SQL；另外「西红柿」与「番茄酱」分属不同标准名。修复过程中 Ruff 还抓到 Python 3.11 不支持 f-string 表达式内反斜杠的语法问题。
- 解决：SQL 先展开词典同义名，再在召回前检查菜名、原料原文及已映射名称；保持 LIKE 参数转义。针对真实事故菜谱和 SQL 形态写回归测试并先确认失败；另核对上游炸薯条原文后，补「薯条」→「土豆」关联名。初版展开全部短别名时「里脊」误伤牛里脊，增加跨食材名称歧义检查并以牛肉菜回归。面试回答：硬约束安全性取决于查询范围、词典覆盖和源数据质量；一次手工回填或只改比较运算符都无法形成持续保障。
