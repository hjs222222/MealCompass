# 数据来源与许可

> 本项目所有外部数据的来源、版本与许可登记表。新增数据源必须在此登记。

## 1. 菜谱数据：HowToCook

| 项 | 值 |
| --- | --- |
| 上游仓库 | <https://github.com/Anduin2017/HowToCook> |
| 采集 commit | `a2d45c6984dff9ee941da0e7c452f7965965d962` |
| commit 日期 | 2026-09-23 |
| 采集日期 | 2026-10-06 |
| License | **Unlicense（公有领域）** —— 可自由复制、修改、分发、商用，无需署名 |
| 落库路径 | `data/raw/howtocook/<category>/<菜名>.md` |
| 数量 | **372 道菜**（上游 `dishes/` 共 373 个 md，剔除 `template/示例菜.md`） |
| 体积 | 0.77 MB |

### 保留了什么

只保留 `dishes/**/*.md`（纯文本菜谱）与上游 `LICENSE`，按上游分类目录组织：

```
data/raw/howtocook/
├── aquatic/  breakfast/  condiment/  dessert/  drink/
├── meat_dish/  semi-finished/  soup/  staple/  vegetable_dish/
└── LICENSE
```

每篇菜谱的结构高度统一（372/372 全部命中，可作为解析器的前提）：

```
# <菜名>的做法
<一段简介>
预估烹饪难度：★★★
预估卡路里：850 大卡
## 必备原料和工具      # 主要为食材名，常带（别称：xxx）等备注；也混有厨具
## 计算                # 每份用量，三种写法：`名称 400 g` / `名称 = 2 斤` / `名称 15g*份数`
## 操作                # 有序步骤
## 附加内容
```

### 丢弃了什么，为什么

| 丢弃内容 | 体积 | 原因 |
| --- | --- | --- |
| 上游 `.git` | 514.6 MB | 与本项目无关的完整历史；需要时按 commit 重新拉取 |
| 配图（`.jpg/.jpeg/.png/.webp`） | 108 MB / 355 张 | 本项目 RAG 只用文本；详情页当前也不展示成品图 |
| `tips/` | — | 通用厨房技巧，不属于菜谱检索范围 |
| `.github/`、`package.json`、`.textlintrc`、`.markdownlint.json`、`CODE_OF_CONDUCT.md` | — | 上游的 CI / 文案校验工具链 |
| `dishes/template/示例菜.md` | — | 贡献模板，不是真实菜谱 |

> 完整 clone 目前仍在仓库根的 `HowToCook/`（623.8 MB，已被 `.gitignore` 排除），确认无误后可整目录删除。

### 已知的数据缺口

- **没有 `time_minutes`（烹饪耗时）**：`time_minutes` 是硬约束字段，缺失时按难度兜底并标注「不确定」，**不得编造**。
- **只有热量，没有蛋白质 / GI / 钠**：这正是本项目**不做医学人群细分**的原因（见 `README.md` 全局约定与 `PRD.md` §1.5）。
- 用量写法不统一，解析器必须对「解析不出」的行保留原文而不是猜（见 `import_report.json` 的未解析统计）。

### 重新获取

上游更新后重跑 `backend/scripts/sync_howtocook.py`（TODO T0.14），它按同一条路径只拉取 markdown，并更新本表里的 commit 与日期。
