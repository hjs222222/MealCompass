"use client";

import { useEffect, useState } from "react";

import { RecommendForm } from "@/components/recommend-form";
import { RecommendResults } from "@/components/recommend-results";
import type { RecommendRequest } from "@/lib/api";
import { useRecommendMutation } from "@/lib/hooks/use-recommend";
import { DEFAULT_RECOMMEND_SESSION, restoreRecommendSession, serializeRecommendSession, type RecommendDraft } from "@/lib/recommend-session";

const STORAGE_KEY = "mealcompass.recommend.v1";

/**
 * 客户端编排层：同时管理表单草稿、最后一次提交和结果。
 * sessionStorage 仅在当前标签页保存快照；返回/前进时恢复，不会重新调用 Agent。
 */
export function RecommendClient() {
  const mutation = useRecommendMutation();
  const [session, setSession] = useState(DEFAULT_RECOMMEND_SESSION);
  const [restored, setRestored] = useState(false);

  useEffect(() => {
    try {
      setSession(restoreRecommendSession(sessionStorage.getItem(STORAGE_KEY)));
    } catch {
      setSession(DEFAULT_RECOMMEND_SESSION);
    }
    setRestored(true);
  }, []);

  useEffect(() => {
    if (!restored) {
      return;
    }
    try {
      sessionStorage.setItem(STORAGE_KEY, serializeRecommendSession(session));
    } catch {
      // Storage may be disabled or full; in-memory navigation still works until remount.
    }
  }, [restored, session]);

  const handleDraftChange = (draft: RecommendDraft): void => {
    setSession((current) => ({ ...current, draft }));
  };

  const handleSubmit = (payload: RecommendRequest): void => {
    setSession((current) => ({ ...current, lastPayload: payload, result: null }));
    mutation.mutate(payload, {
      onSuccess: (result) => setSession((current) => ({ ...current, result })),
    });
  };

  const handleRetry = (): void => {
    if (session.lastPayload !== null) {
      handleSubmit(session.lastPayload);
    }
  };

  return (
    <div className="space-y-8">
      <RecommendForm onSubmit={handleSubmit} isSubmitting={mutation.isPending} draft={session.draft} onDraftChange={handleDraftChange} />
      <RecommendResults
        result={session.result ?? undefined}
        error={mutation.error}
        isPending={mutation.isPending}
        onRetry={handleRetry}
      />
    </div>
  );
}
