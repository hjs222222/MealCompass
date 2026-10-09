import { QueryClient } from "@tanstack/react-query";

/** /health 变化快，短 stale 时间；/version 基本不变，长 stale 时间。 */
export const HEALTH_STALE_TIME_MS = 15_000;
export const VERSION_STALE_TIME_MS = 5 * 60_000;

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // 只对瞬时故障重试一次，避免后端未启动时把浏览器拖长
        retry: 1,
        staleTime: HEALTH_STALE_TIME_MS,
        refetchOnWindowFocus: false,
      },
    },
  });
}

let browserQueryClient: QueryClient | null = null;

/**
 * 浏览器运行时只保留一个 QueryClient；服务端每次渲染新建，避免请求间串数据。
 */
export function getQueryClient(): QueryClient {
  if (typeof window === "undefined") {
    return createQueryClient();
  }
  browserQueryClient ??= createQueryClient();
  return browserQueryClient;
}
