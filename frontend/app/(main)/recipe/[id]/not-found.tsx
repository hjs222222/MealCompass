import Link from "next/link";

export default function RecipeNotFound() {
  return (
    <div className="rounded-[2rem] border border-stone-200 theme-surface p-6 md:p-8">
      <h1 className="font-serif text-2xl text-stone-800">没有找到这道菜谱</h1>
      <p className="mt-3 text-sm text-stone-600">菜谱 ID 无效，或这道菜谱已不存在。</p>
      <Link href="/recommend" className="mt-5 inline-flex min-h-[44px] items-center text-stone-800 underline underline-offset-4">返回推荐</Link>
    </div>
  );
}
