# Frontend Skeleton and Data Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable Next.js App Router frontend that displays backend health/version data with typed API access, TanStack Query, Zustand UI state, and explicit loading/error states.

**Architecture:** Keep the frontend at `frontend/` without a `src/` prefix. Server layout and route shells remain Server Components; an isolated client status panel owns TanStack Query interactions. `lib/api.ts` owns HTTP and error normalization, TanStack Query owns server state, and Zustand stores only UI preferences.

**Tech Stack:** Next.js 14+, React, TypeScript strict mode, Tailwind CSS v4 CSS-first, TanStack Query v5, Zustand v5, pnpm.

## Global Constraints

- Use App Router; do not use Pages Router or a `src/` prefix.
- Default to Server Components; add `"use client"` only for query/state/event components.
- Do not use TypeScript `any` or `@ts-ignore`.
- TanStack Query stores API responses; Zustand stores UI state only.
- Tailwind v4 tokens live in `app/globals.css` with `@theme`; do not create `tailwind.config.js`.
- Map visual tokens to `docs/UI_STYLE.md` Natural Organic palette; use restrained layout and no marketing-only hero.
- Run `pnpm typecheck`, `pnpm lint`, and `pnpm build` before completion.
- Record unfinished functionality and skipped/environment-limited validation in `docs/failed-features.md`.

---

### Task 1: T1.17 Next.js App Router Skeleton

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/next.config.mjs`
- Create: `frontend/postcss.config.mjs`
- Create: `frontend/app/layout.tsx`
- Create: `frontend/app/globals.css`
- Create: `frontend/app/page.tsx`
- Create: `frontend/app/loading.tsx`
- Create: `frontend/app/error.tsx`
- Create: `frontend/app/(auth)/login/page.tsx`
- Create: `frontend/app/(main)/dashboard/page.tsx`
- Create: `frontend/components/providers.tsx`
- Test/verify: `pnpm typecheck`, `pnpm lint`, `pnpm build`

**Interfaces:**
- Produces a Next.js app runnable with `pnpm dev` and buildable with `pnpm build`.
- Produces route paths `/`, `/login`, and `/dashboard`.
- `Providers({ children }: { children: React.ReactNode })` wraps client-side providers without turning `app/layout.tsx` into a client component.

- [ ] **Step 1: Create the package and strict TypeScript configuration**

Use Next.js 14, React 18, TypeScript 5, Tailwind 4, `@tanstack/react-query` 5, and Zustand 5. Configure `strict`, `noImplicitAny`, `strictNullChecks`, and `noImplicitReturns`.

- [ ] **Step 2: Add failing build baseline**

Run from `frontend/`: `pnpm install` then `pnpm typecheck`.
Expected: fail before route files exist or pass only after the complete skeleton is added; capture any dependency/environment issue in `docs/failed-features.md`.

- [ ] **Step 3: Implement layout and Natural Organic tokens**

Create `app/globals.css` with CSS-first `@theme` variables for background, foreground, muted, accent green, border, radius, and typography. Create a semantic `layout.tsx` with metadata and a stable root wrapper. Do not use gradient backgrounds, excessive rounded cards, or raw prohibited Tailwind colors.

- [ ] **Step 4: Implement route shells and states**

Create a compact root page linking to the dashboard and login. Create dashboard and login route pages with clear headings and restrained panels. Add `app/loading.tsx` and `app/error.tsx`; error component uses only the client directive required for reset interaction.

- [ ] **Step 5: Add provider boundary**

Create `components/providers.tsx` as a client component that accepts `children` and renders the QueryClientProvider created in Task 2. Keep the root layout a Server Component and wrap its children with Providers.

- [ ] **Step 6: Verify and commit**

Run `pnpm typecheck`, `pnpm lint`, and `pnpm build`.
Expected: all commands pass. Commit with `feat: add next app router skeleton`.

---

### Task 2: T1.18 Typed API Client and Query/Data State

**Files:**
- Create: `frontend/lib/api.ts`
- Create: `frontend/lib/query-client.ts`
- Create: `frontend/lib/stores/ui.ts`
- Create: `frontend/components/status-panel.tsx`
- Modify: `frontend/components/providers.tsx`
- Modify: `frontend/app/(main)/dashboard/page.tsx`
- Create: `frontend/.env.example`
- Test/verify: `pnpm typecheck`, `pnpm lint`, `pnpm build`

**Interfaces:**
- `HealthResponse = { status: string; environment: string; tracing_enabled: boolean; tracing_degraded: boolean }`.
- `VersionResponse = { name: string; version: string; environment: string }`.
- `ApiError extends Error` contains `status: number` and optional `code`.
- `fetchHealth(): Promise<HealthResponse>` and `fetchVersion(): Promise<VersionResponse>` throw `ApiError` for non-2xx responses or malformed payloads.
- `useUiStore` stores only `compactMode: boolean` and `toggleCompactMode(): void`.

- [ ] **Step 1: Add typed API client and query client**

Read `NEXT_PUBLIC_API_BASE_URL`, defaulting to `http://localhost:8000`. Use `fetch` with an `Accept: application/json` header. Parse JSON as `unknown`, validate required fields with type guards, and throw `ApiError` with a useful non-secret message on failure.

- [ ] **Step 2: Add QueryClient and Zustand store**

Create one QueryClient per browser runtime with retry limited to one request for transient errors. Configure stale time for health/version. Create a Zustand store containing only UI state; never put HealthResponse or VersionResponse in it.

- [ ] **Step 3: Implement status panel states**

Create a client `StatusPanel` using `useQuery` for both endpoints. Render loading indicators, healthy values, an error message with a retry button, and a compact toggle. Use stable layout dimensions and avoid text overflow. The retry button must call both query refetch functions.

- [ ] **Step 4: Mount status panel on dashboard**

Keep the route page as a Server Component that renders the client panel. Ensure page copy explains current runtime status without pretending unimplemented recommendation features exist.

- [ ] **Step 5: Verify and commit**

Run `pnpm typecheck`, `pnpm lint`, and `pnpm build`. Expected: all pass. Commit with `feat: connect frontend status data layer`.

---

### Task 3: Documentation and Failed-Feature Register

**Files:**
- Create: `docs/failed-features.md`
- Modify: `TODO.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/mistakes.md`

**Interfaces:**
- Documentation records incomplete features without claiming they work.
- TODO marks T1.17 and T1.18 complete only after frontend verification succeeds.

- [ ] **Step 1: Create failed-feature register**

Record at minimum: authentication, recommendation Agent, recipe detail, shopping list, frontend integration tests, and any skipped checks due to missing PostgreSQL/Docker/browser or other environment dependencies. Each entry includes status, evidence, impact, and next task.

- [ ] **Step 2: Synchronize project documents**

Add frontend skeleton/data-layer boundaries to the architecture iteration log. Mark T1.17/T1.18 in `TODO.md` only after checks pass. Append a dated no-failure or failure entry to `docs/mistakes.md`.

- [ ] **Step 3: Run final verification and commit**

Run backend verification only if frontend changes affected backend contracts; otherwise report the existing backend evidence and run all frontend checks. Commit docs with `docs: record frontend baseline and unfinished features`.
