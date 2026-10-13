import { parseRecommendResponse, type RecommendRequest, type RecommendResponse } from "./api";

export type RecommendDraft = {
  query: string;
  category: string | null;
  excludedRaw: string;
  topK: string;
};

export type RecommendSession = {
  draft: RecommendDraft;
  lastPayload: RecommendRequest | null;
  result: RecommendResponse | null;
};

export const DEFAULT_RECOMMEND_DRAFT: RecommendDraft = {
  query: "",
  category: null,
  excludedRaw: "",
  topK: "3",
};

export const DEFAULT_RECOMMEND_SESSION: RecommendSession = {
  draft: DEFAULT_RECOMMEND_DRAFT,
  lastPayload: null,
  result: null,
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseDraft(value: unknown): RecommendDraft | null {
  if (!isRecord(value)) {
    return null;
  }
  const category = value.category;
  if (typeof value.query !== "string" || typeof value.excludedRaw !== "string" ||
      typeof value.topK !== "string") {
    return null;
  }
  if (category === null || typeof category === "string") {
    return { query: value.query, category: category as string | null, excludedRaw: value.excludedRaw, topK: value.topK };
  }
  return null;
}

function parsePayload(value: unknown): RecommendRequest | null {
  if (!isRecord(value) || typeof value.query !== "string" ||
      (value.category !== undefined && typeof value.category !== "string") ||
      (value.top_k !== undefined && typeof value.top_k !== "number") ||
      (value.excluded_ingredients !== undefined &&
        (!Array.isArray(value.excluded_ingredients) || !value.excluded_ingredients.every((item) => typeof item === "string")))) {
    return null;
  }
  return value as RecommendRequest;
}

export function restoreRecommendSession(raw: string | null): RecommendSession {
  if (raw === null) {
    return DEFAULT_RECOMMEND_SESSION;
  }
  try {
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value)) {
      return DEFAULT_RECOMMEND_SESSION;
    }
    const draft = parseDraft(value.draft);
    if (draft === null) {
      return DEFAULT_RECOMMEND_SESSION;
    }
    const lastPayload = value.lastPayload === null ? null : parsePayload(value.lastPayload);
    const result = value.result === null ? null : parseRecommendResponse(value.result);
    return { draft, lastPayload, result };
  } catch {
    return DEFAULT_RECOMMEND_SESSION;
  }
}

export function serializeRecommendSession(session: RecommendSession): string {
  return JSON.stringify(session);
}
