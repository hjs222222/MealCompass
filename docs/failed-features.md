# 未完成功能与环境受限项登记（failed-features）

> **用途**：如实登记「还没做 / 没验证 / 被环境挡住」的东西，避免文档或界面假装它们可用。
> **维护规则**：新增未完成能力、或跳过某项验证时，必须在下表补一行，并写清证据、影响与承接任务。
> **当前任务**：T1.17（前端骨架）、T1.18（前端数据层）｜最后更新：2026-10-09
> **配套**：任务进度见 [`../TODO.md`](../TODO.md)，踩坑过程见 [`mistakes.md`](./mistakes.md)。本文件只记录「状态」，不复述踩坑细节。

## 一、总览

| # | 项目 | 状态 | 影响 | 承接任务 |
| --- | --- | --- | --- | --- |
| F1 | 注册 / 登录 / JWT | 未实现 | `/login` 只有禁用占位表单，无鉴权，全部接口假定匿名 | T2.15 |
| F2 | 推荐 Agent（对话 / 推荐） | 未实现 | 无 `/recommend`、`/chat`；首页与面板均不展示推荐结果 | T2.16-T2.26 |
| F3 | 菜谱详情与烹饪模式 | 未实现 | 无 `/recipe/[id]`、`/cook/[id]` | T2.27、T3.2 |
| F4 | 购物清单 / 一周菜单 / 历史 / 画像 | 未实现 | 无对应页面 | T3.1、T3.3、T2.30、T2.14 |
| F5 | 前端自动化测试 | 未实现 | 仓库内 0 个前端测试；回归只能靠人工与三条静态检查 | 待定（选型未决） |
| F6 | 浏览器内运行时验证 | 未执行 | 水合、点击重试、紧凑模式切换、真实浏览器里的 fetch 均未经端到端验证 | 待引入浏览器自动化 |
| F7 | shadcn/ui 组件库 | 未初始化 | `components/ui/` 为空；当前全部为手写 Tailwind 组件 | T0.6 |
| F8 | 视觉与无障碍实测 | 未执行 | 未测 Lighthouse ≥ 80、未做移动端真机 / 屏幕阅读器检查 | T4.5、T3.9 |
| F9 | 后端全量自检（ruff / pytest） | 未执行（本条任务） | 本次未改后端任何文件，故未重跑；不代表后端当前全绿 | 每次改后端时执行 |
| F10 | 前端 lint 之外的 `any` 兜底 | 部分覆盖 | ESLint 已阻断 `any` / `@ts-ignore`，但无前端测试，故缺运行时兜底 | F5 |

## 二、逐项说明

### F1 注册 / 登录 / JWT —— 未实现

- **现状**：`frontend/app/(auth)/login/page.tsx` 存在，但表单全部 `disabled`，页面上写明「登录（未实现）」。
- **证据**：登录页不发任何请求；`lib/api.ts` 只有两个只读 GET 端点，无鉴权头。
- **影响**：全部页面按匿名用户工作；需要登录态的页面无法开发。
- **下一步**：T2.15（邮箱 + 密码 + JWT，bcrypt，多用户数据隔离）。

### F2 推荐 Agent —— 未实现

- **现状**：无推荐 / 对话页面；`/dashboard` 明确写了「不展示推荐结果」。
- **证据**：`frontend/app/` 下只有 `page.tsx`、`(main)/dashboard/page.tsx`、`(auth)/login/page.tsx`。
- **影响**：产品的核心价值链路（查询 → 检索 → 推荐）在界面上完全不可见。
- **下一步**：T2.16-T2.26 完成后接前端。

### F3 菜谱详情与烹饪模式 —— 未实现

- **现状**：无 `/recipe/[id]`、`/cook/[id]` 路由。
- **证据**：`app/` 下无 `recipe/` 目录。
- **影响**：检索到的菜谱无法在界面上查看。
- **下一步**：T2.27（详情 + 份量缩放）、T3.2（烹饪指导模式）。

### F4 购物清单 / 一周菜单 / 历史 / 画像 —— 未实现

- **现状**：均无路由与界面。
- **证据**：`app/(main)/` 下只有 `dashboard/`。
- **影响**：M3 阶段的界面全部缺失。
- **下一步**：T3.1、T3.3、T2.30、T2.14。

### F5 前端自动化测试 —— 未实现

- **现状**：`frontend/package.json` 无 `test` 脚本；仓库内没有任何前端测试文件。
- **证据**：`frontend` 下不存在 `*.test.ts(x)`；未安装 vitest / jest / Testing Library。
- **影响**：`lib/api.ts` 的类型守卫、`ApiError` 分支、`StatusPanel` 的加载/错误/重试状态都没有自动化回归保护。本次靠「编译 `api.ts` 后直接对真实后端跑三条路径」临时验证（见 F6 说明），但该验证脚本未入库，**下次改动不会自动重跑**。
- **下一步**：先定前端测试框架选型（`docs/TECH_STACK.md` 未列前端测试框架，属于待决策项），再补 `lib/api.ts` 与 `StatusPanel` 的用例。

### F6 浏览器内运行时验证 —— 未执行

- **现状**：已完成的两级验证都不在浏览器内：
  1. `pnpm start` 后抓取 `/`、`/dashboard`、`/login`，三条均 HTTP 200 且包含预期文案（服务端渲染产物正确）；
  2. 把 `lib/api.ts` 编译成 CJS 后用 Node 直连真实 FastAPI，覆盖成功 / 网络不可达 / 非 2xx 三条路径，全部通过。
- **未覆盖**：React 水合是否成功、TanStack Query 在浏览器里的实际请求、点击「重试」是否同时触发两次 refetch、紧凑模式开关是否生效、控制台是否有报错。
- **影响**：组件层的交互契约目前只有代码审查保证，没有运行时证据。
- **下一步**：引入 Playwright（或同类）做 1 条端到端冒烟；在此之前不要声称「面板交互已实测」。

### F7 shadcn/ui —— 未初始化

- **现状**：未执行 `npx shadcn@latest init`，`components/ui/` 不存在。
- **证据**：`frontend/components/` 下只有 `providers.tsx`、`status-panel.tsx`。
- **影响**：按钮 / 输入框等为手写 Tailwind，与 `docs/UI_STYLE.md` 的 token 已对齐，但缺少 shadcn 的可访问性封装。
- **下一步**：T0.6（前端工具链收尾）。

### F8 视觉与无障碍实测 —— 未执行

- **现状**：未跑 Lighthouse，未做移动端真机与屏幕阅读器检查。
- **证据**：本次只做了静态检查（Tailwind 类名不含禁止项、状态不靠颜色单独表达、焦点环已定义）。
- **影响**：`TODO.md` §8 的「Lighthouse ≥ 80」「响应式稳定」两条 DoD 尚未取得证据。
- **下一步**：引入浏览器自动化后一并测（F6）。

### F9 后端全量自检 —— 本条任务未执行

- **现状**：本次只新增 `frontend/`，未修改 `backend/` 任何文件。
- **已做的替代验证**：真启动 FastAPI（`uvicorn main:app`），实测 `/health`、`/version` 的返回字段与类型与 `lib/api.ts` 的类型守卫逐项一致。
- **未做**：`ruff check` / `ruff format --check` / `pytest` 未重跑。
- **影响**：本次改动无法影响后端；但**后端当前是否全绿没有在本次被证明**。
- **下一步**：任何后端改动按 `AGENTS.md` §5.1 重跑三项。

### F10 `any` / `@ts-ignore` 的兜底覆盖 —— 部分覆盖

- **现状**：`frontend/.eslintrc.json` 用 `no-restricted-syntax`（选择器 `TSAnyKeyword`）阻断 `any`，用 `no-warning-comments`（terms `@ts-ignore`）阻断忽略指令；两者已用临时探针文件实测会报错（`no-restricted-syntax` 与 `no-warning-comments` 各命中一次）。
- **未覆盖**：没有前端测试框架，因此无法在运行时兜底；另外若有人绕过 `pnpm lint` 直接提交，也没有 pre-commit 钩子拦截。
- **影响**：约束依赖开发者跑 `pnpm lint`。
- **下一步**：T0.10（CI）把 `pnpm lint` 设为必过门禁。

## 三、被环境限制而跳过的验证（与代码无关）

| 项目 | 限制 | 现状 |
| --- | --- | --- |
| `pnpm install` 默认布局 | Windows 符号链接导致 `ERR_PNPM_SYMLINK_FAILED` | 已用 `frontend/.npmrc` 的 `node-linker=hoisted` 绕过，安装可复现 |
| `next build` 默认 worker | 沙箱禁止带 IPC 具名管道的子进程（`spawn EPERM`） | 已用 `workerThreads: true` + `webpackBuildWorker: false` 绕过，构建可复现 |
| PostgreSQL / Docker | 本机未装 Docker | 与本次前端任务无关；未连真库 |
| 浏览器自动化 | 环境未提供 | 见 F6 |

> 这四条都不是代码缺陷，处理方式与代价记录在 [`mistakes.md`](./mistakes.md)。
