"use client";

import { useId, useState, type ChangeEvent, type FormEvent } from "react";

import type { RecommendRequest } from "@/lib/api";
import type { RecommendDraft } from "@/lib/recommend-session";

/** 与 backend/domain/models/recommend.py 的字段约束逐项对齐。 */
const QUERY_MAX_LENGTH = 200;
const TOP_K_MIN = 1;
const TOP_K_MAX = 5;

/**
 * 菜谱分类快捷选项。
 *
 * 来源：data/raw/howtocook/ 下的一级目录（breakfast / soup / meat_dish …），
 * 已落库到 recipes.category 列（见 backend/infra/tables.py，有 ix_recipes_category 索引）。
 * 中文译名面向普通用户；英文 slug 原样提交给后端做 SQL 下推。
 *
 * 注意：厨具相关字段（tools_available）虽然还在 RecommendRequest 类型里保留，
 * 但 HowToCook 上游数据不含 tools 字段（import 后 recipes.tools 恒为 []），
 * 因此前端不再展示厨具选择 UI；后端字段保留以备将来接入有厨具数据的源。
 */
const CATEGORY_OPTIONS: { slug: string; label: string }[] = [
  { slug: "breakfast", label: "早餐" },
  { slug: "staple", label: "主食" },
  { slug: "soup", label: "汤品" },
  { slug: "meat_dish", label: "荤菜" },
  { slug: "vegetable_dish", label: "素菜" },
  { slug: "aquatic", label: "水产" },
  { slug: "dessert", label: "甜点" },
  { slug: "drink", label: "饮品" },
];

const INPUT_CLASS =
  "w-full px-5 py-3 bg-white border border-stone-200 rounded-full text-stone-800 placeholder:text-stone-400 focus:border-stone-400 focus:ring-2 focus:ring-stone-200 transition-all duration-300";
const TEXTAREA_CLASS =
  "w-full px-5 py-3 bg-white border border-stone-200 rounded-[2rem] text-stone-800 placeholder:text-stone-400 focus:border-stone-400 focus:ring-2 focus:ring-stone-200 transition-all duration-300";
const LABEL_CLASS = "block text-sm font-medium text-stone-800";
const HINT_CLASS = "mt-1 text-xs leading-relaxed text-stone-600";
const ERROR_CLASS = "mt-1 text-xs text-stone-800";

type FieldErrors = {
  query?: string;
  topK?: string;
};

export type RecommendFormProps = {
  onSubmit: (payload: RecommendRequest) => void;
  isSubmitting: boolean;
  draft: RecommendDraft;
  onDraftChange: (draft: RecommendDraft) => void;
};

/** 中文逗号、顿号、换行也当分隔符——用户不会只打英文逗号。 */
export function parseExcludedIngredients(raw: string): string[] {
  return raw
    .split(/[,，、\n]/)
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function parseIntegerInRange(raw: string, min: number, max: number): number | null | "invalid" {
  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    return null;
  }
  if (!/^\d+$/.test(trimmed)) {
    return "invalid";
  }
  const value = Number.parseInt(trimmed, 10);
  if (!Number.isInteger(value) || value < min || value > max) {
    return "invalid";
  }
  return value;
}

export function RecommendForm({ onSubmit, isSubmitting, draft, onDraftChange }: RecommendFormProps) {
  const fieldId = useId();
  const queryId = `${fieldId}-query`;
  const excludedId = `${fieldId}-excluded`;
  const topKId = `${fieldId}-top-k`;

  const { query, category, excludedRaw, topK } = draft;
  const [errors, setErrors] = useState<FieldErrors>({});

  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();

    const nextErrors: FieldErrors = {};
    const trimmedQuery = query.trim();
    if (trimmedQuery.length === 0) {
      nextErrors.query = "请描述你想吃什么（必填）。";
    } else if (trimmedQuery.length > QUERY_MAX_LENGTH) {
      nextErrors.query = `需求最多 ${QUERY_MAX_LENGTH} 字，当前 ${trimmedQuery.length} 字。`;
    }

    const parsedTopK = parseIntegerInRange(topK, TOP_K_MIN, TOP_K_MAX);
    if (parsedTopK === "invalid") {
      nextErrors.topK = `推荐条数需在 ${TOP_K_MIN}–${TOP_K_MAX} 之间。`;
    }

    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      return;
    }

    onSubmit({
      query: trimmedQuery,
      // tools_available 字段保留在类型里，但上游数据不含厨具，UI 不再收集；
      // 传空数组等价于"不限厨具"，与后端默认行为一致。
      tools_available: [],
      excluded_ingredients: parseExcludedIngredients(excludedRaw),
      top_k: parsedTopK === "invalid" || parsedTopK === null ? 3 : parsedTopK,
      ...(category !== null ? { category } : {}),
    });
  };

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      aria-busy={isSubmitting}
      className="rounded-[2rem] border border-stone-200 theme-surface p-6 md:p-8"
    >
      <h2 className="font-serif text-xl text-stone-800 md:text-2xl">告诉我你想吃什么</h2>
      <p className="mt-2 text-sm leading-relaxed text-stone-600">
        只写「随便」也可以；写清楚忌口会得到更贴近需求的结果。带 <span aria-hidden="true">*</span>{" "}
        的是必填项。
      </p>

      <div className="mt-6 space-y-6">
        <div>
          <label htmlFor={queryId} className={LABEL_CLASS}>
            需求 <span aria-hidden="true">*</span>
            <span className="sr-only">（必填）</span>
          </label>
          <input
            id={queryId}
            name="query"
            type="text"
            required
            maxLength={QUERY_MAX_LENGTH}
            value={query}
            onChange={(event: ChangeEvent<HTMLInputElement>) => onDraftChange({ ...draft, query: event.target.value })}
            aria-invalid={errors.query !== undefined}
            aria-describedby={`${queryId}-hint`}
            placeholder="例如：想吃家常菜，不要香菜"
            className={`mt-2 ${INPUT_CLASS}`}
          />
          <p id={`${queryId}-hint`} className={HINT_CLASS}>
            最多 {QUERY_MAX_LENGTH} 字。
          </p>
          {errors.query !== undefined ? (
            <p role="alert" className={ERROR_CLASS}>
              {errors.query}
            </p>
          ) : null}
        </div>

        <fieldset>
          <legend className={LABEL_CLASS}>按分类挑（可选）</legend>
          <p className={HINT_CLASS}>选一个分类会只在该类菜谱里推荐；不选则全部类别都可。</p>
          <div className="mt-3 flex flex-wrap gap-3">
            {CATEGORY_OPTIONS.map((option) => {
              const checked = category === option.slug;
              return (
                <label
                  key={option.slug}
                  className={`inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-full border px-5 py-2 text-sm transition-colors duration-300 ${
                    checked
                      ? "border-stone-800 bg-stone-800 text-stone-50"
                      : "border-stone-300 bg-transparent text-stone-800 hover:bg-stone-100"
                  }`}
                >
                  <input
                    type="radio"
                    name="category"
                    value={option.slug}
                    checked={checked}
                    onChange={() => onDraftChange({ ...draft, category: checked ? null : option.slug })}
                    className="h-4 w-4 accent-stone-800"
                  />
                  <span>{option.label}</span>
                </label>
              );
            })}
          </div>
        </fieldset>

        <div>
          <label htmlFor={topKId} className={LABEL_CLASS}>
              希望推荐几条
            </label>
            <input
              id={topKId}
              name="top_k"
              type="number"
              inputMode="numeric"
              min={TOP_K_MIN}
              max={TOP_K_MAX}
              step={1}
              value={topK}
              onChange={(event: ChangeEvent<HTMLInputElement>) => onDraftChange({ ...draft, topK: event.target.value })}
              aria-invalid={errors.topK !== undefined}
              aria-describedby={`${topKId}-hint`}
              className={`mt-2 ${INPUT_CLASS}`}
            />
            <p id={`${topKId}-hint`} className={HINT_CLASS}>
              1–{TOP_K_MAX} 条，默认 3 条。
            </p>
            {errors.topK !== undefined ? (
              <p role="alert" className={ERROR_CLASS}>
                {errors.topK}
              </p>
            ) : null}
          </div>

        <div>
          <label htmlFor={excludedId} className={LABEL_CLASS}>
            忌口 / 过敏食材（可选）
          </label>
          <textarea
            id={excludedId}
            name="excluded_ingredients"
            rows={2}
            value={excludedRaw}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => onDraftChange({ ...draft, excludedRaw: event.target.value })}
            aria-describedby={`${excludedId}-hint`}
            placeholder="例如：香菜, 花生、牛奶"
            className={`mt-2 ${TEXTAREA_CLASS}`}
          />
          <p id={`${excludedId}-hint`} className={HINT_CLASS}>
            用逗号、顿号或换行分隔，标准名和常见别名都可以。
          </p>
        </div>
      </div>

      <div className="mt-8 flex flex-wrap items-center gap-4">
        <button
          type="submit"
          disabled={isSubmitting}
          className="min-h-[44px] rounded-full bg-stone-800 px-6 py-3 font-medium text-stone-50 transition-colors duration-300 hover:bg-stone-700 disabled:cursor-not-allowed disabled:bg-stone-400"
        >
          {isSubmitting ? "正在推荐…" : "开始推荐"}
        </button>
        <p className="text-xs leading-relaxed text-stone-600">
          提交会真的调用后端 Agent（含 LLM），可能需要十几秒，请不要重复点击。
        </p>
      </div>
    </form>
  );
}
