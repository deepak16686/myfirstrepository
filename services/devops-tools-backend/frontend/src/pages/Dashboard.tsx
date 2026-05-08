/* Dashboard — gradient KPIs w/ count-up + sparks, category heatmap, latency
 * histogram, incidents strip, synthesised activity stream. */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useOutletContext, useNavigate } from 'react-router-dom';
import {
  Activity as ActivityIcon,
  AlertTriangle,
  CheckCircle2,
  Layers as LayersIcon,
} from 'lucide-react';
import { PageHeader } from '@/components/common/PageHeader';
import { KpiCard } from '@/components/dashboard/KpiCard';
import { CriticalStrip } from '@/components/dashboard/CriticalStrip';
import { ActivityFeed } from '@/components/dashboard/ActivityFeed';
import { CategoryHeatmap } from '@/components/dashboard/CategoryHeatmap';
import { LatencyHistogram } from '@/components/dashboard/LatencyHistogram';
import { IncidentsStrip } from '@/components/dashboard/IncidentsStrip';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { HealthDot } from '@/components/tools/HealthDot';
import { resolveIcon } from '@/lib/icons';
import { useUiStore } from '@/store/ui';
import type { Category, Tool } from '@/types/tool';

interface Ctx {
  tools: Tool[] | undefined;
  categories: Category[] | undefined;
  loading: boolean;
}

interface Stats {
  total: number;
  healthy: number;
  degraded: number;
  down: number;
  healthyPct: number;
}

function useStatsTrend(stats: Stats): {
  healthyTrend: number[];
  degradedTrend: number[];
  downTrend: number[];
  totalTrend: number[];
} {
  const [healthyTrend, setHealthyTrend] = useState<number[]>([]);
  const [degradedTrend, setDegradedTrend] = useState<number[]>([]);
  const [downTrend, setDownTrend] = useState<number[]>([]);
  const [totalTrend, setTotalTrend] = useState<number[]>([]);
  const last = useRef<string>('');

  useEffect(() => {
    const key = `${stats.total}|${stats.healthy}|${stats.degraded}|${stats.down}`;
    if (key === last.current) return;
    last.current = key;
    setHealthyTrend((p) => [...p.slice(-23), stats.healthy]);
    setDegradedTrend((p) => [...p.slice(-23), stats.degraded]);
    setDownTrend((p) => [...p.slice(-23), stats.down]);
    setTotalTrend((p) => [...p.slice(-23), stats.total]);
  }, [stats]);

  return { healthyTrend, degradedTrend, downTrend, totalTrend };
}

export function Dashboard(): React.ReactElement {
  const { tools, categories, loading } = useOutletContext<Ctx>();
  const navigate = useNavigate();
  const openDetail = useUiStore((s) => s.openDetail);

  const stats: Stats = useMemo(() => {
    const list = tools ?? [];
    const tot = list.length;
    const hc = list.filter((t) => t.health_status === 'healthy').length;
    const dg = list.filter((t) => t.health_status === 'degraded').length;
    const dn = list.filter((t) => t.health_status === 'down').length;
    const pct = tot > 0 ? Math.round((hc / tot) * 100) : 0;
    return { total: tot, healthy: hc, degraded: dg, down: dn, healthyPct: pct };
  }, [tools]);

  const { healthyTrend, degradedTrend, downTrend, totalTrend } = useStatsTrend(stats);

  const critical = useMemo(() => (tools ?? []).filter((t) => t.health_status === 'down'), [tools]);

  const categoriesCount = categories?.length ?? 0;

  const featuredByCategory = useMemo(() => {
    const list = tools ?? [];
    const groups = new Map<string, Tool[]>();
    list.forEach((t) => {
      const arr = groups.get(t.category) ?? [];
      arr.push(t);
      groups.set(t.category, arr);
    });
    return groups;
  }, [tools]);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Control plane · Overview"
        title="DevOps Command Center"
        description="Unified view of every locally-hosted tool in the infra-stack, dev-stack, and app projects. Live health, launch, embed, and drill-down in one place."
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => navigate('/tools')}>
              Browse tools
            </Button>
            <Button size="sm" onClick={() => navigate('/pipelines')}>
              View pipelines
            </Button>
          </>
        }
      />

      {/* KPI row */}
      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[160px] rounded-lg" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard
            label="Total tools"
            value={stats.total}
            hint={
              <>
                across <span className="font-mono">{categoriesCount}</span> categories
              </>
            }
            icon={LayersIcon}
            tone="default"
            trend={totalTrend}
          />
          <KpiCard
            label="Healthy"
            value={stats.healthyPct}
            percent
            hint={
              <>
                <span className="font-mono">{stats.healthy}</span> of{' '}
                <span className="font-mono">{stats.total}</span> responding
              </>
            }
            icon={CheckCircle2}
            tone="success"
            trend={healthyTrend}
          />
          <KpiCard
            label="Degraded"
            value={stats.degraded}
            hint="High latency or partial response"
            icon={ActivityIcon}
            tone="warning"
            trend={degradedTrend}
          />
          <KpiCard
            label="Down"
            value={stats.down}
            hint={stats.down === 0 ? 'No known outages' : 'Immediate attention required'}
            icon={AlertTriangle}
            tone="danger"
            trend={downTrend}
          />
        </div>
      )}

      {/* Critical strip */}
      {loading ? <Skeleton className="h-[160px] rounded-lg" /> : <CriticalStrip tools={critical} />}

      {/* Heatmap */}
      {loading ? (
        <Skeleton className="h-[220px] rounded-lg" />
      ) : (
        <CategoryHeatmap tools={tools} categories={categories} />
      )}

      {/* Latency histogram + Incidents strip */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {loading ? (
            <Skeleton className="h-[220px] rounded-lg" />
          ) : (
            <LatencyHistogram tools={tools} />
          )}
        </div>
        <div>
          {loading ? (
            <Skeleton className="h-[220px] rounded-lg" />
          ) : (
            <IncidentsStrip tools={tools} />
          )}
        </div>
      </div>

      {/* Activity feed + Top picks */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {loading ? (
            <Skeleton className="h-[320px] rounded-lg" />
          ) : (
            <ActivityFeed tools={tools ?? []} />
          )}
        </div>

        <Card className="flex flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b border-border px-5 py-3">
            <p className="text-sm font-semibold">Top picks</p>
            <span className="font-mono text-[11px] text-muted-foreground">
              one per category · click to open
            </span>
          </div>
          <div className="max-h-[320px] flex-1 overflow-y-auto">
            <ul className="divide-y divide-border">
              {(categories ?? [])
                .slice()
                .sort((a, b) => a.order - b.order)
                .map((c) => {
                  const first = featuredByCategory.get(c.id)?.[0];
                  if (!first) return null;
                  const Icon = resolveIcon(first.icon);
                  return (
                    <li key={c.id}>
                      <button
                        type="button"
                        onClick={() => openDetail(first.id)}
                        className="group flex w-full items-center gap-3 px-5 py-3 text-left transition-colors hover:bg-muted/30"
                      >
                        <span className="flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-background">
                          <Icon className="h-3.5 w-3.5" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium">{first.name}</p>
                          <p className="truncate font-mono text-[11px] text-muted-foreground">
                            {c.name}
                          </p>
                        </div>
                        <HealthDot status={first.health_status ?? 'unknown'} />
                      </button>
                    </li>
                  );
                })}
            </ul>
          </div>
        </Card>
      </div>
    </div>
  );
}
