/* Category × health heatmap. Each cell is a category summary with a healthy%
 * intensity gradient; click a cell to filter the Tools page by that category. */
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Category, HealthStatus, Tool } from '@/types/tool';
import { Card } from '@/components/ui/card';
import { resolveIcon, categoryIcons } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { Boxes } from 'lucide-react';

interface HeatmapProps {
  tools: Tool[] | undefined;
  categories: Category[] | undefined;
}

interface CellStats {
  total: number;
  healthy: number;
  degraded: number;
  down: number;
  unknown: number;
  pct: number;
}

function statsFor(list: Tool[]): CellStats {
  const bucket = { healthy: 0, degraded: 0, down: 0, unknown: 0 };
  for (const t of list) {
    const s = (t.health_status ?? 'unknown') as HealthStatus;
    bucket[s] += 1;
  }
  const total = list.length;
  const pct = total > 0 ? Math.round((bucket.healthy / total) * 100) : 0;
  return { ...bucket, total, pct };
}

function intensityBg(stats: CellStats): string {
  if (stats.total === 0) return 'bg-muted/20 text-muted-foreground/70';
  if (stats.down > 0 && stats.pct < 50) {
    return 'bg-[color-mix(in_oklch,var(--destructive)_22%,var(--card))]';
  }
  if (stats.degraded > 0 && stats.pct < 80) {
    return 'bg-[color-mix(in_oklch,var(--warning)_20%,var(--card))]';
  }
  if (stats.pct >= 80) {
    return 'bg-[color-mix(in_oklch,var(--success)_18%,var(--card))]';
  }
  return 'bg-muted/35';
}

export function CategoryHeatmap({ tools, categories }: HeatmapProps): React.ReactElement {
  const navigate = useNavigate();

  const cellsByCat = useMemo(() => {
    const list = tools ?? [];
    const map = new Map<string, Tool[]>();
    for (const t of list) {
      const arr = map.get(t.category) ?? [];
      arr.push(t);
      map.set(t.category, arr);
    }
    return map;
  }, [tools]);

  const orderedCats = useMemo(() => {
    const cats = (categories ?? []).slice().sort((a, b) => a.order - b.order);
    return cats;
  }, [categories]);

  if (orderedCats.length === 0) {
    return (
      <Card className="p-5">
        <p className="mono-caps text-muted-foreground">Category heatmap · empty</p>
      </Card>
    );
  }

  return (
    <Card className="relative flex h-full flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-2">
          <Boxes className="h-4 w-4 text-muted-foreground" />
          <p className="text-sm font-semibold">Category heatmap</p>
          <span className="font-mono text-[11px] text-muted-foreground">
            · healthy% per category
          </span>
        </div>
        <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <span className="size-2 rounded-sm bg-[color-mix(in_oklch,var(--success)_35%,var(--card))]" />
            80+
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="size-2 rounded-sm bg-[color-mix(in_oklch,var(--warning)_35%,var(--card))]" />
            50–79
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="size-2 rounded-sm bg-[color-mix(in_oklch,var(--destructive)_35%,var(--card))]" />
            &lt;50
          </span>
        </div>
      </div>
      <div className="grid flex-1 grid-cols-2 gap-2 p-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7">
        {orderedCats.map((c) => {
          const stats = statsFor(cellsByCat.get(c.id) ?? []);
          const Icon = categoryIcons[c.id] ?? resolveIcon(null);
          return (
            <button
              key={c.id}
              type="button"
              onClick={() => navigate(`/tools?category=${encodeURIComponent(c.id)}`)}
              className={cn(
                'group relative flex h-[92px] flex-col items-start justify-between rounded-lg border border-border/70 p-3 text-left',
                'transition-all duration-200 hover:border-ring/70 hover:shadow-[0_0_0_1px_color-mix(in_oklch,var(--ring)_25%,transparent)]',
                intensityBg(stats)
              )}
              aria-label={`${c.name} — ${stats.pct}% healthy`}
            >
              <div className="flex w-full items-center justify-between">
                <Icon className="h-3.5 w-3.5 text-foreground/70" />
                <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  {stats.total}
                </span>
              </div>
              <div>
                <p className="truncate text-[12px] font-semibold leading-tight">{c.name}</p>
                <div className="mt-1 flex items-baseline gap-1">
                  <span className="font-mono text-[20px] font-semibold leading-none tabular-nums">
                    {stats.pct}
                  </span>
                  <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    % healthy
                  </span>
                </div>
              </div>

              {/* Fine dot indicators for degraded/down */}
              {stats.down > 0 || stats.degraded > 0 ? (
                <span className="absolute right-2.5 top-2.5 flex items-center gap-0.5">
                  {stats.down > 0 ? (
                    <span className="size-1.5 rounded-full bg-[var(--destructive)] shadow-[0_0_4px_var(--destructive)]" />
                  ) : null}
                  {stats.degraded > 0 ? (
                    <span className="size-1.5 rounded-full bg-[var(--warning)] shadow-[0_0_4px_var(--warning)]" />
                  ) : null}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
    </Card>
  );
}
