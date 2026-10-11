import type { Metadata } from "next";

import { RecommendClient } from "./recommend-client";

export const metadata: Metadata = {
  title: "推荐 · MealCompass",
  description: "按你的忌口、可用时间和厨具，调用后端 Agent 推荐能真正做出来的家常菜。",
};

export default function RecommendPage() {
  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <h1 className="font-serif text-3xl tracking-tight text-stone-800 md:text-4xl">今天吃什么</h1>
        <p className="max-w-2xl text-sm leading-relaxed text-stone-600 md:text-base">
          写下需求、时间上限、可用厨具和忌口，页面会调用{" "}
          <code className="font-mono text-xs">POST /recommend</code>
          ，由后端 Agent 做硬约束检索 + 理由生成。硬约束不可满足时后端会显式返回「无解」原因，页面不会把空结果当成功。
        </p>
      </header>

      <RecommendClient />
    </div>
  );
}
