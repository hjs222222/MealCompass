# 前端骨架与数据层设计

## 目标

完成 T1.17 与 T1.18，建立可启动、可构建、能调用 FastAPI `/health` 与 `/version` 的 Next.js 前端基线。

## 范围

- Next.js 14 App Router，目录不使用 `src/`。
- `(auth)` 与 `(main)` 路由组，以及默认 Server Component 布局。
- Natural Organic 设计 token，Tailwind v4 CSS-first。
- `lib/api.ts` 类型安全 API 客户端。
- TanStack Query Provider 与 Zustand UI 状态。
- 首页或主页面展示后端健康状态和版本信息。
- loading、error、空数据和 API 失败状态。
- `docs/failed-features.md` 记录尚未实现、跳过测试和环境限制。

不在本阶段实现登录、推荐 Agent、菜谱详情、购物清单或完整业务页面。

## 目录

```text
frontend/
  app/
    layout.tsx
    globals.css
    page.tsx
    loading.tsx
    error.tsx
    (auth)/login/page.tsx
    (main)/dashboard/page.tsx
  components/
    providers.tsx
    status-panel.tsx
  lib/
    api.ts
    query-client.ts
    stores/ui.ts
  package.json
  tsconfig.json
  next.config.mjs
  postcss.config.mjs
```

## 数据流

`dashboard/page.tsx` 使用客户端数据组件，通过 TanStack Query 调用 `lib/api.ts`；API 客户端仅接收 `NEXT_PUBLIC_API_BASE_URL`，默认使用本地 FastAPI 地址。请求返回明确的 TypeScript 模型，错误统一转换为 `ApiError`。Zustand 只保存 UI 状态，不缓存服务端响应。

## 视觉与交互

页面采用简洁的 Natural Organic token：暖白背景、深色文字、绿色强调色和有限圆角。主视图直接展示“服务状态”和“版本”，同时提供加载、失败和重试状态。避免营销式 hero 和嵌套卡片；状态内容使用紧凑、可扫描布局。

## 验收

- `pnpm typecheck`、`pnpm lint`、`pnpm build` 通过。
- 页面能在浏览器加载，且 API 可用时显示 `/health` 与 `/version` 返回值。
- API 不可用时显示可理解的错误状态和重试操作。
- 不使用 TypeScript `any` 或 `@ts-ignore`。
- Zustand 不存 API 响应；TanStack Query 负责服务端数据缓存。
- `docs/failed-features.md` 与 `TODO.md` 明确记录尚未实现能力。
