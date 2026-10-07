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

## 2026-10-07 T1.6 集成测试：pytest-asyncio 全局 engine 跨事件循环
- 问题：集成测试用 `infra.db.get_engine()`（全局单例），报 `Event loop is closed` / 连接绑死旧 loop。
- 原因：pytest-asyncio 每个测试一个事件循环，全局连接池里的连接绑死第一次使用的 loop。
- 解决：集成测试各自 `create_async_engine(get_settings().database_url)`，用完 `engine.dispose()`；生产代码仍用单例。

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
