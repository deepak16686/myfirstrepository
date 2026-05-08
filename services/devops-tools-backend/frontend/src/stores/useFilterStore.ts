/**
 * Filter store — category multi-select + health multi-select + text query +
 * "only failing" toggle. Intentionally kept separate from the existing
 * `useUiStore` so the two slices can be mounted independently and so the
 * persisted portal-ui blob doesn't churn on every keystroke.
 *
 * This is an in-memory store (no `persist`) because the filters are part
 * of the "look at stuff" state, not the "I've configured the app"
 * preferences. Users expect a reload to return to "all tools visible".
 */
import { create } from 'zustand';
import type { CategoryId, HealthStatus } from '@/types/tool';

interface FilterState {
  query: string;
  selectedCategories: Set<CategoryId>;
  selectedHealth: Set<HealthStatus>;
  onlyFailing: boolean;

  setQuery: (q: string) => void;
  toggleCategory: (id: CategoryId) => void;
  setCategories: (ids: CategoryId[]) => void;
  toggleHealth: (s: HealthStatus) => void;
  setOnlyFailing: (v: boolean) => void;
  clearAll: () => void;

  /** Total number of active filter constraints (used for "Clear all (N)"). */
  activeCount: () => number;
}

export const useFilterStore = create<FilterState>()((set, get) => ({
  query: '',
  selectedCategories: new Set(),
  selectedHealth: new Set(),
  onlyFailing: false,

  setQuery: (q) => set({ query: q }),

  toggleCategory: (id) =>
    set((s) => {
      const next = new Set(s.selectedCategories);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return { selectedCategories: next };
    }),

  setCategories: (ids) => set({ selectedCategories: new Set(ids) }),

  toggleHealth: (status) =>
    set((s) => {
      const next = new Set(s.selectedHealth);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      return { selectedHealth: next };
    }),

  setOnlyFailing: (v) => set({ onlyFailing: v }),

  clearAll: () =>
    set({
      query: '',
      selectedCategories: new Set(),
      selectedHealth: new Set(),
      onlyFailing: false,
    }),

  activeCount: () => {
    const s = get();
    return (
      (s.query.length > 0 ? 1 : 0) +
      s.selectedCategories.size +
      s.selectedHealth.size +
      (s.onlyFailing ? 1 : 0)
    );
  },
}));
