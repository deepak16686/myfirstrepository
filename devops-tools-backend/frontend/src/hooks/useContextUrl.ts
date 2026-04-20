/**
 * useContextUrl — reads window.location.hostname once on mount and picks the
 * correct launch URL per tool, reusing the pure helpers in `lib/urls.ts`.
 *
 * The hostname is not reactive (users don't navigate between origins while
 * keeping the SPA mounted), so we resolve it once with useSyncExternalStore
 * semantics via useState + useEffect for SSR safety.
 */
import { useEffect, useMemo, useState } from 'react';
import type { Tool } from '@/types/tool';
import {
  classifyHostname,
  listAvailableUrls,
  resolveLaunchUrl,
  type LaunchContext,
  type NamedUrl,
} from '@/lib/urls';

export function useContextUrl(): {
  context: LaunchContext;
  hostname: string;
  pickUrl: (t: Tool) => string | null;
  pickUrls: (t: Tool) => NamedUrl[];
} {
  const [hostname, setHostname] = useState<string>(() =>
    typeof window === 'undefined' ? '' : window.location.hostname,
  );

  useEffect(() => {
    if (typeof window === 'undefined') return;
    // Hostname doesn't change without a full navigation, but just in case a
    // user back/forwards between dev & prod within the same SPA (rare), we
    // re-read on popstate.
    const onPop = (): void => setHostname(window.location.hostname);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const context = useMemo<LaunchContext>(() => classifyHostname(hostname), [hostname]);

  return {
    context,
    hostname,
    pickUrl: (t: Tool): string | null => resolveLaunchUrl(t, context),
    pickUrls: (t: Tool): NamedUrl[] => listAvailableUrls(t, context),
  };
}
