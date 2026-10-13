import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { RecipeImages } from "@/components/recommend-results";
import { ApiError, fetchRecipePage } from "@/lib/api";

export const metadata: Metadata = {
  title: "完整菜谱 · MealCompass",
};

export default async function RecipePage({ params }: { params: { id: string } }) {
  let recipe;
  try {
    recipe = await fetchRecipePage(params.id);
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 422)) {
      notFound();
    }
    return (
      <div className="rounded-[2rem] border border-stone-200 theme-surface p-6 md:p-8" role="alert">
        <h1 className="font-serif text-2xl text-stone-800">暂时无法读取菜谱</h1>
        <p className="mt-3 text-sm text-stone-600">请确认后端正在运行，稍后刷新页面。</p>
        <Link href="/recommend" className="mt-5 inline-flex min-h-[44px] items-center text-stone-800 underline underline-offset-4">返回推荐</Link>
      </div>
    );
  }

  const details = recipe.details;
  return (
    <article className="space-y-8">
      <header className="space-y-4">
        <Link href="/recommend" className="inline-flex min-h-[44px] items-center text-sm text-stone-600 underline underline-offset-4 hover:text-stone-800">← 返回推荐</Link>
        <h1 className="font-serif text-3xl tracking-tight text-stone-800 md:text-4xl">{recipe.name}</h1>
        <code className="block break-all text-xs text-stone-500">菜谱 ID：{recipe.recipe_id}</code>
        {details.description ? <p className="whitespace-pre-line text-stone-600">{details.description}</p> : null}
        <div className="flex flex-wrap gap-2 text-xs text-stone-600">
          <span className="rounded-full border border-stone-300 px-3 py-1">耗时：{details.time_text || "原文未注明"}</span>
          <span className="rounded-full border border-stone-300 px-3 py-1">难度：{details.difficulty != null ? `${details.difficulty}/5` : "未知"}</span>
          <span className="rounded-full border border-stone-300 px-3 py-1">热量：{details.calories_kcal != null ? `${details.calories_kcal} 大卡` : "未知"}</span>
        </div>
      </header>

      <RecipeImages name={recipe.name} details={details} />

      <section className="rounded-[2rem] border border-stone-200 theme-surface p-6 md:p-8">
        <h2 className="font-serif text-2xl text-stone-800">原料与用量</h2>
        {details.servings_text ? <p className="mt-2 text-sm text-stone-600">份量：{details.servings_text}</p> : null}
        {details.ingredients.length > 0 ? (
          <ul className="mt-4 list-disc space-y-2 pl-5 text-sm leading-relaxed text-stone-700">
            {details.ingredients.map((ingredient, index) => (
              <li key={`${ingredient.name}-${index}`} className="break-words">
                {ingredient.name}{ingredient.amount_text ? ` · ${ingredient.amount_text}` : " · 用量未注明"}
                {ingredient.per_serving ? "（每份）" : ""}{ingredient.optional ? "（可选）" : ""}
                {ingredient.note ? ` · ${ingredient.note}` : ""}
              </li>
            ))}
          </ul>
        ) : <p className="mt-4 text-sm text-stone-600">暂无原料清单。</p>}
      </section>

      {details.tools.length > 0 ? (
        <section className="rounded-[2rem] border border-stone-200 theme-surface p-6 md:p-8">
          <h2 className="font-serif text-2xl text-stone-800">所需工具</h2>
          <ul className="mt-4 list-disc space-y-2 pl-5 text-sm text-stone-700">
            {details.tools.map((tool, index) => <li key={`${tool}-${index}`}>{tool}</li>)}
          </ul>
        </section>
      ) : null}

      <section className="rounded-[2rem] border border-stone-200 theme-surface p-6 md:p-8">
        <h2 className="font-serif text-2xl text-stone-800">做法步骤</h2>
        {details.steps.length > 0 ? (
          <ol className="mt-4 list-decimal space-y-4 pl-5 text-sm leading-relaxed text-stone-700">
            {details.steps.map((step, index) => <li key={`${recipe.recipe_id}-step-${index}`} className="whitespace-pre-line break-words pl-1">{step}</li>)}
          </ol>
        ) : <p className="mt-4 text-sm text-stone-600">暂无做法步骤。</p>}
      </section>

      {details.extra ? (
        <section className="rounded-[2rem] border border-stone-200 theme-surface p-6 md:p-8">
          <h2 className="font-serif text-2xl text-stone-800">附加说明</h2>
          <p className="mt-4 whitespace-pre-line break-words text-sm leading-relaxed text-stone-700">{details.extra}</p>
        </section>
      ) : null}
      {details.source_url && /^https:\/\//i.test(details.source_url) ? (
        <a href={details.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-[44px] items-center text-sm text-stone-800 underline underline-offset-4 hover:text-stone-600">查看 HowToCook 原菜谱</a>
      ) : null}
    </article>
  );
}
