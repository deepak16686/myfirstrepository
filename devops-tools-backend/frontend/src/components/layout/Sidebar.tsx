import { memo, useMemo } from 'react';
import { NavLink, useLocation, useSearchParams } from 'react-router-dom';
import {
  BarChart3,
  Boxes,
  MessageSquare,
  GitPullRequestArrow,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useUiStore } from '@/store/ui';
import type { Category, Tool } from '@/types/tool';
import { categoryIcons } from '@/lib/icons';
import { Separator } from '@/components/ui/separator';
import { Button } from '@/components/ui/button';
import type { HealthStatus } from '@/types/tool';

interface SidebarProps {
  tools: Tool[] | undefined;
  categories: Category[] | undefined;
  loading?: boolean;
}

const MAIN_NAV = [
  { to: '/', label: 'Overview', icon: BarChart3 },
  { to: '/tools', label: 'Tools', icon: Boxes },
  { to: '/pipelines', label: 'Pipelines', icon: GitPullRequestArrow },
  { to: '/chat', label: 'AI Chat', icon: MessageSquare },
] as const;

const HEALTH_FILTERS: { key: HealthStatus; label: string; dot: string }[] = [
  { key: 'healthy', label: 'Healthy', dot: 'bg-[var(--success)]' },
  { key: 'degraded', label: 'Degraded', dot: 'bg-[var(--warning)]' },
  { key: 'down', label: 'Down', dot: 'bg-[var(--destructive)]' },
  { key: 'unknown', label: 'Unknown', dot: 'bg-muted-foreground/60' },
];

function _Sidebar({ tools, categories }: SidebarProps): React.ReactElement {
  const collapsed = useUiStore((s) => s.sidebarCollapsed);
  const toggle = useUiStore((s) => s.toggleSidebar);
  const location = useLocation();
  const [params, setParams] = useSearchParams();

  const toolsOnly = location.pathname === '/tools';

  const countsByCategory = useMemo(() => {
    const m = new Map<string, number>();
    (tools ?? []).forEach((t) => m.set(t.category, (m.get(t.category) ?? 0) + 1));
    return m;
  }, [tools]);

  const activeCats = useMemo(
    () => new Set((params.getAll('category') ?? []).flatMap((v) => v.split(','))),
    [params]
  );
  const activeHealths = useMemo(
    () => new Set((params.getAll('health') ?? []).flatMap((v) => v.split(','))),
    [params]
  );

  const toggleCategory = (id: string): void => {
    const next = new URLSearchParams(params);
    next.delete('category');
    const current = new Set(activeCats);
    if (current.has(id)) current.delete(id);
    else current.add(id);
    current.forEach((c) => next.append('category', c));
    setParams(next, { replace: true });
  };

  const toggleHealth = (id: HealthStatus): void => {
    const next = new URLSearchParams(params);
    next.delete('health');
    const current = new Set(activeHealths);
    if (current.has(id)) current.delete(id);
    else current.add(id);
    current.forEach((c) => next.append('health', c));
    setParams(next, { replace: true });
  };

  return (
    <aside
      className={cn(
        'relative flex h-dvh shrink-0 flex-col border-r border-border bg-sidebar text-sidebar-foreground',
        'transition-[width] duration-200 ease-out',
        collapsed ? 'w-[68px]' : 'w-[256px]'
      )}
      aria-label="Primary sidebar"
    >
      {/* Brand */}
      <div
        className={cn(
          'flex h-14 items-center gap-2.5 border-b border-border px-4',
          collapsed && 'justify-center px-0'
        )}
      >
        <div className="relative flex size-8 items-center justify-center rounded-md bg-gradient-to-br from-[color-mix(in_oklch,var(--primary)_75%,transparent)] to-[color-mix(in_oklch,var(--chart-4)_80%,transparent)]">
          <Boxes className="h-4 w-4 text-primary-foreground" />
          <span className="absolute -right-0.5 -top-0.5 size-1.5 rounded-full bg-[var(--success)] shadow-[0_0_6px_var(--success)]" />
        </div>
        {!collapsed ? (
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-semibold leading-none">DevOps Portal</p>
            <p className="mt-1 truncate font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
              control plane
            </p>
          </div>
        ) : null}
      </div>

      {/* Nav + filters */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden px-2 py-3">
        <ul className="space-y-0.5">
          {MAIN_NAV.map((n) => {
            const I = n.icon;
            return (
              <li key={n.to}>
                <NavLink
                  to={n.to}
                  end={n.to === '/'}
                  className={({ isActive }) =>
                    cn(
                      'group/nav flex h-9 items-center gap-3 rounded-md px-2 text-sm font-medium transition-colors',
                      'hover:bg-sidebar-accent hover:text-sidebar-accent-foreground',
                      isActive
                        ? 'bg-sidebar-accent text-sidebar-accent-foreground shadow-[inset_0_0_0_1px_color-mix(in_oklch,var(--ring)_25%,transparent)]'
                        : 'text-muted-foreground'
                    )
                  }
                  title={n.label}
                >
                  <I className="h-4 w-4 shrink-0" />
                  {!collapsed ? <span className="truncate">{n.label}</span> : null}
                </NavLink>
              </li>
            );
          })}
        </ul>

        {/* Filters only visible on /tools or when not collapsed */}
        {!collapsed && toolsOnly ? (
          <>
            <Separator className="my-4 bg-sidebar-border" />
            <p className="mono-caps mb-2 px-2 text-muted-foreground">Categories</p>
            <ul className="space-y-0.5">
              {(categories ?? []).map((c: Category) => {
                const I = categoryIcons[c.id] ?? Boxes;
                const count = countsByCategory.get(c.id) ?? 0;
                const active = activeCats.has(c.id);
                return (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => toggleCategory(c.id)}
                      className={cn(
                        'group/cat flex h-8 w-full items-center gap-2 rounded-md px-2 text-left text-[13px] transition-colors',
                        active
                          ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                          : 'text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
                      )}
                      aria-pressed={active}
                    >
                      <I className="h-3.5 w-3.5 shrink-0" />
                      <span className="flex-1 truncate">{c.name}</span>
                      <span
                        className={cn(
                          'rounded border border-sidebar-border px-1.5 font-mono text-[10px]',
                          active ? 'bg-background/50' : 'bg-sidebar-accent/30'
                        )}
                      >
                        {count}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>

            <Separator className="my-4 bg-sidebar-border" />
            <p className="mono-caps mb-2 px-2 text-muted-foreground">Health</p>
            <ul className="space-y-0.5">
              {HEALTH_FILTERS.map((h) => {
                const active = activeHealths.has(h.key);
                return (
                  <li key={h.key}>
                    <button
                      type="button"
                      onClick={() => toggleHealth(h.key)}
                      className={cn(
                        'flex h-8 w-full items-center gap-2.5 rounded-md px-2 text-left text-[13px] transition-colors',
                        active
                          ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                          : 'text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
                      )}
                      aria-pressed={active}
                    >
                      <span className={cn('size-2 rounded-full', h.dot)} />
                      <span className="truncate">{h.label}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </>
        ) : null}
      </nav>

      {/* Footer / collapse */}
      <div className={cn('border-t border-border px-2 py-2', collapsed && 'px-1')}>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={toggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className={cn(
            'w-full text-muted-foreground hover:text-foreground',
            collapsed ? 'justify-center' : 'justify-start gap-2 px-2'
          )}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" />
          ) : (
            <>
              <PanelLeftClose className="h-4 w-4" />
              <span className="text-xs">Collapse</span>
            </>
          )}
        </Button>
      </div>
    </aside>
  );
}

export const Sidebar = memo(_Sidebar);
