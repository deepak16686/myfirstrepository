/**
 * Application chrome: sidebar + topbar + main content area.
 * Hosts the tool detail drawer, the status rail, the command palette,
 * and every global overlay — all of them need `useNavigate` from the
 * router tree, so they live here rather than in main.tsx.
 */
import { useMemo } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';
import { ToolDetailDrawer } from '@/components/tools/ToolDetailDrawer';
import { CommandPalette } from '@/components/common/CommandPalette';
import { GlobalShortcuts } from '@/components/common/GlobalShortcuts';
import { StatusAnnouncer } from '@/components/common/StatusAnnouncer';
import { StatusRail } from '@/components/common/StatusRail';
import { useTools, useCategories } from '@/hooks/useTools';
import { useHealth } from '@/hooks/useHealth';
import type { Tool } from '@/types/tool';

export function AppShell(): React.ReactElement {
  const location = useLocation();
  const toolsQuery = useTools();
  const cats = useCategories();
  const { data: healthMap } = useHealth();

  // Merge live health into tools (server-side may already do this; this is defensive).
  const enrichedTools = useMemo<Tool[] | undefined>(() => {
    if (!toolsQuery.data) return undefined;
    if (!healthMap || Object.keys(healthMap).length === 0) return toolsQuery.data;
    return toolsQuery.data.map((t) => {
      const live = healthMap[t.id];
      if (!live) return t;
      return {
        ...t,
        health_status: live.status,
        latency_ms: live.latency_ms ?? t.latency_ms ?? null,
        last_checked: live.last_checked ?? t.last_checked ?? null,
      };
    });
  }, [toolsQuery.data, healthMap]);

  return (
    <div className="relative flex min-h-dvh bg-background text-foreground">
      {/* Skip link — invisible until tab-focused, then jumps to main content. */}
      <a href="#main-content" className="skip-link" tabIndex={0}>
        Skip to main content
      </a>

      {/* Atmospheric layered background — dot grid + drifting mesh. */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-0 -z-10 grid-dots opacity-[0.35] dark:opacity-[0.22]"
      />
      <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 mesh-bg" />

      {/* Global router-scoped overlays (all need router context). */}
      <GlobalShortcuts />
      <StatusAnnouncer tools={enrichedTools} />
      <CommandPalette />

      <Sidebar tools={enrichedTools} categories={cats.data} loading={toolsQuery.isLoading} />

      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />

        {/* Narrow row above the main scroll area for the compact StatusRail. */}
        <div className="px-4 pt-3 sm:px-8">
          <StatusRail tools={enrichedTools} />
        </div>

        <main
          id="main-content"
          tabIndex={-1}
          className="relative min-w-0 flex-1 overflow-x-hidden px-4 py-6 outline-none sm:px-8 sm:py-8"
        >
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
              className="mx-auto w-full max-w-[1400px]"
            >
              <Outlet
                context={{
                  tools: enrichedTools,
                  categories: cats.data,
                  loading: toolsQuery.isLoading,
                }}
              />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      <ToolDetailDrawer />
    </div>
  );
}
