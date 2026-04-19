/* Global keyboard shortcuts: ⌘K palette, / search, ? shortcuts, g-<x> nav, t theme, esc. */
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { useUiStore } from '@/store/ui';
import { useTheme } from '@/hooks/useTheme';

function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (el.isContentEditable) return true;
  // cmdk lists
  if (el.closest('[cmdk-root]')) return true;
  return false;
}

export function GlobalShortcuts(): null {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const closeDetail = useUiStore((s) => s.closeDetail);
  const togglePalette = useUiStore((s) => s.togglePalette);
  const closePalette = useUiStore((s) => s.closePalette);
  const paletteOpen = useUiStore((s) => s.paletteOpen);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const openShortcuts = useUiStore((s) => s.openShortcuts);
  const closeShortcuts = useUiStore((s) => s.closeShortcuts);
  const shortcutsOpen = useUiStore((s) => s.shortcutsOpen);
  const { resolved, setTheme } = useTheme();

  useEffect(() => {
    let gBuffer = '';
    let gTimer: number | undefined;

    const onKey = (e: KeyboardEvent): void => {
      // Esc always closes things.
      if (e.key === 'Escape') {
        if (paletteOpen) {
          closePalette();
          return;
        }
        if (shortcutsOpen) {
          closeShortcuts();
          return;
        }
        closeDetail();
        return;
      }

      const typing = isTypingTarget(e.target);

      // ⌘K / Ctrl+K is captured even when typing (it's the universal override).
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        togglePalette();
        return;
      }

      if (typing) return;

      // ? shows the shortcuts overlay.
      if (e.key === '?' || (e.shiftKey && e.key === '/')) {
        e.preventDefault();
        openShortcuts();
        return;
      }

      // Refresh all health + tools.
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'r' && e.shiftKey) {
        e.preventDefault();
        void qc.invalidateQueries();
        return;
      }

      // t — toggle theme dark/light.
      if (e.key === 't' || e.key === 'T') {
        if (!e.metaKey && !e.ctrlKey && !e.altKey) {
          setTheme(resolved === 'dark' ? 'light' : 'dark');
          return;
        }
      }

      // g d / g t / g p / g c — navigate.
      if (e.key === 'g' || e.key === 'G') {
        gBuffer = 'g';
        if (gTimer) window.clearTimeout(gTimer);
        gTimer = window.setTimeout(() => (gBuffer = ''), 900);
        return;
      }
      if (gBuffer === 'g') {
        const k = e.key.toLowerCase();
        if (k === 'd' || k === 'o') {
          e.preventDefault();
          navigate('/');
        } else if (k === 't') {
          e.preventDefault();
          navigate('/tools');
        } else if (k === 'p') {
          e.preventDefault();
          navigate('/pipelines');
        } else if (k === 'c') {
          e.preventDefault();
          navigate('/chat');
        }
        gBuffer = '';
        return;
      }

      // \ — collapse sidebar.
      if (e.key === '\\' && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        toggleSidebar();
      }
    };

    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [
    closeDetail,
    togglePalette,
    closePalette,
    paletteOpen,
    toggleSidebar,
    openShortcuts,
    closeShortcuts,
    shortcutsOpen,
    navigate,
    qc,
    setTheme,
    resolved,
  ]);

  return null;
}
