import { create } from "zustand";

/**
 * 只保存界面状态。
 * 服务端响应（HealthResponse / VersionResponse）由 TanStack Query 缓存，绝不放进这里。
 */
export type UiState = {
  compactMode: boolean;
  toggleCompactMode: () => void;
};

export const useUiStore = create<UiState>((set) => ({
  compactMode: false,
  toggleCompactMode: () => set((state) => ({ compactMode: !state.compactMode })),
}));
