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

