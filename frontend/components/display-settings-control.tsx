"use client";

import { useEffect, useState, type ChangeEvent } from "react";

import { DEFAULT_DISPLAY_SETTINGS, restoreDisplaySettings, serializeDisplaySettings, type DisplaySettings } from "@/lib/display-settings";

const STORAGE_KEY = "mealcompass.display.v1";

function applySettings(settings: DisplaySettings): void {
  const root = document.documentElement;
  root.dataset.font = settings.font;
  root.dataset.size = settings.size;
  root.dataset.layout = settings.layout;
  root.dataset.theme = settings.theme;
}

export function DisplaySettingsControl() {
  const [settings, setSettings] = useState(DEFAULT_DISPLAY_SETTINGS);
  const [restored, setRestored] = useState(false);

  useEffect(() => {
    try {
      setSettings(restoreDisplaySettings(localStorage.getItem(STORAGE_KEY)));
    } catch {
      setSettings(DEFAULT_DISPLAY_SETTINGS);
    }
    setRestored(true);
  }, []);

  useEffect(() => {
    if (!restored) {
      return;
    }
    applySettings(settings);
    try {
      localStorage.setItem(STORAGE_KEY, serializeDisplaySettings(settings));
    } catch {
      // Private browsing can reject writes; the current page still reflects the choice.
    }
  }, [restored, settings]);

  function update<K extends keyof DisplaySettings>(key: K, value: DisplaySettings[K]): void {
    setSettings((current) => ({ ...current, [key]: value }));
  }

  const selectClass = "mt-2 min-h-[44px] w-full rounded-full border border-stone-300 bg-white px-4 text-sm text-stone-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#5c4033]";

  return (
    <details className="relative shrink-0">
      <summary className="flex min-h-[44px] cursor-pointer list-none items-center rounded-full border border-stone-300 px-4 text-sm text-stone-800 transition-colors hover:bg-stone-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#5c4033]">
        外观设置
      </summary>
      <div className="theme-surface absolute right-0 top-full z-50 mt-3 w-[min(20rem,calc(100vw-2rem))] space-y-4 rounded-[2rem] border border-stone-300 p-5 shadow-md">
        <h2 className="font-serif text-lg text-stone-800">调整阅读方式</h2>
        <label className="block text-sm text-stone-700">
          字体风格
          <select aria-label="字体风格" className={selectClass} value={settings.font} onChange={(event: ChangeEvent<HTMLSelectElement>) => update("font", event.target.value as DisplaySettings["font"])}>
            <option value="sans">清晰黑体</option>
            <option value="serif">书卷宋体</option>
          </select>
        </label>
        <label className="block text-sm text-stone-700">
          字体大小
          <select aria-label="字体大小" className={selectClass} value={settings.size} onChange={(event: ChangeEvent<HTMLSelectElement>) => update("size", event.target.value as DisplaySettings["size"])}>
            <option value="normal">标准</option>
            <option value="large">较大</option>
            <option value="xlarge">最大</option>
          </select>
        </label>
        <label className="block text-sm text-stone-700">
          页面排列
          <select aria-label="页面排列" className={selectClass} value={settings.layout} onChange={(event: ChangeEvent<HTMLSelectElement>) => update("layout", event.target.value as DisplaySettings["layout"])}>
            <option value="grid">舒展双列</option>
            <option value="list">单列阅读</option>
          </select>
        </label>
        <label className="block text-sm text-stone-700">
          页面主题
          <select aria-label="页面主题" className={selectClass} value={settings.theme} onChange={(event: ChangeEvent<HTMLSelectElement>) => update("theme", event.target.value as DisplaySettings["theme"])}>
            <option value="cream">奶油米色</option>
            <option value="sage">鼠尾草绿</option>
            <option value="clay">陶土暖粉</option>
          </select>
        </label>
      </div>
    </details>
  );
}
