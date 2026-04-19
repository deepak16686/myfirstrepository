/* Incidents strip — detects tool state transitions over the last 15 minutes
 * of the client-side health buffer and lists them with a short glyph trail. */
import { useMemo } from 'react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { HealthDot } from '@/components/tools/HealthDot';
import { getHealthHistory } from '@/hooks/useHealth';
import { useUiStore } from '@/store/ui';
import { timeAgo } from '@/lib/utils';
import { resolveIcon } from '@/lib/icons';
import { statusMeta } from '@/lib/status';
import { AlertOctagon, ArrowRight, CheckCircle2, CircleSlash2, History } from 'lucide-react';
import type { HealthStatus, Tool } from '@/types/tool';

interface IncidentsStripProps {
  tools: Tool[] | undefined;
  limit?: number;
}

interface Incident {
  id: string;
  toolId: string;
  toolName: string;
  icon: string;
  from: HealthStatus;
  to: HealthStatus;
  at: string;
  ts: number;
}

function detectIncidents(tools: Tool[] | undefined): Incident[] {
  if (!tools) return [];
  const out: Incident[] = [];
  for (const t of tools) {
    const hist = getHealthHistory(t.id);
    for (let i = 1; i < hist.length; i++) {
      const prev = hist[i - 1];
      const curr = hist[i];
      if (prev.status === curr.status) continue;
      const from = prev.status as HealthStatus;
      const to = curr.status as HealthStatus;
      // Filter the noisy unknown→anything transitions on cold boot.
      if (from === 'unknown' && to === 'healthy') continue;
      out.push({
        id: `${t.id}-${curr.t}`,
        toolId: t.id,
        toolName: t.name,
        icon: t.icon,
        from,
        to,
        at: new Date(curr.t).toISOString(),
        ts: curr.t,
      });
    }
  }
  return out.sort((a, b) => b.ts - a.ts);
}

function toneFor(to: HealthStatus): 'attention' | 'recovery' | 'warning' {
  if (to === 'down') return 'attention';
  if (to === 'degraded') return 'warning';
  return 'recovery';
}

export function IncidentsStrip({ tools, limit = 6 }: IncidentsStripProps): React.ReactElement {
  const openDetail = useUiStore((s) => s.openDetail);
  const incidents = useMemo(() => detectIncidents(tools).slice(0, limit), [tools, limit]);

  if (incidents.length === 0) {
    return (
      <Card className="flex items-center gap-3 p-5">
        <div className="flex size-10 items-center justify-center rounded-md bg-[color-mix(in_oklch,var(--success)_12%,transparent)] text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))]">
          <CheckCircle2 className="h-4 w-4" />
        </div>
        <div>
          <p className="text-sm font-semibold">No incidents in the last 15 minutes</p>
          <p className="text-[12px] text-muted-foreground">
            Transition history starts filling after the second probe cycle (~30s).
          </p>
        </div>
      </Card>
    );
  }

  return (
    <Card className="relative overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-2">
          <History className="h-4 w-4 text-muted-foreground" />
          <p className="text-sm font-semibold">Recent transitions</p>
          <span className="font-mono text-[11px] text-muted-foreground">
            · {incidents.length} in the last 15 min
          </span>
        </div>
      </div>
      <ul className="divide-y divide-border">
        {incidents.map((inc) => {
          const Icon = resolveIcon(inc.icon);
          const toMeta = statusMeta(inc.to);
          const fromMeta = statusMeta(inc.from);
          const tone = toneFor(inc.to);
          const toneCls =
            tone === 'attention'
              ? 'text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))]'
              : tone === 'warning'
                ? 'text-[color-mix(in_oklch,var(--warning)_92%,var(--foreground))]'
                : 'text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))]';

          return (
            <li
              key={inc.id}
              className="flex items-center gap-3 px-5 py-2.5 transition-colors hover:bg-muted/30"
            >
              <div className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-background">
                <Icon className="h-3.5 w-3.5" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium">{inc.toolName}</p>
                <div className="mt-0.5 flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
                  <span className={fromMeta.text}>{fromMeta.shortLabel}</span>
                  <ArrowRight className="h-3 w-3 opacity-60" />
                  <span className={toMeta.text}>{toMeta.shortLabel}</span>
                </div>
              </div>
              <div className={`flex shrink-0 items-center gap-1.5 ${toneCls}`}>
                {inc.to === 'down' ? (
                  <CircleSlash2 className="h-3.5 w-3.5" />
                ) : inc.to === 'healthy' ? (
                  <CheckCircle2 className="h-3.5 w-3.5" />
                ) : (
                  <AlertOctagon className="h-3.5 w-3.5" />
                )}
                <HealthDot status={inc.to} pulse={false} size="sm" />
                <time className="font-mono text-[11px]">{timeAgo(inc.at)}</time>
              </div>
              <Button size="sm" variant="ghost" onClick={() => openDetail(inc.toolId)}>
                Detail
              </Button>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}
