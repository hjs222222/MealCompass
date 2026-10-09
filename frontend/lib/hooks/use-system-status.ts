"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { fetchHealth, fetchVersion, type HealthResponse, type VersionResponse } from "@/lib/api";
import { HEALTH_STALE_TIME_MS, VERSION_STALE_TIME_MS } from "@/lib/query-client";

/** queryKey 是缓存契约，集中在这里，组件里不写字符串数组。 */
export const systemStatusQueryKeys = {
  health: ["system", "health"] as const,
  version: ["system", "version"] as const,
};

export function useHealthQuery(): UseQueryResult<HealthResponse, Error> {
  return useQuery<HealthResponse, Error>({
    queryKey: systemStatusQueryKeys.health,
    queryFn: fetchHealth,
    staleTime: HEALTH_STALE_TIME_MS,
  });
}

export function useVersionQuery(): UseQueryResult<VersionResponse, Error> {
  return useQuery<VersionResponse, Error>({
    queryKey: systemStatusQueryKeys.version,
    queryFn: fetchVersion,
    staleTime: VERSION_STALE_TIME_MS,
  });
}
