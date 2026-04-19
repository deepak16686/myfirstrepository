/**
 * Lightweight UI store — sidebar collapsed, detail drawer selection, palette open,
 * status rail visibility, tools view mode, saved view. Persisted partialize-keys
 * live in localStorage.
 *
 * NOTE on `operatorToken`:
 *   The operator token is persisted to its own localStorage key
 *   (`portal.operator-token`) so the main `portal-ui` blob stays free of
 *   secrets. The token is only read when the user clicks "Reveal" in the
 *   CredentialsPanel; it is never logged, toasted, or sent anywhere other
 *   than the `X-Portal-Operator` header on the credentials endpoint.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ToolsViewMode = 'grid' | 'table' | 'compact';
export type SavedViewKey = 'all' | 'ai' | 'cicd' | 'down';

const OPERATOR_TOKEN_KEY = 'portal.operator-token';

/** Safely read the persisted operator token at module init. */
function readPersistedOperatorToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(OPERATOR_TOKEN_KEY);
    return raw && raw.length > 0 ? raw : null;
  } catch {
    return null;
  }
}

/** Safely write (or clear) the persisted operator token. */
function writePersistedOperatorToken(token: string | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (token && token.length > 0) {
      window.localStorage.setItem(OPERATOR_TOKEN_KEY, token);
    } else {
      window.localStorage.removeItem(OPERATOR_TOKEN_KEY);
    }
  } catch {
    /* storage quota or SSR — best-effort only */
  }
}

interface UiState {
  sidebarCollapsed: boolean;
  toggleSidebar: () => void;
  setSidebar: (collapsed: boolean) => void;

  selectedToolId: string | null;
  openDetail: (id: string) => void;
  closeDetail: () => void;

  searchOpen: boolean;
  setSearchOpen: (v: boolean) => void;

  paletteOpen: boolean;
  openPalette: () => void;
  closePalette: () => void;
  togglePalette: () => void;

  statusRailVisible: boolean;
  toggleStatusRail: () => void;
  setStatusRail: (v: boolean) => void;

  shortcutsOpen: boolean;
  openShortcuts: () => void;
  closeShortcuts: () => void;

  toolsView: ToolsViewMode;
  setToolsView: (v: ToolsViewMode) => void;

  savedView: SavedViewKey;
  setSavedView: (v: SavedViewKey) => void;

  /** Operator token used by the credentials reveal flow. Persisted in a
   *  separate localStorage key (`portal.operator-token`); `null` until the
   *  user unlocks for the first time. */
  operatorToken: string | null;
  setOperatorToken: (token: string | null) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setSidebar: (collapsed) => set({ sidebarCollapsed: collapsed }),

      selectedToolId: null,
      openDetail: (id) => set({ selectedToolId: id }),
      closeDetail: () => set({ selectedToolId: null }),

      searchOpen: false,
      setSearchOpen: (v) => set({ searchOpen: v }),

      paletteOpen: false,
      openPalette: () => set({ paletteOpen: true }),
      closePalette: () => set({ paletteOpen: false }),
      togglePalette: () => set((s) => ({ paletteOpen: !s.paletteOpen })),

      statusRailVisible: true,
      toggleStatusRail: () => set((s) => ({ statusRailVisible: !s.statusRailVisible })),
      setStatusRail: (v) => set({ statusRailVisible: v }),

      shortcutsOpen: false,
      openShortcuts: () => set({ shortcutsOpen: true }),
      closeShortcuts: () => set({ shortcutsOpen: false }),

      toolsView: 'grid',
      setToolsView: (v) => set({ toolsView: v }),

      savedView: 'all',
      setSavedView: (v) => set({ savedView: v }),

      operatorToken: readPersistedOperatorToken(),
      setOperatorToken: (token) => {
        writePersistedOperatorToken(token);
        set({ operatorToken: token });
      },
    }),
    {
      name: 'portal-ui',
      // `operatorToken` is intentionally EXCLUDED from the `portal-ui` blob —
      // it lives in its own dedicated storage key so secrets are not mingled
      // with benign UI preferences.
      partialize: (s) => ({
        sidebarCollapsed: s.sidebarCollapsed,
        statusRailVisible: s.statusRailVisible,
        toolsView: s.toolsView,
        savedView: s.savedView,
      }),
    }
  )
);
