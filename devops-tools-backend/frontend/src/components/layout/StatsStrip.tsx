/**
 * StatsStrip — thin horizontal instrument row sitting between the top bar
 * and the category chips. Gives operators the global health summary in
 * one glance: total / healthy / degraded / down / last probe time /
 * polling indicator.
 *
 * Visual language (Mission Control):
 *   - Monospace numerics with tabular-nums so digits line up as the
 *     counter ticks over.
 *   - Each segment separated by a thin 1px vertical rule.
 *   - "Last probe" shows a live age string that refreshes every second via
 *     the parent re-render cycle (the health query already refetches every
 *     15s, which causes a re-render).
 *   - A subtle throb on the primary accent when a fetch is in flight.
 */
import { memo, useEffect, useMemo, useState } from 'react';
import { Activity, AlertTriangle, CheckCircle2, CircleSlash2, RefreshCw } from 'lucide-react';
import type { Tool } from '@/types/tool';
import { cn, timeAgo } from '@/lib/utils';
import { Button } from '@/components/ui/button';

interface StatsStripProps {
  tools: Tool[];
  isFetching?: boolean;
  onRefresh?: () => void;
  className?: string;
}

interface Agg {
  total: number;
  healthy: number;
  degraded: number;
  down: number;
  unknown: number;
  lastChecked: string | null;
}

function aggregate(tools: Tool[]): Agg {
  let healthy = 0;
  let degraded = 0;
  let down = 0;
  let unknown = 0;
  let latestMs = 0;
  let latestIso: string | null = null;
  for (const t of tools) {
    const s = t.health_status ?? 'unknown';
    if (s === 'healthy') healthy++;
    else if (s === 'degraded') degraded++;
    else if (s === 'down') down++;
    else unknown++;
    if (t.last_checked) {
      const ms = new Date(t.last_checked).getTime();
      if (!Number.isNaN(ms) && ms > latestMs) {
        latestMs = ms;
        latestIso = t.last_checked;
      }
    }
  }
  return { total: tools.length, healthy, degraded, down, unknown, lastChecked: latestIso };
}

function _StatsStrip({
  tools,
  isFetching = false,
  onRefresh,
  className,
}: StatsStripProps): React.ReactElement {
  const agg = useMemo(() => aggregate(tools), [tools]);
  // Rerender every second to keep "Last probe Xs ago" ticking without
  // relying on the parent. We use a tiny counter instead of Date.now to
  // keep React happy.
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => (n + 1) % 60), 1000);
    return () => window.clearInterval(id);
  }, []);

  const healthyPct =
    agg.total > 0 ? Math.round((agg.healthy / agg.total) * 100) : 0;

  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-0 rounded-lg border border-border bg-card/60 px-1 py-1',
        'font-mono text-[11px] text-muted-foreground tabular-nums',
        'shadow-[inset_0_0_0_1px_color-mix(in_oklch,var(--border)_60%,transparent)]',
        className,
      )}
      role="status"
      aria-live="polite"
      aria-label="Portal health summary"
    >
      {/* Left rail — total */}
      <Segment
        label="Total"
        icon={<Activity className="h-3 w-3 text-muted-foreground/70" aria-hidden />}
        value={<span className="text-foreground/90">{agg.total}</span>}
      />

      {/* Healthy */}
      <Segment
        label="Healthy"
        icon={
          <CheckCircle2
            className="h-3 w-3 text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))]"
            aria-hidden
          />
        }
        value={
          <span className="text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))]">
            {agg.healthy}
            <span className="ml-1 text-muted-foreground/70">· {healthyPct}%</span>
          </span>
        }
      />

      {/* Degraded */}
      <Segment
        label="Degraded"
        icon={
          <AlertTriangle
            className={cn(
              'h-3 w-3',
              agg.degraded > 0
                ? 'text-[color-mix(in_oklch,var(--warning)_92%,var(--foreground))]'
                : 'text-muted-foreground/50',
            )}
            aria-hidden
          />
        }
        value={
          <span
            className={cn(
              agg.degraded > 0
                ? 'text-[color-mix(in_oklch,var(--warning)_92%,var(--foreground))]'
                : 'text-foreground/70',
            )}
          >
            {agg.degraded}
          </span>
        }
      />

      {/* Down */}
      <Segment
        label="Down"
        icon={
          <CircleSlash2
            className={cn(
              'h-3 w-3',
              agg.down > 0
                ? 'text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))]'
                : 'text-muted-foreground/50',
            )}
            aria-hidden
          />
        }
        value={
          <span
            className={cn(
              agg.down > 0
                ? 'text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))]'
                : 'text-foreground/70',
            )}
          >
            {agg.down}
          </span>
        }
      />

      {/* Probe timestamp + refresh */}
      <div className="ml-auto flex items-center gap-2 px-3 py-1">
        <span className="mono-caps text-muted-foreground/70">Last probe</span>
        <span
          className={cn(
            'rounded border border-border/70 bg-background/60 px-1.5 py-0.5',
            'text-foreground/85',
          )}
        >
          {timeAgo(agg.lastChecked)}
        </span>
        {onRefresh ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={onRefresh}
            aria-label="Refresh health probes"
            className={cn(
              'size-6 text-muted-foreground hover:text-foreground',
              isFetching && 'text-foreground',
            )}
          >
            <RefreshCw className={cn('h-3 w-3', isFetching && 'animate-spin')} />
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function Segment({
  label,
  icon,
  value,
}: {
  label: string;
  icon?: React.ReactNode;
  value: React.ReactNode;
}): React.ReactElement {
  return (
    <div className="flex items-center gap-2 border-r border-border/60 px-3 py-1 last:border-r-0">
      {icon}
      <span className="mono-caps text-muted-foreground/80">{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  );
}

export const StatsStrip = memo(_StatsStrip);
