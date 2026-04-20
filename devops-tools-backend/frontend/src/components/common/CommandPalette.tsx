/* Command palette — cmd/ctrl+K. Tools, actions, and navigation in one fuzzy finder. */
import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { createPortal } from 'react-dom';
import { Command } from 'cmdk';
import { useNavigate } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import Fuse from 'fuse.js';
import {
  Activity,
  ArrowUpRight,
  BarChart3,
  Boxes,
  Copy,
  GitBranch,
  GitPullRequestArrow,
  Info,
  LineChart,
  MessageSquare,
  Moon,
  PanelLeftClose,
  Paintbrush,
  Power,
  RefreshCw,
  Search,
  Signal,
  Sun,
  type LucideIcon,
} from 'lucide-react';
import { useTools } from '@/hooks/useTools';
import { useUiStore } from '@/store/ui';
import { useTheme } from '@/hooks/useTheme';
import { launchTool } from '@/lib/api';
import { resolveIcon } from '@/lib/icons';
import { statusMeta } from '@/lib/status';
import { cn, modKey } from '@/lib/utils';
import type { Tool } from '@/types/tool';
import { HealthDot } from '@/components/tools/HealthDot';

interface PaletteAction {
  id: string;
  label: string;
  subtitle?: string;
  icon: LucideIcon;
  keywords?: string[];
  onSelect: () => void | Promise<void>;
}

type RunMode = 'launch' | 'embed' | 'detail';

function isBrowser(): boolean {
  return typeof window !== 'undefined';
}

export function CommandPalette(): React.ReactElement | null {
  const open = useUiStore((s) => s.paletteOpen);
  const closePalette = useUiStore((s) => s.closePalette);
  const openDetail = useUiStore((s) => s.openDetail);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const toggleStatusRail = useUiStore((s) => s.toggleStatusRail);
  const openShortcuts = useUiStore((s) => s.openShortcuts);
  const { theme, setTheme } = useTheme();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: tools } = useTools();
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Track the latest keyboard event so onSelect can read modifiers reliably.
  const lastKeyRef = useRef<{ meta: boolean; alt: boolean; shift: boolean }>({
    meta: false,
    alt: false,
    shift: false,
  });

  const [query, setQuery] = useState('');

  // Reset query on close.
  useEffect(() => {
    if (!open) setQuery('');
  }, [open]);

  // Focus trap: let cmdk own keyboard but auto-focus input on open.
  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => searchRef.current?.focus());
    }
  }, [open]);

  // Build fuse index for fast fuzzy search over tools.
  const fuse = useMemo(() => {
    const list = tools ?? [];
    return new Fuse(list, {
      keys: [
        { name: 'name', weight: 0.5 },
        { name: 'id', weight: 0.25 },
        { name: 'description', weight: 0.15 },
        { name: 'tags', weight: 0.1 },
      ],
      threshold: 0.38,
      ignoreLocation: true,
    });
  }, [tools]);

  // Actions — always present regardless of search.
  const actions: PaletteAction[] = useMemo(
    () => [
      {
        id: 'theme-dark',
        label: 'Switch to dark theme',
        icon: Moon,
        keywords: ['theme', 'dark', 'mode'],
        onSelect: () => setTheme('dark'),
      },
      {
        id: 'theme-light',
        label: 'Switch to light theme',
        icon: Sun,
        keywords: ['theme', 'light', 'mode'],
        onSelect: () => setTheme('light'),
      },
      {
        id: 'theme-cyberpunk',
        label: 'Switch to cyberpunk theme',
        icon: Paintbrush,
        keywords: ['theme', 'neon', 'pink', 'cyan'],
        onSelect: () => setTheme('cyberpunk'),
      },
      {
        id: 'refresh-all',
        label: 'Refresh all health probes',
        icon: RefreshCw,
        keywords: ['invalidate', 'refetch'],
        onSelect: () => {
          void qc.invalidateQueries();
          toast.info('Refetching portal queries');
        },
      },
      {
        id: 'toggle-sidebar',
        label: 'Collapse / expand sidebar',
        icon: PanelLeftClose,
        keywords: ['sidebar', 'collapse', 'layout'],
        onSelect: () => toggleSidebar(),
      },
      {
        id: 'toggle-status-rail',
        label: 'Toggle status rail',
        icon: Signal,
        keywords: ['status', 'rail', 'dots', 'indicator'],
        onSelect: () => toggleStatusRail(),
      },
      {
        id: 'shortcuts',
        label: 'Show keyboard shortcuts',
        icon: Info,
        keywords: ['help', 'keys', 'hotkeys'],
        onSelect: () => openShortcuts(),
      },
      {
        id: 'copy-portal-url',
        label: 'Copy portal URL',
        icon: Copy,
        keywords: ['share', 'link'],
        onSelect: () => {
          if (!isBrowser()) return;
          navigator.clipboard.writeText(window.location.href).then(
            () => toast.success('Portal URL copied'),
            () => toast.error('Clipboard blocked')
          );
        },
      },
      {
        id: 'open-gitlab',
        label: 'Open GitLab in a new tab',
        icon: GitBranch,
        keywords: ['scm', 'git'],
        onSelect: () => {
          const gl = (tools ?? []).find((t) => t.id === 'gitlab');
          window.open(gl?.url_external ?? 'http://localhost:8082', '_blank', 'noopener,noreferrer');
        },
      },
      {
        id: 'open-grafana',
        label: 'Open Grafana in a new tab',
        icon: LineChart,
        keywords: ['observability', 'metrics'],
        onSelect: () => {
          const g = (tools ?? []).find((t) => t.id === 'grafana');
          window.open(g?.url_external ?? 'http://localhost:3000', '_blank', 'noopener,noreferrer');
        },
      },
      {
        id: 'open-splunk',
        label: 'Open Splunk in a new tab',
        icon: Activity,
        keywords: ['logs', 'siem'],
        onSelect: () => {
          const s = (tools ?? []).find((t) => t.id === 'splunk');
          window.open(s?.url_external ?? 'http://localhost:8000', '_blank', 'noopener,noreferrer');
        },
      },
      {
        id: 'tailscale-info',
        label: 'Show Tailscale status info',
        icon: Power,
        keywords: ['tailnet', 'funnel'],
        onSelect: () => toast.info('Tailscale status is shown in the top-right chip.'),
      },
    ],
    [setTheme, qc, toggleSidebar, toggleStatusRail, openShortcuts, tools]
  );

  const navItems: { id: string; label: string; icon: LucideIcon; to: string; hint: string }[] = [
    { id: 'go-portal', label: 'Portal (dense grid)', icon: Boxes, to: '/', hint: 'g h' },
    { id: 'go-analytics', label: 'Analytics', icon: BarChart3, to: '/analytics', hint: 'g a' },
    { id: 'go-tools', label: 'Tools (grid/table/compact)', icon: Activity, to: '/tools', hint: 'g t' },
    { id: 'go-pipelines', label: 'Pipelines', icon: GitPullRequestArrow, to: '/pipelines', hint: 'g p' },
    { id: 'go-chat', label: 'AI Chat', icon: MessageSquare, to: '/chat', hint: 'g c' },
  ];

  const toolResults = useMemo<Tool[]>(() => {
    if (!tools) return [];
    const q = query.trim();
    if (!q) return tools.slice(0, 200);
    return fuse.search(q).map((r) => r.item);
  }, [tools, query, fuse]);

  const invokeAndClose = (fn: () => void | Promise<void>): void => {
    try {
      const maybe = fn();
      if (maybe && typeof (maybe as Promise<unknown>).then === 'function') {
        void (maybe as Promise<unknown>).finally(() => closePalette());
      } else {
        closePalette();
      }
    } catch {
      closePalette();
    }
  };

  const runTool = async (tool: Tool, mode: RunMode): Promise<void> => {
    if (mode === 'detail') {
      openDetail(tool.id);
      return;
    }
    if (mode === 'embed') {
      if (!tool.embed) {
        toast.error(`${tool.name} cannot be embedded`);
        return;
      }
      navigate(`/embed/${tool.id}`);
      return;
    }
    // launch
    if (!tool.url_external) {
      toast.error('No external URL configured');
      return;
    }
    try {
      const r = await launchTool(tool.id);
      window.open(r.redirect_url || tool.url_external, '_blank', 'noopener,noreferrer');
    } catch {
      window.open(tool.url_external, '_blank', 'noopener,noreferrer');
    }
  };

  // Capture modifier state just before cmdk fires onSelect (it fires on keydown/click).
  const onListKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>): void => {
    lastKeyRef.current = { meta: e.metaKey || e.ctrlKey, alt: e.altKey, shift: e.shiftKey };
  };
  const onListMouseDown = (e: React.MouseEvent<HTMLDivElement>): void => {
    lastKeyRef.current = { meta: e.metaKey || e.ctrlKey, alt: e.altKey, shift: e.shiftKey };
  };

  if (!isBrowser()) return null;
  if (!open) return null;

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      className="fixed inset-0 z-[70] flex items-start justify-center px-4 pt-[8vh] sm:pt-[12vh]"
    >
      {/* Backdrop */}
      <button
        type="button"
        aria-label="Close command palette"
        onClick={closePalette}
        className="absolute inset-0 bg-background/70 backdrop-blur-sm animate-in fade-in-0 duration-200"
      />

      {/* Shell */}
      <div
        className={cn(
          'relative w-full max-w-[640px] overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-[0_24px_70px_-20px_rgba(0,0,0,0.55),0_0_0_1px_color-mix(in_oklch,var(--accent-signal)_18%,transparent)]',
          'animate-in fade-in-0 zoom-in-95 slide-in-from-top-4 duration-200'
        )}
      >
        {/* Top signal hairline */}
        <div
          aria-hidden
          className="absolute inset-x-0 top-0 h-px"
          style={{
            background:
              'linear-gradient(90deg, transparent, color-mix(in oklch, var(--accent-signal) 70%, transparent), color-mix(in oklch, var(--accent-signal-alt) 60%, transparent), transparent)',
          }}
        />

        <Command
          label="DevOps Portal command palette"
          loop
          shouldFilter={false}
          onKeyDown={onListKeyDown}
        >
          <div className="flex items-center gap-3 border-b border-border px-4">
            <Search className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
            <Command.Input
              ref={searchRef}
              value={query}
              onValueChange={setQuery}
              placeholder="Search tools, run actions, jump to a page…"
              autoFocus
            />
            <kbd className="hidden items-center gap-1 rounded border border-border bg-muted/60 px-1.5 py-0.5 font-mono text-[10px] uppercase text-muted-foreground sm:inline-flex">
              esc
            </kbd>
          </div>

          <Command.List ref={listRef} onMouseDown={onListMouseDown}>
            <Command.Empty>
              <div className="flex flex-col items-center gap-1">
                <Search className="h-6 w-6 text-muted-foreground/70" />
                <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                  no results · refine your query
                </p>
              </div>
            </Command.Empty>

            {query.trim().length === 0 ? (
              <Command.Group heading="Navigation">
                {navItems.map((n) => {
                  const I = n.icon;
                  return (
                    <Command.Item
                      key={n.id}
                      value={`nav ${n.label} ${n.to}`}
                      onSelect={() => invokeAndClose(() => navigate(n.to))}
                    >
                      <I className="h-4 w-4 text-muted-foreground" />
                      <span className="flex-1 truncate">{n.label}</span>
                      <kbd className="rounded border border-border bg-muted/50 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                        {n.hint}
                      </kbd>
                    </Command.Item>
                  );
                })}
              </Command.Group>
            ) : null}

            <Command.Group heading={`Tools · ${toolResults.length}`}>
              {toolResults.map((t) => {
                const I = resolveIcon(t.icon);
                const sm = statusMeta(t.health_status);
                return (
                  <Command.Item
                    key={t.id}
                    value={`tool ${t.name} ${t.id} ${t.category} ${t.tags.join(' ')}`}
                    onSelect={() => {
                      const { meta, alt } = lastKeyRef.current;
                      const mode: RunMode = meta ? 'embed' : alt ? 'detail' : 'launch';
                      void runTool(t, mode);
                      closePalette();
                    }}
                  >
                    <span className="flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-muted/50">
                      <I className="h-3.5 w-3.5" />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-medium leading-snug">{t.name}</p>
                      <p className="mt-0.5 truncate font-mono text-[10.5px] uppercase tracking-wider text-muted-foreground">
                        {t.category} · {t.id}
                      </p>
                    </div>
                    <HealthDot status={t.health_status ?? 'unknown'} size="xs" pulse={false} />
                    <span className={cn('mono-caps', sm.text)}>{sm.shortLabel}</span>
                    <kbd className="rounded border border-border bg-muted/40 px-1 py-[1px] font-mono text-[10px] text-muted-foreground">
                      {'\u21B5'}
                    </kbd>
                  </Command.Item>
                );
              })}
            </Command.Group>

            <Command.Group heading="Actions">
              {actions.map((a) => {
                const I = a.icon;
                return (
                  <Command.Item
                    key={a.id}
                    value={`action ${a.label} ${(a.keywords ?? []).join(' ')}`}
                    onSelect={() => invokeAndClose(() => a.onSelect())}
                  >
                    <I className="h-4 w-4 text-muted-foreground" />
                    <span className="flex-1 truncate">{a.label}</span>
                    <ArrowUpRight className="h-3 w-3 text-muted-foreground/60" />
                  </Command.Item>
                );
              })}
            </Command.Group>
          </Command.List>

          {/* Footer */}
          <div className="flex flex-wrap items-center gap-3 border-t border-border bg-muted/30 px-4 py-2 text-[11px] text-muted-foreground">
            <Hint kbd="Enter" label="Launch" />
            <Hint kbd={`${modKey()}Enter`} label="Embed" />
            <Hint kbd="Alt+Enter" label="Details" />
            <span className="mx-auto" />
            <span className="font-mono">
              theme: <span className="text-foreground/80">{theme}</span>
            </span>
          </div>
        </Command>
      </div>
    </div>,
    document.body
  );
}

function Hint({ kbd, label }: { kbd: string; label: string }): React.ReactElement {
  return (
    <span className="inline-flex items-center gap-1.5">
      <kbd className="rounded border border-border bg-card px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider">
        {kbd}
      </kbd>
      <span>{label}</span>
    </span>
  );
}
