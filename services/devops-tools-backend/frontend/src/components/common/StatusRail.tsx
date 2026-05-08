/* Status rail — condensed dot strip summarising every tool's live health.
 * Each dot is a minimal interactive target: hover for a tooltip, click to
 * open the detail drawer for that tool. Animates a subtle pulse whenever
 * the upstream data changes. */
import { memo, useEffect, useRef, useState } from 'react';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useUiStore } from '@/store/ui';
import { statusMeta } from '@/lib/status';
import { cn, formatLatency, timeAgo } from '@/lib/utils';
import type { HealthStatus, Tool } from '@/types/tool';

interface StatusRailProps {
  tools: Tool[] | undefined;
  className?: string;
}

function orderScore(s: HealthStatus): number {
  return s === 'down' ? 0 : s === 'degraded' ? 1 : s === 'unknown' ? 2 : 3;
}

function _StatusRail({ tools, className }: StatusRailProps): React.ReactElement | null {
  const openDetail = useUiStore((s) => s.openDetail);
  const visible = useUiStore((s) => s.statusRailVisible);
  const [pulseKey, setPulseKey] = useState<number>(0);
  const lastSnapshotRef = useRef<string>('');

  // Pulse the rail whenever the aggregate snapshot changes (health status or latency).
  useEffect(() => {
    if (!tools) return;
    const snap = tools
      .map((t) => `${t.id}:${t.health_status ?? 'unknown'}:${t.latency_ms ?? -1}`)
      .join('|');
    if (snap !== lastSnapshotRef.current) {
      lastSnapshotRef.current = snap;
      setPulseKey((k) => k + 1);
    }
  }, [tools]);

  if (!visible) return null;
  if (!tools || tools.length === 0) return null;

  // Sort: trouble first (down → degraded → unknown → healthy).
  const sorted = [...tools].sort((a, b) => {
    const sa = orderScore((a.health_status ?? 'unknown') as HealthStatus);
    const sb = orderScore((b.health_status ?? 'unknown') as HealthStatus);
    if (sa !== sb) return sa - sb;
    return a.name.localeCompare(b.name);
  });

  const summary = sorted.reduce(
    (acc, t) => {
      const s = (t.health_status ?? 'unknown') as HealthStatus;
      acc[s] += 1;
      return acc;
    },
    { healthy: 0, degraded: 0, down: 0, unknown: 0 } as Record<HealthStatus, number>
  );

  return (
    <div
      role="region"
      aria-label="Tool status rail"
      className={cn(
        'flex items-center gap-3 overflow-hidden rounded-md border border-border/80 bg-card/40 px-3 py-1.5',
        'glass',
        className
      )}
    >
      <span className="mono-caps shrink-0 text-muted-foreground">Status rail</span>

      <div className="flex min-w-0 flex-1 items-center gap-[5px] overflow-hidden">
        {sorted.map((t, i) => {
          const status = (t.health_status ?? 'unknown') as HealthStatus;
          const meta = statusMeta(status);
          return (
            <Tooltip key={t.id}>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={() => openDetail(t.id)}
                  aria-label={`${t.name} — ${meta.label}`}
                  className={cn(
                    'group relative size-3 shrink-0 rounded-sm outline-none',
                    'transition-[transform,box-shadow] duration-200',
                    'hover:scale-[1.6] focus-visible:scale-[1.6]'
                  )}
                  style={{
                    background: meta.signal,
                    boxShadow: `0 0 4px color-mix(in oklch, ${meta.signal} 55%, transparent)`,
                    animation:
                      status === 'healthy'
                        ? undefined
                        : status === 'down'
                          ? 'pulse-signal 1.8s cubic-bezier(0.4,0,0.6,1) infinite'
                          : undefined,
                    animationDelay: `${(i % 8) * 60}ms`,
                    ['--tw-signal-color' as string]: meta.signal,
                    opacity: status === 'unknown' ? 0.55 : 1,
                  }}
                />
              </TooltipTrigger>
              <TooltipContent sideOffset={8} className="max-w-[240px]">
                <div className="flex flex-col gap-0.5">
                  <p className="text-sm font-semibold leading-tight">{t.name}</p>
                  <p className="font-mono text-[10.5px] uppercase tracking-wider text-muted-foreground">
                    {t.category} · {t.id}
                  </p>
                  <p className={cn('mt-0.5 text-[11px] font-semibold', meta.text)}>
                    {meta.label} · {formatLatency(t.latency_ms, t.last_checked)}
                  </p>
                  <p className="mt-0.5 font-mono text-[10.5px] text-muted-foreground">
                    last probe {timeAgo(t.last_checked)}
                  </p>
                </div>
              </TooltipContent>
            </Tooltip>
          );
        })}
      </div>

      {/* Compact summary counts — one chip per bucket */}
      <div
        key={pulseKey}
        className={cn(
          'flex shrink-0 items-center gap-1 font-mono text-[11px]',
          'animate-[count-up_0.5s_cubic-bezier(0.22,1,0.36,1)_both]'
        )}
      >
        <span className="text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))]">
          {summary.healthy}
        </span>
        <span className="text-muted-foreground/60">/</span>
        <span className="text-[color-mix(in_oklch,var(--warning)_92%,var(--foreground))]">
          {summary.degraded}
        </span>
        <span className="text-muted-foreground/60">/</span>
        <span className="text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))]">
          {summary.down}
        </span>
      </div>
    </div>
  );
}

export const StatusRail = memo(_StatusRail);
