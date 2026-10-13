export type DisplaySettings = {
  font: "serif" | "sans";
  size: "normal" | "large" | "xlarge";
  layout: "grid" | "list";
  theme: "cream" | "sage" | "clay";
};

export const DEFAULT_DISPLAY_SETTINGS: DisplaySettings = {
  font: "sans",
  size: "normal",
  layout: "grid",
  theme: "cream",
};

export function restoreDisplaySettings(raw: string | null): DisplaySettings {
  if (raw === null) {
    return DEFAULT_DISPLAY_SETTINGS;
  }
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null || Array.isArray(value)) {
      return DEFAULT_DISPLAY_SETTINGS;
    }
    const saved = value as Record<string, unknown>;
    return {
      font: saved.font === "serif" || saved.font === "sans" ? saved.font : DEFAULT_DISPLAY_SETTINGS.font,
      size: saved.size === "normal" || saved.size === "large" || saved.size === "xlarge"
        ? saved.size : DEFAULT_DISPLAY_SETTINGS.size,
      layout: saved.layout === "grid" || saved.layout === "list" ? saved.layout : DEFAULT_DISPLAY_SETTINGS.layout,
      theme: saved.theme === "cream" || saved.theme === "sage" || saved.theme === "clay"
        ? saved.theme : DEFAULT_DISPLAY_SETTINGS.theme,
    };
  } catch {
    return DEFAULT_DISPLAY_SETTINGS;
  }
}

export function serializeDisplaySettings(settings: DisplaySettings): string {
  return JSON.stringify(settings);
}
