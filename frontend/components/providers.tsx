"use client";

import { QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { getQueryClient } from "@/lib/query-client";

type ProvidersProps = {
  children: ReactNode;
};

/**
 * 客户端 Provider 边界：让 app/layout.tsx 保持 Server Component。
 */
export function Providers({ children }: ProvidersProps) {
  const [queryClient] = useState(() => getQueryClient());

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
