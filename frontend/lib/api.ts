/**
 * 类型安全 API 客户端。
 *
 * 契约来源：
 * - GET  /health、/version → backend/api/v1/health.py
 * - POST /recommend、/recipes/search → backend/domain/models/recommend.py（C1 冻结契约）
 *
 * 唯一的环境依赖是 NEXT_PUBLIC_API_BASE_URL；错误一律归一化为 ApiError，
 * 错误信息只包含路径与状态码，不泄露响应体中的任何敏感内容。
 *
 * 类型守卫原则（与 C1 Pydantic 模型对齐）：
 * - 模型里**没有默认值**的字段（query、candidates_considered、每条推荐的 recipe_id/name/reason）
 *   必须存在且类型正确，否则视为 invalid_payload；
 * - 模型里**有默认值**的字段（list 走 default_factory、可空字段走 None）缺失时按默认值处理，
 *   只有「存在但类型不对」才算 invalid_payload —— 这样既拦住真实契约漂移，又不因为
 *   `exclude_none` 之类的序列化差异误伤。
 */

export type HealthResponse = {
  status: string;
  environment: string;
  tracing_enabled: boolean;
  tracing_degraded: boolean;
};

export type VersionResponse = {
  name: string;
  version: string;
  environment: string;
};

/** backend/domain/models/recipe.py::Ingredient 与 recipe_details.py::RecipeDetails */
export type RecipeIngredient = {
  name: string;
  amount_text: string | null;
  note: string | null;
  optional: boolean;
  per_serving: boolean;
};

export type RecipeDetails = {
  description: string | null;
  time_text: string | null;
  difficulty: number | null;
  calories_kcal: number | null;
  calories_source: string | null;
  servings_text: string | null;
  ingredients: RecipeIngredient[];
  tools: string[];
  steps: string[];
  images: string[];
  external_images: string[];
  extra: string | null;
  source_url: string | null;
};

export type RecipePage = {
  recipe_id: string;
  name: string;
  details: RecipeDetails;
};

/** backend/domain/models/recommendation.py::Recommendation */
export type Recommendation = {
  recipe_id: string;
  name: string;
  reason: string;
  missing_ingredients: string[];
  substitutions: string[];
  steps: string[];
  time_minutes: number | null;
  details: RecipeDetails | null;
};

/** backend/domain/models/retrieval.py::RecipeCandidate */
export type RecipeCandidate = {
  recipe_id: string;
  name: string;
  score: number;
  rank: number | null;
  sources: string[];
  matched_step_no: number | null;
  matched_step_content: string | null;
  rerank_score: number | null;
  degraded: boolean;
};

/** backend/domain/models/recommend.py::RecommendRequest */
export type RecommendRequest = {
  query: string;
  max_time_minutes?: number | null;
  tools_available?: string[];
  excluded_ingredients?: string[];
  category?: string | null;
  top_k?: number;
};

/** backend/domain/models/recommend.py::RecommendResponse */
export type RecommendResponse = {
  query: string;
  recommendations: Recommendation[];
  candidates_considered: number;
  no_solution_reason: string | null;
  degraded: boolean;
  degradations: string[];
  node_path: string[];
  trace_id: string | null;
};

/** backend/domain/models/recommend.py::SearchRequest */
export type SearchRequest = {
  query: string;
  max_time_minutes?: number | null;
  tools_available?: string[];
  excluded_ingredients?: string[];
  category?: string | null;
  top_k?: number;
};

/** backend/domain/models/recommend.py::SearchResponse */
export type SearchResponse = {
  query: string;
  candidates: RecipeCandidate[];
  degraded: boolean;
  degradations: string[];
};

export type ApiErrorCode = "network_error" | "timeout" | "http_error" | "invalid_json" | "invalid_payload";

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode;

  constructor(message: string, options: { status: number; code: ApiErrorCode; cause?: unknown }) {
    super(message, options.cause === undefined ? undefined : { cause: options.cause });
    this.name = "ApiError";
    this.status = options.status;
    this.code = options.code;
  }
}

const DEFAULT_API_BASE_URL = "http://localhost:8000";

/** 只读端点的默认超时：后端没启动时尽快失败，不让页面一直转圈。 */
const REQUEST_TIMEOUT_MS = 8_000;

/** 推荐端点要跑规则 + 检索 + LLM，8s 明显不够；单独给 30s。 */
export const RECOMMEND_TIMEOUT_MS = 30_000;

/** 检索端点要跑向量 + BM25 + RRF/重排，比只读端点慢，给 15s。 */
export const SEARCH_TIMEOUT_MS = 15_000;

export const API_BASE_URL: string = normalizeBaseUrl(
  process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL,
);

function normalizeBaseUrl(raw: string): string {
  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    return DEFAULT_API_BASE_URL;
  }
  return trimmed.endsWith("/") ? trimmed.slice(0, -1) : trimmed;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readString(source: Record<string, unknown>, key: string): string | null {
  const value = source[key];
  return typeof value === "string" ? value : null;
}

function readBoolean(source: Record<string, unknown>, key: string): boolean | null {
  const value = source[key];
  return typeof value === "boolean" ? value : null;
}

/** 严格数字守卫：只接受有限数字（拒绝 NaN / Infinity / 数字字符串）。 */
function readNumber(source: Record<string, unknown>, key: string): number | null {
  const value = source[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/** 数组守卫：缺失按空数组（对应 Pydantic 的 default_factory），存在但不是数组 → null。 */
function readArray(source: Record<string, unknown>, key: string): unknown[] | null {
  const value = source[key];
  if (value === undefined) {
    return [];
  }
  return Array.isArray(value) ? value : null;
}

function readStringArray(source: Record<string, unknown>, key: string): string[] | null {
  const items = readArray(source, key);
  if (items === null) {
    return null;
  }
  return items.every((item) => typeof item === "string") ? (items as string[]) : null;
}

/** 可空字符串：JSON null / 缺失 / 非字符串统一归一化为 null（字段默认值语义）。 */
function readNullableString(source: Record<string, unknown>, key: string): string | null {
  const value = source[key];
  return typeof value === "string" ? value : null;
}

/** 可空数字：同上，非有限数字一律当 null（展示层显示“未知”，不猜值）。 */
function readNullableNumber(source: Record<string, unknown>, key: string): number | null {
  const value = source[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function parseHealth(payload: unknown): HealthResponse | null {
  if (!isRecord(payload)) {
    return null;
  }
  const status = readString(payload, "status");
  const environment = readString(payload, "environment");
  const tracingEnabled = readBoolean(payload, "tracing_enabled");
  const tracingDegraded = readBoolean(payload, "tracing_degraded");
  if (status === null || environment === null || tracingEnabled === null || tracingDegraded === null) {
    return null;
  }
  return {
    status,
    environment,
    tracing_enabled: tracingEnabled,
    tracing_degraded: tracingDegraded,
  };
}

function parseVersion(payload: unknown): VersionResponse | null {
  if (!isRecord(payload)) {
    return null;
  }
  const name = readString(payload, "name");
  const version = readString(payload, "version");
  const environment = readString(payload, "environment");
  if (name === null || version === null || environment === null) {
    return null;
  }
  return { name, version, environment };
}

function parseRecipeIngredient(payload: unknown): RecipeIngredient | null {
  if (!isRecord(payload)) {
    return null;
  }
  const name = readString(payload, "name");
  if (name === null) {
    return null;
  }
  return {
    name,
    amount_text: readNullableString(payload, "amount_text"),
    note: readNullableString(payload, "note"),
    optional: readBoolean(payload, "optional") ?? false,
    per_serving: readBoolean(payload, "per_serving") ?? false,
  };
}

function parseRecipeDetails(payload: unknown): RecipeDetails | null {
  if (!isRecord(payload)) {
    return null;
  }
  const rawIngredients = readArray(payload, "ingredients");
  const tools = readStringArray(payload, "tools");
  const steps = readStringArray(payload, "steps");
  const images = readStringArray(payload, "images");
  const externalImages = readStringArray(payload, "external_images");
  if (rawIngredients === null || tools === null || steps === null || images === null || externalImages === null) {
    return null;
  }
  const ingredients: RecipeIngredient[] = [];
  for (const ingredient of rawIngredients) {
    const parsed = parseRecipeIngredient(ingredient);
    if (parsed === null) {
      return null;
    }
    ingredients.push(parsed);
  }
  return {
    description: readNullableString(payload, "description"),
    time_text: readNullableString(payload, "time_text"),
    difficulty: readNullableNumber(payload, "difficulty"),
    calories_kcal: readNullableNumber(payload, "calories_kcal"),
    calories_source: readNullableString(payload, "calories_source"),
    servings_text: readNullableString(payload, "servings_text"),
    ingredients,
    tools,
    steps,
    images,
    external_images: externalImages,
    extra: readNullableString(payload, "extra"),
    source_url: readNullableString(payload, "source_url"),
  };
}

function parseRecipePage(payload: unknown): RecipePage | null {
  if (!isRecord(payload)) {
    return null;
  }
  const recipeId = readString(payload, "recipe_id");
  const name = readString(payload, "name");
  const details = parseRecipeDetails(payload.details);
  return recipeId !== null && name !== null && details !== null
    ? { recipe_id: recipeId, name, details }
    : null;
}

function parseRecommendation(payload: unknown): Recommendation | null {
  if (!isRecord(payload)) {
    return null;
  }
  const recipeId = readString(payload, "recipe_id");
  const name = readString(payload, "name");
  const reason = readString(payload, "reason");
  const missing = readStringArray(payload, "missing_ingredients");
  const substitutions = readStringArray(payload, "substitutions");
  const steps = payload.steps === undefined ? [] : readStringArray(payload, "steps");
  if (recipeId === null || name === null || reason === null || missing === null || substitutions === null || steps === null) {
    return null;
  }
  const detailsPayload = payload.details;
  const details = detailsPayload === undefined || detailsPayload === null ? null : parseRecipeDetails(detailsPayload);
  if (detailsPayload !== undefined && detailsPayload !== null && details === null) {
    return null;
  }
  return {
    recipe_id: recipeId,
    name,
    reason,
    missing_ingredients: missing,
    substitutions,
    steps,
    time_minutes: readNullableNumber(payload, "time_minutes"),
    details,
  };
}

function parseRecipeCandidate(payload: unknown): RecipeCandidate | null {
  if (!isRecord(payload)) {
    return null;
  }
  const recipeId = readString(payload, "recipe_id");
  const name = readString(payload, "name");
  const score = readNumber(payload, "score");
  const sources = readStringArray(payload, "sources");
  if (recipeId === null || name === null || score === null || sources === null) {
    return null;
  }
  return {
    recipe_id: recipeId,
    name,
    score,
    rank: readNullableNumber(payload, "rank"),
    sources,
    matched_step_no: readNullableNumber(payload, "matched_step_no"),
    matched_step_content: readNullableString(payload, "matched_step_content"),
    rerank_score: readNullableNumber(payload, "rerank_score"),
    degraded: readBoolean(payload, "degraded") ?? false,
  };
}

export function parseRecommendResponse(payload: unknown): RecommendResponse | null {
  if (!isRecord(payload)) {
    return null;
  }
  const query = readString(payload, "query");
  const candidatesConsidered = readNumber(payload, "candidates_considered");
  const rawItems = readArray(payload, "recommendations");
  const degradations = readStringArray(payload, "degradations");
  const nodePath = readStringArray(payload, "node_path");
  if (
    query === null ||
    candidatesConsidered === null ||
    rawItems === null ||
    degradations === null ||
    nodePath === null
  ) {
    return null;
  }
  const recommendations: Recommendation[] = [];
  for (const item of rawItems) {
    const parsed = parseRecommendation(item);
    if (parsed === null) {
      return null;
    }
    recommendations.push(parsed);
  }
  return {
    query,
    recommendations,
    candidates_considered: candidatesConsidered,
    no_solution_reason: readNullableString(payload, "no_solution_reason"),
    degraded: readBoolean(payload, "degraded") ?? false,
    degradations,
    node_path: nodePath,
    trace_id: readNullableString(payload, "trace_id"),
  };
}

function parseSearchResponse(payload: unknown): SearchResponse | null {
  if (!isRecord(payload)) {
    return null;
  }
  const query = readString(payload, "query");
  const rawItems = readArray(payload, "candidates");
  const degradations = readStringArray(payload, "degradations");
  if (query === null || rawItems === null || degradations === null) {
    return null;
  }
  const candidates: RecipeCandidate[] = [];
  for (const item of rawItems) {
    const parsed = parseRecipeCandidate(item);
    if (parsed === null) {
      return null;
    }
    candidates.push(parsed);
  }
  return {
    query,
    candidates,
    degraded: readBoolean(payload, "degraded") ?? false,
    degradations,
  };
}

function isAbortError(cause: unknown): boolean {
  return cause instanceof Error && cause.name === "AbortError";
}

type RequestOptions = {
  /** 默认 GET —— 不传 body 时行为与改造前完全一致。 */
  method?: "GET" | "POST";
  /** 存在即序列化为 JSON body，并补 Content-Type。 */
  body?: unknown;
  /** 默认 8s；推荐 / 检索端点各自传更长的值。 */
  timeoutMs?: number;
};

async function requestJson(path: string, options: RequestOptions = {}): Promise<unknown> {
  const method = options.method ?? "GET";
  const timeoutMs = options.timeoutMs ?? REQUEST_TIMEOUT_MS;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const headers: Record<string, string> = { Accept: "application/json" };
  const init: RequestInit = {
    method,
    headers,
    cache: "no-store",
    signal: controller.signal,
  };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch (cause) {
    if (isAbortError(cause)) {
      throw new ApiError(`请求超时（${timeoutMs} ms）：${path}`, {
        status: 0,
        code: "timeout",
        cause,
      });
    }
    throw new ApiError(`无法连接后端（${API_BASE_URL}）：${path}`, {
      status: 0,
      code: "network_error",
      cause,
    });
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    throw new ApiError(`后端返回 HTTP ${response.status}：${path}`, {
      status: response.status,
      code: "http_error",
    });
  }

  try {
    return (await response.json()) as unknown;
  } catch (cause) {
    throw new ApiError(`响应不是合法 JSON：${path}`, {
      status: response.status,
      code: "invalid_json",
      cause,
    });
  }
}

export async function fetchHealth(): Promise<HealthResponse> {
  const parsed = parseHealth(await requestJson("/health"));
  if (parsed === null) {
    throw new ApiError("健康检查响应缺少必需字段或类型不符：/health", {
      status: 200,
      code: "invalid_payload",
    });
  }
  return parsed;
}

export async function fetchVersion(): Promise<VersionResponse> {
  const parsed = parseVersion(await requestJson("/version"));
  if (parsed === null) {
    throw new ApiError("版本响应缺少必需字段或类型不符：/version", {
      status: 200,
      code: "invalid_payload",
    });
  }
  return parsed;
}

/** POST /recommend：规则硬约束 + 检索 + LLM 生成理由的最小闭环。 */
export async function fetchRecommendations(payload: RecommendRequest): Promise<RecommendResponse> {
  const parsed = parseRecommendResponse(
    await requestJson("/recommend", {
      method: "POST",
      body: payload,
      timeoutMs: RECOMMEND_TIMEOUT_MS,
    }),
  );
  if (parsed === null) {
    throw new ApiError("推荐响应缺少必需字段或类型不符：/recommend", {
      status: 200,
      code: "invalid_payload",
    });
  }
  return parsed;
}

/** POST /recipes/search：只取检索候选（供「先看候选」与评估脚本复用）。 */
export async function fetchSearch(payload: SearchRequest): Promise<SearchResponse> {
  const parsed = parseSearchResponse(
    await requestJson("/recipes/search", {
      method: "POST",
      body: payload,
      timeoutMs: SEARCH_TIMEOUT_MS,
    }),
  );
  if (parsed === null) {
    throw new ApiError("检索响应缺少必需字段或类型不符：/recipes/search", {
      status: 200,
      code: "invalid_payload",
    });
  }
  return parsed;
}

export async function fetchRecipePage(recipeId: string): Promise<RecipePage> {
  const parsed = parseRecipePage(await requestJson(`/recipes/${encodeURIComponent(recipeId)}`));
  if (parsed === null) {
    throw new ApiError("菜谱详情响应缺少必需字段或类型不符", {
      status: 200,
      code: "invalid_payload",
    });
  }
  return parsed;
}
