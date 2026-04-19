import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Concatenate Tailwind classnames with conflict resolution.
 * Standard shadcn pattern.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Format an ISO timestamp as a compact "5s ago" / "3m ago" / "2h ago" string.
 * Falls back to an absolute short form after 24h.
 */
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return 'never';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return 'never';
  const diffMs = Date.now() - t;
  if (diffMs < 0) return 'just now';
  const sec = Math.round(diffMs / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return new Date(iso).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  });
}

/**
 * Richer latency formatter: sub-ms, ms, sub-s, s, or stale (if a fresh-by-timestamp
 * is older than 5 minutes).
 */
export function formatLatency(
  ms: number | null | undefined,
  freshAsOf?: string | null | undefined
): string {
  if (freshAsOf) {
    const ts = new Date(freshAsOf).getTime();
    if (!Number.isNaN(ts) && Date.now() - ts > 5 * 60_000) return '— stale';
  }
  if (ms === null || ms === undefined) return '—';
  if (ms < 1) return '<1ms';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 10_000) return `${(ms / 1000).toFixed(2)}s`;
  return `${Math.round(ms / 1000)}s`;
}

/**
 * Intl-backed absolute clock render (HH:MM:SS or short date).
 */
export function clockTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleTimeString(undefined, {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/**
 * Safe-access window.location.origin for dev/prod parity; never throws.
 */
export function apiOrigin(): string {
  if (typeof window === 'undefined') return '';
  return window.location.origin;
}

/**
 * Tiny RNG for client-side fake sparkline data.
 */
export function seedRandom(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 0xffffffff;
  };
}

/**
 * Clamp between [min, max].
 */
export function clamp(n: number, min: number, max: number): number {
  return Math.min(Math.max(n, min), max);
}

/**
 * Detect prefers-reduced-motion (safe on SSR). Re-reads on subscription.
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

/**
 * Detect macOS; used to render the correct modifier glyph (⌘ vs Ctrl).
 */
export function isMac(): boolean {
  if (typeof navigator === 'undefined') return false;
  const ua = navigator.userAgent || '';
  return /Mac|iPhone|iPad|iPod/.test(ua);
}

/**
 * Modifier key symbol helpers for kbd rendering.
 */
export function modKey(): string {
  return isMac() ? '⌘' : 'Ctrl';
}
