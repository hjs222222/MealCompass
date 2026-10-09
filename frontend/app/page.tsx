import Link from "next/link";
import type { ReactNode } from "react";

type CardProps = {
  title: string;
  children: ReactNode;
};

function Card({ title, children }: CardProps) {
  return (
    <section className="rounded-[2rem] border border-stone-200 bg-[#faf6f1] p-6 md:p-8">
      <h2 className="font-serif text-xl text-stone-800 md:text-2xl">{title}</h2>
      <div className="mt-3 text-sm leading-relaxed text-stone-600 md:text-base">{children}</div>
    </section>
  );
}

export default function HomePage() {
  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <h1 className="font-serif text-3xl tracking-tight text-stone-800 md:text-4xl">MealCompass</h1>
        <p className="max-w-xl text-sm leading-relaxed text-stone-600 md:text-base">
          按你的忌口、可用时间和厨具，推荐能真正做出来的家常菜。当前仓库处于 M1 阶段，前端只完成了骨架与数据层。
        </p>
      </header>

      <div className="flex flex-wrap gap-4">
        <Link
          href="/dashboard"
          className="rounded-full bg-stone-800 px-6 py-3 font-medium text-stone-50 transition-colors duration-300 hover:bg-stone-700"
        >
          查看服务状态
        </Link>
        <Link
          href="/login"
          className="rounded-full border border-stone-300 px-6 py-3 font-medium text-stone-800 transition-colors duration-300 hover:bg-stone-100"
        >
          登录（未实现）
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 md:gap-8">
        <Card title="本阶段已完成">
          <ul className="list-disc space-y-1 pl-5">
            <li>Next.js App Router 骨架与路由组</li>
            <li>类型安全 API 客户端（/health、/version）</li>
            <li>TanStack Query 服务端状态 + Zustand 界面状态</li>
            <li>加载 / 错误 / 空状态与重试</li>
          </ul>
        </Card>
        <Card title="尚未实现">
          <ul className="list-disc space-y-1 pl-5">
            <li>注册与登录（T2.15）</li>
            <li>推荐 Agent 与对话（T2.16-T2.26）</li>
            <li>菜谱详情与购物清单（T2.27、T3.1）</li>
            <li>前端自动化测试</li>
          </ul>
          <p className="mt-3">
            完整清单见 <code className="font-mono text-xs">docs/failed-features.md</code>。
          </p>
        </Card>
      </div>
    </div>
  );
}
