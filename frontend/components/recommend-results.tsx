"use client";

import { useState } from "react";

import Image from "next/image";
import Link from "next/link";

import { API_BASE_URL, ApiError, type RecipeDetails, type RecommendResponse, type Recommendation } from "@/lib/api";

/**
 * 降级标签 → 人话。
 *
 * 只登记**已被后端确认真实产出**的标签（C3 在 `agents/state.py` 里定义的 7 个常量，
 * 其中 6 个带语义；`recommendation_shortfall` 语义待文档登记，这里**不写死**）。
 * 表里没有的标签一律原样展示 `font-mono` tag，不加注解，不编造含义。
 * 文案只做字面翻译，不断言后端走了哪条召回通道。
 *
 * 注意：`llm_unavailable` 与 `generate_fallback` 会同时出现（LLM 挂了 → 改用规则兜底），
 * 这是真实的两行信息，逐条渲染、不合并、不丢弃。
 */
const DEGRADATION_LABELS: Record<string, string> = {
  parse_intent_failed: "需求解析失败，已退回不加约束的检索",
  generate_fallback: "理由生成未走通，改用规则拼装的兜底理由",
  citation_invalid: "引用校验未通过，非法推荐已被丢弃",
  retrieval_failed: "检索通道失败",
  retrieval_degraded: "检索走了降级路径",
  llm_unavailable: "LLM 不可用",
  recommendation_shortfall: "模型给出的条数不足，已用剩余候选补齐到你要的数量",
};

/** Agent 节点名 → 人话。 */
const NODE_LABELS: Record<string, string> = {
  parse: "解析需求",
  search: "硬约束检索",
  generate: "生成推荐理由",
  validate: "校验引用与硬约束",
  no_solution: "无解终止",
  reflect: "反思重试",
};

const CARD_CLASS = "rounded-[2rem] border border-stone-200 theme-surface p-6 md:p-8";
const TAG_CLASS = "inline-flex items-center rounded-full border border-stone-300 px-3 py-1 text-xs text-stone-600";

function describeError(error: Error): string {
  if (error instanceof ApiError) {
    if (error.code === "network_error") {
      return `连不上后端（${error.message}）。请确认 FastAPI 已在 8000 端口启动。`;
    }
    if (error.code === "timeout") {
      return `后端超时（${error.message}）。推荐要跑检索 + LLM，稍等片刻后可以重试。`;
    }
    return `${error.message}（code=${error.code}）`;
  }
  return error.message;
}

function LoadingSkeleton() {
  return (
    <div aria-busy="true" className="space-y-6">
      <div className="rounded-[2rem] border border-stone-200 theme-surface p-6 md:p-8">
        <div className="h-6 w-52 rounded-full bg-stone-200" />
        <div className="mt-4 h-4 w-64 rounded-full bg-stone-200" />
      </div>
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 md:gap-8">
        {[0, 1].map((index) => (
          <div key={index} className="rounded-[2rem] border border-stone-200 theme-surface p-6 md:p-8">
            <div className="h-6 w-32 rounded-full bg-stone-200" />
            <div className="mt-4 h-4 w-full rounded-full bg-stone-200" />
            <div className="mt-2 h-4 w-4/5 rounded-full bg-stone-200" />
            <div className="mt-4 h-4 w-24 rounded-full bg-stone-200" />
          </div>
        ))}
      </div>
      <p className="text-sm text-stone-600">正在检索菜谱并生成推荐，通常需要 10–30 秒…</p>
    </div>
  );
}

function MetaBar({ result }: { result: RecommendResponse }) {
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-stone-600">
      <span className={TAG_CLASS}>参与决策候选 {result.candidates_considered} 条</span>
      {result.trace_id !== null ? (
        <span className={`${TAG_CLASS} font-mono`}>trace {result.trace_id}</span>
      ) : (
        <span className={TAG_CLASS}>未记录 trace</span>
      )}
    </div>
  );
}

function NodePath({ nodes }: { nodes: string[] }) {
  if (nodes.length === 0) {
    return null;
  }
  return (
    <div className="mt-6">
      <h3 className="font-serif text-base text-stone-800">Agent 执行路径</h3>
      <ol className="mt-2 list-decimal space-y-1 pl-5 text-xs text-stone-600">
        {nodes.map((node, index) => (
          <li key={`${node}-${index}`}>
            <span className="font-mono">{node}</span>
            {NODE_LABELS[node] !== undefined ? <span> · {NODE_LABELS[node]}</span> : null}
          </li>
        ))}
      </ol>
    </div>
  );
}

function DegradationNotice({ result }: { result: RecommendResponse }) {
  if (!result.degraded) {
    return null;
  }
  return (
    <div className="rounded-[2rem] border border-[#d4a373] bg-amber-50 p-6">
      <h3 className="font-serif text-base text-stone-800">本次走了降级路径</h3>
      <p className="mt-1 text-xs leading-relaxed text-stone-600">
        结果仍然可用，但有环节没有按理想路径执行；下面列出实际触发的兜底项。
      </p>
      {result.degradations.length > 0 ? (
        <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-stone-600">
          {result.degradations.map((item, index) => (
            <li key={`${item}-${index}`}>
              <span className="font-mono text-xs">{item}</span>
              {DEGRADATION_LABELS[item] !== undefined ? <span> · {DEGRADATION_LABELS[item]}</span> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-stone-600">后端标记为降级，但未给出具体原因标签。</p>
      )}
    </div>
  );
}

function localImageUrl(path: string): string | null {
  const segments = path.replaceAll("\\", "/").split("/");
  if (segments.some((segment) => segment === "" || segment === "." || segment === "..")) {
    return null;
  }
  return `${API_BASE_URL}/recipe-images/${segments.map(encodeURIComponent).join("/")}`;
}

function RecipeImage({ src, name }: { src: string; name: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return <p className="py-3 text-sm text-stone-600">这张菜谱配图暂时无法加载。</p>;
  }
  return (
    <div className="relative aspect-[4/3] overflow-hidden rounded-[2rem] bg-stone-200">
      <Image src={src} alt={`${name}的菜谱配图`} fill sizes="(max-width: 768px) 100vw, 50vw"
        className="object-contain" loading="lazy" unoptimized onError={() => setFailed(true)} />
    </div>
  );
}

export function RecipeImages({ name, details }: { name: string; details: RecipeDetails | null }) {
  const sources = [
    ...(details?.images ?? []).map(localImageUrl).filter((url): url is string => url !== null),
    ...(details?.external_images ?? []).filter((url) => /^https:\/\/[^/]+/i.test(url)),
  ];
  if (sources.length === 0) {
    return <p className="mt-4 text-sm text-stone-600">暂无菜谱配图。</p>;
  }
  return (
    <figure className="mt-5">
      <RecipeImage key={sources[0]} src={sources[0]} name={name} />
      {sources.length > 1 ? (
        <details className="mt-2">
          <summary className="min-h-[44px] cursor-pointer py-3 text-sm text-stone-800 hover:text-stone-600">
            查看其余配图（{sources.length - 1} 张）
          </summary>
          <div className="space-y-4">
            {sources.slice(1).map((src, index) => <RecipeImage key={`${src}-${index}`} src={src} name={name} />)}
          </div>
        </details>
      ) : null}
    </figure>
  );
}

function RecommendationCard({ item }: { item: Recommendation }) {
  const recipeUrl = `/recipe/${encodeURIComponent(item.recipe_id)}`;
  return (
    <article className={CARD_CLASS}>
      <div className="flex flex-col items-end gap-2">
        <code className="max-w-full break-all text-right text-[10px] leading-relaxed text-stone-500" title="菜谱 ID">{item.recipe_id}</code>
        <h3 className="self-start font-serif text-xl text-stone-800 md:text-2xl">
          <Link href={recipeUrl} className="rounded-lg underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-stone-700">{item.name}</Link>
        </h3>
      </div>
      <p className="mt-3 text-sm leading-relaxed text-stone-600 md:text-base">{item.reason}</p>

      <RecipeImages name={item.name} details={item.details} />
      <div className="mt-4 flex flex-wrap gap-2" aria-label="菜谱信息">
        <span className={TAG_CLASS}>耗时：{item.details === null ? "详情暂未读取" : item.details.time_text || "原文未注明"}</span>
        <span className={TAG_CLASS}>难度：{item.details?.difficulty != null ? `${item.details.difficulty}/5` : "未知"}</span>
        <span className={TAG_CLASS}>
          热量：{item.details?.calories_kcal != null ? `${item.details.calories_kcal} 大卡` : "未知"}
        </span>
      </div>
      <Link href={recipeUrl} className="mt-5 inline-flex min-h-[44px] items-center rounded-full border border-stone-300 px-5 py-3 text-sm font-medium text-stone-800 transition-colors duration-300 hover:bg-stone-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-stone-700">
        查看完整菜谱（原料、工具与做法）
      </Link>

      {item.substitutions.length > 0 ? (
        <div className="mt-4">
          <h4 className="text-xs font-medium text-stone-800">替代建议</h4>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-stone-600">
            {item.substitutions.map((substitution, index) => (
              <li key={`${substitution}-${index}`}>{substitution}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </article>
  );
}

export type RecommendResultsProps = {
  result: RecommendResponse | undefined;
  error: Error | null;
  isPending: boolean;
  onRetry: () => void;
};

export function RecommendResults({ result, error, isPending, onRetry }: RecommendResultsProps) {
  return (
    <section aria-live="polite" aria-busy={isPending} className="space-y-6">
      {isPending ? <LoadingSkeleton /> : null}

      {!isPending && error !== null ? (
        <div role="alert" className={`${CARD_CLASS} space-y-3`}>
          <h2 className="font-serif text-xl text-stone-800 md:text-2xl">没能拿到推荐结果</h2>
          <p className="break-words text-sm leading-relaxed text-stone-600">{describeError(error)}</p>
          <button
            type="button"
            onClick={onRetry}
            className="min-h-[44px] rounded-full bg-stone-800 px-6 py-3 font-medium text-stone-50 transition-colors duration-300 hover:bg-stone-700"
          >
            重试
          </button>
        </div>
      ) : null}

      {!isPending && error === null && result === undefined ? (
        <div className={`${CARD_CLASS} space-y-3`}>
          <h2 className="font-serif text-xl text-stone-800 md:text-2xl">还没有推荐结果</h2>
          <p className="text-sm leading-relaxed text-stone-600">
            在上面的表单里写下你的需求，提交后会调用后端 Agent 检索并生成推荐。
          </p>
        </div>
      ) : null}

      {!isPending && error === null && result !== undefined ? (
        result.no_solution_reason !== null ? (
          <div className={`${CARD_CLASS} space-y-3`}>
            <h2 className="font-serif text-xl text-stone-800 md:text-2xl">这次没有可推荐的菜</h2>
            <p className="text-sm leading-relaxed text-stone-600">
              硬约束无法同时满足，后端给的原因如下。这里是「无解」而不是「没有结果」，空列表不代表成功。
            </p>
            <p className="break-words text-sm leading-relaxed text-stone-800">
              <span className="font-mono text-xs">{result.no_solution_reason}</span>
            </p>
            <MetaBar result={result} />
            <DegradationNotice result={result} />
            <NodePath nodes={result.node_path} />
          </div>
        ) : result.recommendations.length === 0 ? (
          <div role="alert" className={`${CARD_CLASS} space-y-3`}>
            <h2 className="font-serif text-xl text-stone-800 md:text-2xl">结果为空且没有说明</h2>
            <p className="text-sm leading-relaxed text-stone-600">
              后端返回了 0 条推荐，却没有给出 <code className="font-mono text-xs">no_solution_reason</code>
              。这属于契约异常，请连同下面的 trace 信息反馈。
            </p>
            <MetaBar result={result} />
            <NodePath nodes={result.node_path} />
          </div>
        ) : (
          <div className="space-y-6">
            <div className={`${CARD_CLASS} space-y-3`}>
              <h2 className="font-serif text-xl text-stone-800 md:text-2xl">
                为你找到 {result.recommendations.length} 道菜
              </h2>
              <p className="text-sm leading-relaxed text-stone-600">
                查询：「{result.query}」。每条推荐都对应真实菜谱，点击菜名或查看完整菜谱可阅读原料与做法。
              </p>
              <MetaBar result={result} />
            </div>

            <DegradationNotice result={result} />

            <div className="recommend-grid grid grid-cols-1 gap-6 md:grid-cols-2 md:gap-8">
              {result.recommendations.map((item) => (
                <RecommendationCard key={item.recipe_id} item={item} />
              ))}
            </div>

            <NodePath nodes={result.node_path} />
          </div>
        )
      ) : null}
    </section>
  );
}
