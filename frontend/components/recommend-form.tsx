"use client";

import { useId, useState, type ChangeEvent, type FormEvent } from "react";

import type { RecommendRequest } from "@/lib/api";

/** 与 backend/domain/models/recommend.py 的字段约束逐项对齐。 */
const QUERY_MAX_LENGTH = 200;
const TIME_MIN_MINUTES = 1;
const TIME_MAX_MINUTES = 600;
const TOP_K_MIN = 1;
const TOP_K_MAX = 5;

const TOOL_OPTIONS = ["炒锅", "平底锅", "蒸锅", "空气炸锅", "烤箱", "微波炉", "电饭煲"] as const;

const INPUT_CLASS =
  "w-full px-5 py-3 bg-white border border-stone-200 rounded-full text-stone-800 placeholder:text-stone-400 focus:border-stone-400 focus:ring-2 focus:ring-stone-200 transition-all duration-300";
const TEXTAREA_CLASS =
  "w-full px-5 py-3 bg-white border border-stone-200 rounded-[2rem] text-stone-800 placeholder:text-stone-400 focus:border-stone-400 focus:ring-2 focus:ring-stone-200 transition-all duration-300";
const LABEL_CLASS = "block text-sm font-medium text-stone-800";
const HINT_CLASS = "mt-1 text-xs leading-relaxed text-stone-600";
const ERROR_CLASS = "mt-1 text-xs text-stone-800";

type FieldErrors = {
  query?: string;
  maxTimeMinutes?: string;
  topK?: string;
};

export type RecommendFormProps = {
  onSubmit: (payload: RecommendRequest) => void;
  isSubmitting: boolean;
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

export function RecommendForm({ onSubmit, isSubmitting }: RecommendFormProps) {
  const fieldId = useId();
  const queryId = `${fieldId}-query`;
  const timeId = `${fieldId}-time`;
  const toolsId = `${fieldId}-tools`;
  const excludedId = `${fieldId}-excluded`;
  const topKId = `${fieldId}-top-k`;

  const [query, setQuery] = useState("");
  const [maxTimeMinutes, setMaxTimeMinutes] = useState("");
  const [toolsAvailable, setToolsAvailable] = useState<string[]>([]);
  const [excludedRaw, setExcludedRaw] = useState("");
  const [topK, setTopK] = useState("3");
  const [errors, setErrors] = useState<FieldErrors>({});

  const toggleTool = (tool: string): void => {
    setToolsAvailable((current) =>
      current.includes(tool) ? current.filter((item) => item !== tool) : [...current, tool],
    );
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();

    const nextErrors: FieldErrors = {};
    const trimmedQuery = query.trim();
    if (trimmedQuery.length === 0) {
      nextErrors.query = "请描述你想吃什么（必填）。";
    } else if (trimmedQuery.length > QUERY_MAX_LENGTH) {
      nextErrors.query = `需求最多 ${QUERY_MAX_LENGTH} 字，当前 ${trimmedQuery.length} 字。`;
    }

    const parsedTime = parseIntegerInRange(maxTimeMinutes, TIME_MIN_MINUTES, TIME_MAX_MINUTES);
    if (parsedTime === "invalid") {
      nextErrors.maxTimeMinutes = `耗时必须是不超过 ${TIME_MAX_MINUTES} 分钟的正整数。`;
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
      max_time_minutes: parsedTime === "invalid" ? null : parsedTime,
      tools_available: toolsAvailable,
      excluded_ingredients: parseExcludedIngredients(excludedRaw),
      top_k: parsedTopK === "invalid" || parsedTopK === null ? 3 : parsedTopK,
    });
  };

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      aria-busy={isSubmitting}
      className="rounded-[2rem] border border-stone-200 bg-[#faf6f1] p-6 md:p-8"
    >
      <h2 className="font-serif text-xl text-stone-800 md:text-2xl">告诉我你想吃什么</h2>
      <p className="mt-2 text-sm leading-relaxed text-stone-600">
        只写「随便」也可以，但写清楚时间、忌口和厨具会得到更靠谱的结果。带 <span aria-hidden="true">*</span>{" "}
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
            onChange={(event: ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)}
            aria-invalid={errors.query !== undefined}
            aria-describedby={`${queryId}-hint`}
            placeholder="例如：20 分钟内能做的家常菜，不要香菜"
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

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
          <div>
            <label htmlFor={timeId} className={LABEL_CLASS}>
              最长烹饪时间（分钟，可选）
            </label>
            <input
              id={timeId}
              name="max_time_minutes"
              type="number"
              inputMode="numeric"
              min={TIME_MIN_MINUTES}
              max={TIME_MAX_MINUTES}
              step={1}
              value={maxTimeMinutes}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setMaxTimeMinutes(event.target.value)}
              aria-invalid={errors.maxTimeMinutes !== undefined}
              aria-describedby={`${timeId}-hint`}
              placeholder="留空表示不限"
              className={`mt-2 ${INPUT_CLASS}`}
            />
            <p id={`${timeId}-hint`} className={HINT_CLASS}>
              超时的菜会被硬约束直接排除；耗时未知的菜同样按「做不出来」排除。
            </p>
            {errors.maxTimeMinutes !== undefined ? (
              <p role="alert" className={ERROR_CLASS}>
                {errors.maxTimeMinutes}
              </p>
            ) : null}
          </div>

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
              onChange={(event: ChangeEvent<HTMLInputElement>) => setTopK(event.target.value)}
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
        </div>

        <fieldset aria-describedby={`${toolsId}-hint`}>
          <legend className={LABEL_CLASS}>你有哪些厨具（可选）</legend>
          <p id={`${toolsId}-hint`} className={HINT_CLASS}>
            不选表示不限厨具；菜谱用到的厨具必须都在你勾选的范围内。
          </p>
          <div className="mt-3 flex flex-wrap gap-3">
            {TOOL_OPTIONS.map((tool) => {
              const checked = toolsAvailable.includes(tool);
              return (
                <label
                  key={tool}
                  className={`inline-flex min-h-[44px] cursor-pointer items-center gap-2 rounded-full border px-5 py-2 text-sm transition-colors duration-300 ${
                    checked
                      ? "border-stone-800 bg-stone-800 text-stone-50"
                      : "border-stone-300 bg-transparent text-stone-800 hover:bg-stone-100"
                  }`}
                >
                  <input
                    type="checkbox"
                    name="tools_available"
                    value={tool}
                    checked={checked}
                    onChange={() => toggleTool(tool)}
                    className="h-4 w-4 accent-stone-800"
                  />
                  <span>{tool}</span>
                </label>
              );
            })}
          </div>
        </fieldset>

        <div>
          <label htmlFor={excludedId} className={LABEL_CLASS}>
            忌口 / 过敏食材（可选）
          </label>
          <textarea
            id={excludedId}
            name="excluded_ingredients"
            rows={2}
            value={excludedRaw}
            onChange={(event: ChangeEvent<HTMLTextAreaElement>) => setExcludedRaw(event.target.value)}
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
