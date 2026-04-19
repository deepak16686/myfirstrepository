/**
 * Theme hook — system / dark / light / cyberpunk, persisted to localStorage.
 * Syncs with the pre-paint script in index.html so no FOUC occurs.
 */
import { useCallback, useEffect, useState } from 'react';

export type Theme = 'dark' | 'light' | 'system' | 'cyberpunk';
export type ResolvedTheme = 'dark' | 'light';

const STORAGE_KEY = 'portal-theme';

function resolveSystem(): ResolvedTheme {
  if (typeof window === 'undefined') return 'dark';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function readStored(): Theme {
  if (typeof window === 'undefined') return 'dark';
  const v = localStorage.getItem(STORAGE_KEY);
  if (v === 'dark' || v === 'light' || v === 'system' || v === 'cyberpunk') return v;
  return 'system';
}

function applyClass(theme: Theme, resolved: ResolvedTheme): void {
  const html = document.documentElement;
  html.classList.remove('dark', 'light', 'theme-cyberpunk');
  if (theme === 'cyberpunk') {
    html.classList.add('dark', 'theme-cyberpunk');
    html.style.colorScheme = 'dark';
  } else {
    html.classList.add(resolved);
    html.style.colorScheme = resolved;
  }
}

export function useTheme(): {
  theme: Theme;
  resolved: ResolvedTheme;
  isCyberpunk: boolean;
  setTheme: (t: Theme) => void;
  toggle: () => void;
} {
  const [theme, setThemeState] = useState<Theme>(() => readStored());
  const [resolved, setResolved] = useState<ResolvedTheme>(() => {
    const stored = readStored();
    if (stored === 'cyberpunk') return 'dark';
    if (stored === 'system') return resolveSystem();
    return stored;
  });

  // Apply on theme change and on system preference change.
  useEffect(() => {
    const effective: ResolvedTheme =
      theme === 'cyberpunk' ? 'dark' : theme === 'system' ? resolveSystem() : theme;
    applyClass(theme, effective);
    setResolved(effective);

    if (theme === 'system') {
      const mq = window.matchMedia('(prefers-color-scheme: dark)');
      const onChange = (): void => {
        const e: ResolvedTheme = mq.matches ? 'dark' : 'light';
        applyClass('system', e);
        setResolved(e);
      };
      mq.addEventListener('change', onChange);
      return () => mq.removeEventListener('change', onChange);
    }
    return undefined;
  }, [theme]);

  const setTheme = useCallback((t: Theme) => {
    localStorage.setItem(STORAGE_KEY, t);
    setThemeState(t);
  }, []);

  const toggle = useCallback(() => {
    setTheme(resolved === 'dark' ? 'light' : 'dark');
  }, [resolved, setTheme]);

  return { theme, resolved, isCyberpunk: theme === 'cyberpunk', setTheme, toggle };
}
