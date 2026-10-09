import type { Metadata } from "next";

import { StatusPanel } from "@/components/status-panel";

export const metadata: Metadata = {
  title: "服务状态 · MealCompass",
  description: "查看 FastAPI 后端的健康状态与版本信息。",
};

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <h1 className="font-serif text-3xl tracking-tight text-stone-800 md:text-4xl">服务状态</h1>
        <p className="max-w-2xl text-sm leading-relaxed text-stone-600 md:text-base">
          本页只读取后端两个只读端点：<code className="font-mono text-xs">GET /health</code> 与{" "}
          <code className="font-mono text-xs">GET /version</code>。数据由 TanStack Query 缓存，紧凑模式开关只改界面，
          不触发请求。
        </p>
      </header>

      <StatusPanel />

      <p className="max-w-2xl text-sm leading-relaxed text-stone-600">
        页面刻意不展示推荐结果：推荐 Agent、菜谱详情与购物清单尚未实现，虚假占位会误导使用者。
        未完成能力统一记录在 <code className="font-mono text-xs">docs/failed-features.md</code>。
      </p>
    </div>
  );
}
