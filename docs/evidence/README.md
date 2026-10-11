# `docs/evidence/` —— 入库的原始证据

**为什么有这个目录**：`README.md` 和 `docs/INTERVIEW.md` 里有大量数字（指标、延迟、归因、前后对比）。它们的原始产物有两类问题：

- `data/eval/reports/*.json` 与 `data/recipes/*.json` 是**可重建产物**，已被 `.gitignore` 排除（4 份评估报告合计 ~920 KB）；
- `.tmp/` 更是完全不入库，**别人 clone 下来看不到任何对账材料**。

于是「这些数字从哪来」就只剩一句自述。本目录把这些证据**收进版本库**：都是小体积、只读、逐字复制的原始输出或摘要。**正文只做排版，不改任何数字。**

## 内容清单

| 文件 | 是什么 | 由谁产生 / 怎么复现 |
| --- | --- | --- |
| `eval_reports_summary.json` | 4 份评估报告的**指标 / 延迟 / 分场景 / 双通道占比 / 文件 SHA256 前 16 位**摘要（10 KB） | `cd backend && python -m scripts.summarize_eval_reports` |
| `rerank_variance.txt` | 同一语料 `hybrid_rerank` **连跑 3 次**的极差与逐查询比对 | `python -m scripts.rerank_variance --runs <3 份报告>` |
| `channel_attribution.txt` | 7 条回落查询的 `{vector 名次, BM25 名次, RRF 名次}` 三元组与汇总 | `python -m scripts.channel_attribution` |
| `e2e_run2.txt` / `e2e_run3.txt` / `e2e_run4.txt` | 端到端 5 场景的**干净复跑**原始输出 | `python -m scripts.e2e_probe`（需先起 uvicorn） |
| `e2e_latency_summary.txt` | 把上面 3 轮**聚合成的 min–max 区间表**（README 那张表就是它） | `python -m scripts.e2e_latency_summary` |
| `e2e_run1_OLD_PROBE_field_bug.txt` | ⚠️ **误报留档**：探针写死读 `results`（真实字段是 `candidates`），把 5 条候选报成 0 条 | 同上（旧版脚本），**刻意保留**；聚合脚本会自动把它排除 |
| `import_report.before.json` / `import_report.after.json` | 解析层噪声清理**前 / 后**的真实报告，可直接 diff | `python -m scripts.import_howtocook` |
| `eval_reports_summary.json` 的**对账器** | 不是证据文件，而是"证据与 README 是否一致"的 CI 门禁 | `python -m scripts.check_docs_consistency` |

## 三条纪律

1. **正文数字必须能追到这里的某一行。** 追不到的数字不许写进 README / 面试材料。
2. **失败的输出也留档，不许只留成功的那次。** `e2e_run1_OLD_PROBE_field_bug.txt` 就是例子——它记录了「我们差点被自己的脚本骗过」，删掉等于把踩坑过程擦干净。
3. **对账方式**：重跑对应脚本 → 与本目录文件逐字段比对。指标不同先查**语料版本**（是否重灌过、是否重建索引）与**抖动范围**（`hybrid_rerank` R@10 有 ±0.83pp），再谈其他。

## 对账不是靠自觉：`scripts/check_docs_consistency.py`

上面第 1 条以前只是"写在文档里的要求"——**没有任何东西会在 README 与证据对不上时报错**。现在有了：

```powershell
cd backend
.venv\Scripts\python.exe -m scripts.check_docs_consistency   # 必须 exit 0，已进 CI
```

它检查三件事，任何一件不过就 exit 1：

| 检查 | 抓什么 |
| --- | --- |
| 指标格对账 | README 评估表里每个数字（单值或 `a–b%`）必须覆盖 `eval_reports_summary.json` 的对应报告值 |
| **区间来源对账** | `hybrid_rerank` 的区间格子必须**恰好等于** `rerank_variance.txt` 的跨轮极差——**"覆盖得住就行"不算**（手写 70–80% 会被抓） |
| 来源标注对账 | README 引用的每个 `docs/evidence/...` 路径必须真实存在（防止悬空引用） |

它自己有 28 项单测（`backend/tests/unit/test_check_docs_consistency.py`），**其中一半是"注入错误必须报错"**——一个永远返回 0 的检查器比没有检查器更糟，因为它提供虚假的安全感。

## 与完整报告的关系

`data/eval/reports/*.json` 才是**全量原始报告**（含每条查询的 `evidence_top10` / `channel_sources` / `latency_ms`）；
本目录的 `eval_reports_summary.json` 是它的**可入库摘要**，用 `sha256_16` 字段绑定到具体那一份报告文件，防止"摘要与报告对不上"。

评估流程与「改语料后必须走完的证据链」见 [`../CONVENTIONS.md`](../CONVENTIONS.md) §4.6。
