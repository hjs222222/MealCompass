"use client";

import { useEffect } from "react";

type ErrorPageProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

export default function ErrorPage({ error, reset }: ErrorPageProps) {
  useEffect(() => {
    console.error("[MealCompass] 页面渲染失败", error.message);
  }, [error]);

  return (
    <div className="rounded-[2rem] border border-stone-200 bg-[#faf6f1] p-6 md:p-8" role="alert">
      <h1 className="font-serif text-xl text-stone-800 md:text-2xl">页面出错了</h1>
      <p className="mt-3 text-sm leading-relaxed text-stone-600 md:text-base">
        渲染过程中发生未处理的错误。可以重试；若持续失败，请查看后端与浏览器控制台日志。
      </p>
      <p className="mt-2 font-mono text-xs text-stone-600">{error.message}</p>
      <button
        type="button"
        onClick={reset}
        className="mt-6 rounded-full bg-stone-800 px-6 py-3 font-medium text-stone-50 transition-colors duration-300 hover:bg-stone-700"
      >
        重试
      </button>
    </div>
  );
}
