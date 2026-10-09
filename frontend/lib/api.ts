/**
 * 类型安全 API 客户端。
 *
 * 契约来源：backend/api/v1/health.py 的 HealthResponse / VersionResponse。
 * 唯一的环境依赖是 NEXT_PUBLIC_API_BASE_URL；错误一律归一化为 ApiError，
 * 错误信息只包含路径与状态码，不泄露响应体中的任何敏感内容。
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
const REQUEST_TIMEOUT_MS = 8_000;

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

function isAbortError(cause: unknown): boolean {
  return cause instanceof Error && cause.name === "AbortError";
}

async function requestJson(path: string): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (cause) {
    if (isAbortError(cause)) {
      throw new ApiError(`请求超时（${REQUEST_TIMEOUT_MS} ms）：${path}`, {
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
