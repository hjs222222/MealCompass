export default function Loading() {
  return (
    <div aria-busy="true" aria-live="polite" className="space-y-6">
      <div className="h-9 w-56 rounded-full bg-stone-200" />
      <div className="h-4 w-full max-w-xl rounded-full bg-stone-200" />
      <div className="rounded-[2rem] border border-stone-200 theme-surface p-6 md:p-8">
        <div className="space-y-3">
          <div className="h-5 w-40 rounded-full bg-stone-200" />
          <div className="h-4 w-64 rounded-full bg-stone-200" />
          <div className="h-4 w-52 rounded-full bg-stone-200" />
        </div>
      </div>
      <p className="text-sm text-stone-600">页面加载中…</p>
    </div>
  );
}
