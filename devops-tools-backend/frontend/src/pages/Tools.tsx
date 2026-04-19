/* Tools page — sticky filter bar, view tabs (grid/table/compact), saved-view
 * chips, URL-synced query + category + health filters. */
import { useMemo } from 'react';
import { useOutletContext, useSearchParams } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { X } from 'lucide-react';
import type { Category, HealthStatus, Tool } from '@/types/tool';
import { PageHeader } from '@/components/common/PageHeader';
import { ToolsFilterBar } from '@/components/tools/ToolsFilterBar';
import { ToolCard } from '@/components/tools/ToolCard';
import { ToolsTableView } from '@/components/tools/ToolsTableView';
import { ToolsCompactView } from '@/components/tools/ToolsCompactView';
import { useUiStore, type SavedViewKey } from '@/store/ui';
import { launchTool } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';

interface Ctx {
  tools: Tool[] | undefined;
  categories: Category[] | undefined;
  loading: boolean;
}

function applySavedView(tools: Tool[], saved: SavedViewKey): Tool[] {
  if (saved === 'all') return tools;
  if (saved === 'ai') return tools.filter((t) => t.category === 'ai');
  if (saved === 'cicd') return tools.filter((t) => t.category === 'cicd');
  if (saved === 'down') return tools.filter((t) => (t.health_status ?? 'unknown') === 'down');
  return tools;
}

export function Tools(): React.ReactElement {
  const { tools, categories, loading } = useOutletContext<Ctx>();
  const [params, setParams] = useSearchParams();
  const view = useUiStore((s) => s.toolsView);
  const saved = useUiStore((s) => s.savedView);
  const openDetail = useUiStore((s) => s.openDetail);
  const navigate = useNavigate();

  const q = params.get('q') ?? '';
  const setQuery = (next: string): void => {
    const n = new URLSearchParams(params);
    if (next) n.set('q', next);
    else n.delete('q');
    setParams(n, { replace: true });
  };

  const activeCats = useMemo(
    () => new Set((params.getAll('category') ?? []).flatMap((v) => v.split(','))),
    [params]
  );
  const activeHealths = useMemo(
    () =>
      new Set(
        (params.getAll('health') ?? []).flatMap((v) => v.split(','))
      ) as Set<HealthStatus>,
    [params]
  );

  const clearFilters = (): void => {
    const next = new URLSearchParams();
    setParams(next, { replace: true });
  };

  const filtered = useMemo(() => {
    const list = tools ?? [];
    const savedApplied = applySavedView(list, saved);
    const ql = q.trim().toLowerCase();
    return savedApplied.filter((t) => {
      if (activeCats.size > 0 && !activeCats.has(t.category)) return false;
      if (activeHealths.size > 0 && !activeHealths.has((t.health_status ?? 'unknown') as HealthStatus))
        return false;
      if (!ql) return true;
      const hay = [t.name, t.id, t.description, t.category, ...(t.tags ?? [])]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return hay.includes(ql);
    });
  }, [tools, saved, activeCats, activeHealths, q]);

  const totalCount = tools?.length ?? 0;
  const appliedCount = activeCats.size + activeHealths.size + (q ? 1 : 0) + (saved !== 'all' ? 1 : 0);

  const categoryNameMap = useMemo(() => {
    const m = new Map<string, string>();
    (categories ?? []).forEach((c) => m.set(c.id, c.name));
    return m;
  }, [categories]);

  const onLaunch = async (t: Tool): Promise<void> => {
    if (!t.url_external) {
      toast.error('No external URL configured');
      return;
    }
    try {
      const r = await launchTool(t.id);
      window.open(r.redirect_url || t.url_external, '_blank', 'noopener,noreferrer');
    } catch {
      window.open(t.url_external, '_blank', 'noopener,noreferrer');
    }
  };

  const onEmbed = (t: Tool): void => {
    if (!t.embed) {
      toast.error(`${t.name} cannot be embedded; opening externally.`);
      void onLaunch(t);
      return;
    }
    navigate(`/embed/${t.id}`);
  };

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Catalog"
        title="Tools"
        description="Every tool registered in config/tools.yaml with live health. Cycle views with the tabs, refine with the saved-view chips, or press / to search."
        actions={
          appliedCount > 0 ? (
            <Button variant="outline" size="sm" onClick={clearFilters}>
              <X className="h-3.5 w-3.5" />
              Clear filters ({appliedCount})
            </Button>
          ) : null
        }
      />

      <ToolsFilterBar
        query={q}
        setQuery={setQuery}
        visibleCount={filtered.length}
        totalCount={totalCount}
      />

      {appliedCount > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="mono-caps text-muted-foreground">active filters</span>
          {q ? (
            <Badge variant="outline" className="gap-1">
              q: <span className="font-mono">{q}</span>
              <button
                type="button"
                aria-label="Clear search"
                className="ml-0.5 opacity-60 hover:opacity-100"
                onClick={() => setQuery('')}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ) : null}
          {saved !== 'all' ? (
            <Badge variant="default" className="gap-1 uppercase">
              view: <span className="font-mono">{saved}</span>
            </Badge>
          ) : null}
          {[...activeCats].map((c) => (
            <Badge key={`c-${c}`} variant="outline" className="gap-1">
              {categoryNameMap.get(c) ?? c}
              <button
                type="button"
                aria-label={`Remove category ${c}`}
                className="ml-0.5 opacity-60 hover:opacity-100"
                onClick={() => {
                  const next = new URLSearchParams(params);
                  next.delete('category');
                  [...activeCats].filter((x) => x !== c).forEach((x) => next.append('category', x));
                  setParams(next, { replace: true });
                }}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
          {[...activeHealths].map((h) => (
            <Badge
              key={`h-${h}`}
              variant={
                h === 'healthy'
                  ? 'success'
                  : h === 'degraded'
                    ? 'warning'
                    : h === 'down'
                      ? 'danger'
                      : 'outline'
              }
              className="gap-1"
            >
              {h}
              <button
                type="button"
                aria-label={`Remove ${h} filter`}
                className="ml-0.5 opacity-70 hover:opacity-100"
                onClick={() => {
                  const next = new URLSearchParams(params);
                  next.delete('health');
                  [...activeHealths].filter((x) => x !== h).forEach((x) => next.append('health', x));
                  setParams(next, { replace: true });
                }}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      ) : null}

      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-[180px] rounded-lg" />
          ))}
        </div>
      ) : (
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={view}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            {view === 'grid' ? (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                <AnimatePresence initial={false}>
                  {filtered.map((t, i) => (
                    <ToolCard
                      key={t.id}
                      tool={t}
                      categoryName={categoryNameMap.get(t.category)}
                      onDetail={openDetail}
                      onLaunch={onLaunch}
                      onEmbed={onEmbed}
                      style={{ animationDelay: `${Math.min(i * 18, 320)}ms` }}
                    />
                  ))}
                </AnimatePresence>
              </div>
            ) : null}

            {view === 'table' ? (
              <ToolsTableView tools={filtered} categories={categories} />
            ) : null}

            {view === 'compact' ? <ToolsCompactView tools={filtered} /> : null}
          </motion.div>
        </AnimatePresence>
      )}
    </div>
  );
}
