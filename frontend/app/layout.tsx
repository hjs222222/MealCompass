import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { Providers } from "@/components/providers";

import "./globals.css";

export const metadata: Metadata = {
  title: "MealCompass",
  description: "按你的忌口、时间和厨具，推荐能真正做出来的菜。",
};

const NAV_LINKS = [
  { href: "/", label: "首页" },
  { href: "/recommend", label: "推荐" },
  { href: "/dashboard", label: "服务状态" },
  { href: "/login", label: "登录" },
] as const;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-[#faf6f1] font-sans text-stone-800 antialiased">
        <Providers>
          <div className="flex min-h-screen flex-col">
            <nav
              aria-label="主导航"
              className="border-b border-stone-200 bg-[#faf6f1] px-6 md:px-12"
            >
              <div className="mx-auto flex max-w-6xl items-center justify-between gap-6 py-4 md:gap-8">
                <Link href="/" className="font-serif text-xl text-stone-800 md:text-2xl">
                  MealCompass
                </Link>
                <ul className="flex gap-4 text-xs md:gap-8 md:text-sm">
                  {NAV_LINKS.map((link) => (
                    <li key={link.href}>
                      <Link
                        href={link.href}
                        className="rounded-full px-3 py-2 text-stone-600 transition-colors duration-300 hover:bg-stone-100 hover:text-stone-800 focus-visible:bg-stone-100"
                      >
                        {link.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            </nav>

            <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-10 md:px-12 md:py-16">{children}</main>

            <footer className="border-t border-stone-200 bg-white px-6 py-8 text-xs text-stone-600 md:px-12">
              <div className="mx-auto flex max-w-6xl flex-col gap-2">
                <span className="font-serif text-base text-stone-800">MealCompass</span>
                <p>本服务只提供家常烹饪参考，不构成医学建议。</p>
                <p>菜谱数据来自 HowToCook（Unlicense，公有领域）。</p>
              </div>
            </footer>
          </div>
        </Providers>
      </body>
    </html>
  );
}
