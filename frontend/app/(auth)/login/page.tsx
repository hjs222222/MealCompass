import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "登录 · MealCompass",
  description: "邮箱 + 密码 + JWT 登录（尚未实现）。",
};

export default function LoginPage() {
  return (
    <div className="mx-auto max-w-md space-y-6">
      <header className="space-y-2">
        <h1 className="font-serif text-2xl tracking-tight text-stone-800 md:text-3xl">登录</h1>
        <p className="text-sm leading-relaxed text-stone-600 md:text-base">
          邮箱 + 密码 + JWT 的注册 / 登录属于 T2.15，本阶段尚未实现。
        </p>
      </header>

      <section className="rounded-[2rem] border border-stone-200 bg-[#faf6f1] p-6 md:p-8">
        <p className="rounded-full border border-stone-200 bg-white px-4 py-2 text-xs text-stone-600">
          以下表单仅为样式占位，全部控件已禁用，不会发出任何请求。
        </p>

        <form className="mt-5 space-y-4" aria-describedby="login-unavailable">
          <p id="login-unavailable" className="sr-only">
            登录功能尚未实现。
          </p>

          <div className="space-y-2">
            <label htmlFor="email" className="text-xs text-stone-600">
              邮箱
            </label>
            <input
              id="email"
              name="email"
              type="email"
              disabled
              placeholder="you@example.com"
              className="w-full rounded-full border border-stone-200 bg-white px-5 py-3 text-stone-800 transition-all duration-300 placeholder:text-stone-400 focus:border-stone-400 focus:ring-2 focus:ring-stone-200 disabled:cursor-not-allowed disabled:opacity-60"
            />
          </div>

          <div className="space-y-2">
            <label htmlFor="password" className="text-xs text-stone-600">
              密码
            </label>
            <input
              id="password"
              name="password"
              type="password"
              disabled
              placeholder="至少 8 位"
              className="w-full rounded-full border border-stone-200 bg-white px-5 py-3 text-stone-800 transition-all duration-300 placeholder:text-stone-400 focus:border-stone-400 focus:ring-2 focus:ring-stone-200 disabled:cursor-not-allowed disabled:opacity-60"
            />
          </div>

          <button
            type="button"
            disabled
            className="w-full rounded-full bg-stone-800 px-6 py-3 font-medium text-stone-50 transition-colors duration-300 hover:bg-stone-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            登录（未实现）
          </button>
        </form>
      </section>

      <p className="text-sm text-stone-600">
        返回{" "}
        <Link href="/" className="rounded-full underline decoration-stone-300 underline-offset-4 hover:text-stone-800">
          首页
        </Link>
      </p>
    </div>
  );
}
