"use client";

import { ApiError } from "@/lib/api";
import { useHealthQuery, useVersionQuery } from "@/lib/hooks/use-system-status";
import { useUiStore } from "@/lib/stores/ui";

type FieldProps = {
  label: string;
  value: string;
};

function Field({ label, value }: FieldProps) {
  const display = value.trim().length === 0 ? "—" : value;
  return (
    <div className="border-t border-stone-200 pt-3 first:border-t-0 first:pt-0">
      <dt className="text-xs text-stone-600">{label}</dt>
      <dd className="mt-1 break-words font-mono text-sm text-stone-800">{display}</dd>
    </div>
  );
}

function describeError(error: Error): string {
  if (error instanceof ApiError) {
    return `${error.message}（code=${error.code}, status=${error.status}）`;
  }
  return error.message;
}

function Skeleton() {
  return (
    <div className="space-y-3">
      <div className="h-5 w-40 rounded-full bg-stone-200" />
      <div className="h-4 w-64 rounded-full bg-stone-200" />
      <div className="h-4 w-52 rounded-full bg-stone-200" />
    </div>
  );
}

export function StatusPanel() {
  const health = useHealthQuery();
  const version = useVersionQuery();
  const compactMode = useUiStore((state) => state.compactMode);
  const toggleCompactMode = useUiStore((state) => state.toggleCompactMode);

  const errors = [health.error, version.error].filter((error): error is Error => error !== null);
  const isLoading = health.isPending || version.isPending;
  const hasError = errors.length > 0;
  const healthData = health.data;
  const versionData = version.data;

  const refetchAll = (): void => {
    void health.refetch();
    void version.refetch();
  };

  return (
    <section
      aria-labelledby="status-panel-title"
      className={`rounded-[2rem] border border-stone-200 bg-[#faf6f1] ${compactMode ? "p-4" : "p-6 md:p-8"}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h2 id="status-panel-title" className="font-serif text-xl text-stone-800 md:text-2xl">
          服务状态
        </h2>
        <button
          type="button"
          onClick={toggleCompactMode}
          aria-pressed={compactMode}
          className="rounded-full border border-stone-300 px-6 py-3 text-xs font-medium text-stone-800 transition-colors duration-300 hover:bg-stone-100"
        >
          {compactMode ? "紧凑模式：开" : "紧凑模式：关"}
        </button>
      </div>

      <div aria-live="polite" className="mt-5 min-h-[9rem]">
        {isLoading ? (
          <div className="space-y-3">
            <Skeleton />
            <p className="text-sm text-stone-600">正在读取后端状态…</p>
          </div>
        ) : hasError ? (
          <div role="alert" className="space-y-3">
            <p className="text-sm font-medium text-stone-800">无法读取后端状态</p>
            <ul className="space-y-1 text-sm text-stone-600">
              {errors.map((error) => (
                <li key={error.message} className="break-words">
                  {describeError(error)}
                </li>
              ))}
            </ul>
            <p className="text-xs text-stone-600">
              请确认 FastAPI 已在 http://localhost:8000 启动，或检查 NEXT_PUBLIC_API_BASE_URL。
            </p>
            <button
              type="button"
              onClick={refetchAll}
              className="rounded-full bg-stone-800 px-6 py-3 font-medium text-stone-50 transition-colors duration-300 hover:bg-stone-700"
            >
              重试
            </button>
          </div>
        ) : (
          <div className={`grid grid-cols-1 gap-6 md:grid-cols-2 ${compactMode ? "md:gap-4" : "md:gap-8"}`}>
            <dl className="space-y-3">
              <Field label="状态" value={healthData?.status ?? ""} />
              <Field label="环境" value={healthData?.environment ?? ""} />
              <Field label="链路追踪" value={healthData?.tracing_enabled === true ? "已启用" : "未启用"} />
              <Field label="追踪降级" value={healthData?.tracing_degraded === true ? "已降级为本地日志" : "正常"} />
            </dl>
            <dl className="space-y-3">
              <Field label="服务名" value={versionData?.name ?? ""} />
              <Field label="版本" value={versionData?.version ?? ""} />
              <Field label="版本环境" value={versionData?.environment ?? ""} />
            </dl>
          </div>
        )}
      </div>
    </section>
  );
}
