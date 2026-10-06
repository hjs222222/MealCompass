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
| 落库路径 | `data/raw/howtocook/<category>/...` |
| 菜谱 | **372 道**（上游 `dishes/` 共 373 个 md，剔除 `template/示例菜.md`） |
| 配图 | **354 张，108 MB**（`.jpg` 213 / `.jpeg` 96 / `.png` 42 / `.webp` 3） |
| 总体积 | 108.7 MB |

### 目录结构

配图与对应菜谱**放在同一目录**，markdown 里用相对路径引用（如 `![成品](./成品.jpg)`），
所以镜像上游结构即可保证引用不失效：

```
data/raw/howtocook/
├── aquatic/  breakfast/  condiment/  dessert/  drink/
├── meat_dish/  semi-finished/  soup/  staple/  vegetable_dish/
│   ├── 上汤娃娃菜/
│   │   ├── 上汤娃娃菜.md      ← 菜谱
│   │   └── 上汤娃娃菜.png     ← 成品配图（127 KB）
│   └── 葱烧鸡腿.md            ← 部分菜谱是扁平结构，无配图
└── LICENSE
```

- **177 / 372 道菜有配图**，共 346 条本地引用；另有 2 条外链图（上游托管在 GitHub user-images，未下载）。
- 354 张图里有 8 张没有被任何菜谱引用（上游遗留）。
- 部分文件名含括号（如 `石凉粉(冰粉)成品1.jpg`），解析器已按 markdown 语法正确处理，**0 缺失**。

### 保留了什么

只保留 `dishes/**`（菜谱 markdown + 同目录配图）与上游 `LICENSE`，按上游分类目录组织。

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
| `tips/` | — | 通用厨房技巧，不属于菜谱检索范围 |
| `.github/`、`package.json`、`.textlintrc`、`.markdownlint.json`、`CODE_OF_CONDUCT.md` | — | 上游的 CI / 文案校验工具链 |
| `dishes/template/示例菜.md` | — | 贡献模板，不是真实菜谱 |

> 完整 clone 目前在仓库根的 `HowToCook/`（623.8 MB，已被 `.gitignore` 用 `/HowToCook/` 排除）。
> 内容已全部复制到 `data/raw/howtocook/`，确认无误后可整目录删除。

### 已知的数据缺口

- **没有 `time_minutes`（烹饪耗时）**：`time_minutes` 是硬约束字段，缺失时按难度兜底并标注「不确定」，**不得编造**。
- **只有热量，没有蛋白质 / GI / 钠**：这正是本项目**不做医学人群细分**的原因（见 `README.md` 全局约定与 `PRD.md` §1.5）。
- 用量写法不统一，解析器对「解析不出」的行保留原文而不是猜（见 `import_report.json`；当前 86 条）。
- 195 道菜没有配图，前端详情页需要占位图兜底。

### 重新获取

上游更新后重跑 `backend/scripts/sync_howtocook.py`（TODO T0.14），它按同一条路径只拉取 markdown 与配图，并更新本表里的 commit 与日期。
