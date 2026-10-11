"use client";

import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { fetchRecommendations, type RecommendRequest, type RecommendResponse } from "@/lib/api";

/**
 * queryKey 是缓存契约，集中在这里，组件里不写字符串数组。
 * 推荐走 mutation（有副作用、结果与本次输入一一对应），这里的 key 只用于
 * `mutate` 的失效与调试标记，不参与自动 refetch。
 */
export const recommendQueryKeys = {
  all: ["recommend"] as const,
  recommendation: (payload: RecommendRequest) => ["recommend", "result", payload] as const,
} as const;

/**
 * 推荐是 mutation 而不是 query：一次提交对应一次真实的 Agent 执行（含 LLM 调用），
 * 不应该被窗口聚焦、重连或 staleTime 触发重复执行。
 */
export function useRecommendMutation(): UseMutationResult<
  RecommendResponse,
  Error,
  RecommendRequest
> {
  return useMutation<RecommendResponse, Error, RecommendRequest>({
    mutationKey: recommendQueryKeys.all,
    mutationFn: fetchRecommendations,
    retry: 0,
  });
}
