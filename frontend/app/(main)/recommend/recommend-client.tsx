"use client";

import { useState } from "react";

import { RecommendForm } from "@/components/recommend-form";
import { RecommendResults } from "@/components/recommend-results";
import type { RecommendRequest } from "@/lib/api";
import { useRecommendMutation } from "@/lib/hooks/use-recommend";

/**
 * 客户端编排层：只有它同时知道表单与结果，页面外壳保持 Server Component。
 * 推荐走 mutation，所以结果不会因为窗口聚焦或网络重连被重复执行。
 */
export function RecommendClient() {
  const mutation = useRecommendMutation();
  /** 只用于「重试上一次提交」；结果本身始终以 mutation 的最新状态为准。 */
  const [lastPayload, setLastPayload] = useState<RecommendRequest | null>(null);

  const handleSubmit = (payload: RecommendRequest): void => {
    setLastPayload(payload);
    mutation.mutate(payload);
  };

  const handleRetry = (): void => {
    if (lastPayload !== null) {
      mutation.mutate(lastPayload);
    }
  };

  return (
    <div className="space-y-8">
      <RecommendForm onSubmit={handleSubmit} isSubmitting={mutation.isPending} />
      <RecommendResults
        result={mutation.data}
        error={mutation.error}
        isPending={mutation.isPending}
        onRetry={handleRetry}
      />
    </div>
  );
}
