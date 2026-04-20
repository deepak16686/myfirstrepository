/**
 * DensePortal — the primary "mission control" view of the portal.
 *
 * Target UX:
 *   - All tools (currently 34) visible in roughly two scroll-heights.
 *   - Category-grouped with sticky per-category headers while scrolling.
 *   - 4-col grid on ≥xl, 3-col on ≥lg, 2-col on ≥sm, 1-col on mobile.
 *   - Top row: StatsStrip (global health summary) + CategoryChips.
 *   - Inline fuzzy search (also available via ⌘K palette).
 *
 * Data flow:
 *   - Consumes the `tools + categories + loading` context injected by
 *     AppShell's `<Outlet context={…}>`; no direct API calls here.
 *   - Filters via `useFilterStore` (category multi-select + text query +
 *     only-failing toggle).
 *   - Text search uses Fuse.js for typo-tolerant matching across name /
 *     id / description / tags.
 *
 * Aesthetic (Mission Control / Flight Deck):
 *   - Monospace section headers, uppercase micro-labels.
 *   - Sticky category headers with a soft glass blur and an underline.
 *   - "NO MATCH" empty state with a diagnostic tip, not a sad-face
 *     illustration.
 *   - `motion` staggered fade-in on initial render only (respects
 *     `prefers-reduced-motion`).
 */
import { useDeferredValue, useEffect, useMemo, useRef } from 'react';
import { useNavigate, useOutletContext } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import Fuse from 'fuse.js';
import { Filter, Search, X, Activity } from 'lucide-react';
import { toast } from 'sonner';

import type { Category, CategoryId, HealthStatus, Tool } from '@/types/tool';
import { StatsStrip } from '@/components/layout/StatsStrip';
import { CategoryChips } from '@/components/layout/CategoryChips';
import { ToolCard } from '@/components/cards/ToolCard';
import { useFilterStore } from '@/stores/useFilterStore';
import { useContextUrl } from '@/hooks/useContextUrl';
import { useHealth } from '@/hooks/useHealth';
import { categoryIcons } from '@/lib/icons';
import { useUiStore } from '@/store/ui';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

interface Ctx {
  tools: Tool[] | undefined;
  categories: Category[] | undefined;
  loading: boolean;
}

export function DensePortal(): React.ReactElement {
  const { tools, categories, loading } = useOutletContext<Ctx>();
  const navigate = useNavigate();
  const openDetail = useUiStore((s) => s.openDetail);
  const { context, pickUrl } = useContextUrl();
  const { isLoading: healthLoading, refetch: refetchHealth } = useHealth();

  const query = useFilterStore((s) => s.query);
  const setQuery = useFilterStore((s) => s.setQuery);
  const selectedCategories = useFilterStore((s) => s.selectedCategories);
  const selectedHealth = useFilterStore((s) => s.selectedHealth);
  const toggleHealth = useFilterStore((s) => s.toggleHealth);
  const onlyFailing = useFilterStore((s) => s.onlyFailing);
  const setOnlyFailing = useFilterStore((s) => s.setOnlyFailing);
  const clearAll = useFilterStore((s) => s.clearAll);
  const activeCount = useFilterStore((s) => s.activeCount());

  // Debounced query so fast typists don't trigger 34×(N-chars) re-sorts.
  const deferredQuery = useDeferredValue(query);

  // Build fuse index once per tools change.
  const fuse = useMemo(() => {
    if (!tools || tools.length === 0) return null;
    return new Fuse(tools, {
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

  // Filtered result list.
  const filtered = useMemo<Tool[]>(() => {
    if (!tools) return [];
    let list = tools;

    // Category filter
    if (selectedCategories.size > 0) {
      list = list.filter((t) => selectedCategories.has(t.category));
    }

    // Health filter
    if (selectedHealth.size > 0) {
      list = list.filter((t) =>
        selectedHealth.has((t.health_status ?? 'unknown') as HealthStatus),
      );
    }

    // "Only failing" convenience toggle
    if (onlyFailing) {
      list = list.filter((t) => {
        const s = t.health_status ?? 'unknown';
        return s === 'down' || s === 'degraded';
      });
    }

    // Text query via fuse
    const q = deferredQuery.trim();
    if (q && fuse) {
      const hitIds = new Set(fuse.search(q).map((r) => r.item.id));
      list = list.filter((t) => hitIds.has(t.id));
    }

    return list;
  }, [tools, selectedCategories, selectedHealth, onlyFailing, deferredQuery, fuse]);

  // Group by category.
  const groups = useMemo(() => {
    if (!categories || filtered.length === 0) return [];
    const byId = new Map<CategoryId, Tool[]>();
    filtered.forEach((t) => {
      const arr = byId.get(t.category) ?? [];
      arr.push(t);
      byId.set(t.category, arr);
    });
    return [...categories]
      .filter((c) => (byId.get(c.id)?.length ?? 0) > 0)
      .sort((a, b) => a.order - b.order)
      .map((c) => ({ category: c, tools: byId.get(c.id)! }));
  }, [categories, filtered]);

  const categoryNameMap = useMemo(() => {
    const m = new Map<string, string>();
    (categories ?? []).forEach((c) => m.set(c.id, c.name));
    return m;
  }, [categories]);

  const searchRef = useRef<HTMLInputElement>(null);

  // `/` keyboard shortcut to focus inline search (same as before).
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      const typing = tag === 'INPUT' || tag === 'TEXTAREA';
      if (!typing && e.key === '/' && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const onEmbed = (t: Tool): void => {
    if (!t.embed) {
      toast.error(`${t.name} cannot be embedded`);
      return;
    }
    navigate(`/embed/${t.id}`);
  };

  const visibleTotal = tools?.length ?? 0;
  const visibleFiltered = filtered.length;

  const HEALTH_FILTERS: Array<{ key: HealthStatus; label: string; dot: string }> = [
    { key: 'healthy', label: 'Healthy', dot: 'bg-[var(--success)]' },
    { key: 'degraded', label: 'Degraded', dot: 'bg-[var(--warning)]' },
    { key: 'down', label: 'Down', dot: 'bg-[var(--destructive)]' },
    { key: 'unknown', label: 'Unknown', dot: 'bg-muted-foreground/60' },
  ];

  return (
    <div className="space-y-4">
      {/* Stats row + refresh */}
      <StatsStrip
        tools={tools ?? []}
        isFetching={healthLoading}
        onRefresh={() => refetchHealth()}
      />

      {/* Filter row — chips + search + health + only-failing */}
      <div className="flex flex-col gap-2 rounded-lg border border-border bg-card/40 p-2">
        <CategoryChips tools={tools ?? []} categories={categories ?? []} />

        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          {/* Inline fuzzy search */}
          <label
            className={cn(
              'relative flex h-8 min-w-0 flex-1 items-center gap-2 rounded-md border border-border bg-muted/25 px-2.5',
              'focus-within:border-ring focus-within:bg-card md:max-w-[440px]',
              'transition-colors',
            )}
          >
            <Search className="h-3 w-3 text-muted-foreground" aria-hidden />
            <input
              ref={searchRef}
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter by name, id, tag, category…  press / to focus"
              aria-label="Filter tools"
              className="h-full w-full bg-transparent font-mono text-[12px] outline-hidden placeholder:text-muted-foreground/70"
            />
            {query ? (
              <button
                type="button"
                aria-label="Clear filter"
                className="rounded p-0.5 text-muted-foreground hover:text-foreground"
                onClick={() => setQuery('')}
              >
                <X className="h-3 w-3" />
              </button>
            ) : null}
            <span className="hidden font-mono text-[10px] text-muted-foreground md:inline">
              {visibleFiltered}/{visibleTotal}
            </span>
          </label>

          {/* Health chips */}
          <div className="flex flex-wrap items-center gap-1">
            {HEALTH_FILTERS.map((h) => {
              const active = selectedHealth.has(h.key);
              return (
                <button
                  key={h.key}
                  type="button"
                  onClick={() => toggleHealth(h.key)}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1',
                    'font-mono text-[10.5px] uppercase tracking-wider transition-colors',
                    active
                      ? 'border-ring/40 bg-[color-mix(in_oklch,var(--accent-signal)_10%,var(--card))] text-foreground'
                      : 'border-border text-muted-foreground hover:text-foreground',
                  )}
                  aria-pressed={active}
                >
                  <span className={cn('size-1.5 rounded-full', h.dot)} aria-hidden />
                  {h.label}
                </button>
              );
            })}
            <button
              type="button"
              onClick={() => setOnlyFailing(!onlyFailing)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1',
                'font-mono text-[10.5px] uppercase tracking-wider transition-colors',
                onlyFailing
                  ? 'border-[color-mix(in_oklch,var(--destructive)_40%,var(--border))] bg-[color-mix(in_oklch,var(--destructive)_14%,transparent)] text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))]'
                  : 'border-border text-muted-foreground hover:text-foreground',
              )}
              aria-pressed={onlyFailing}
              title="Show only tools that are down or degraded"
            >
              <Activity className="h-3 w-3" aria-hidden />
              Failing only
            </button>
            {activeCount > 0 ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={clearAll}
                className="h-7 gap-1 px-2 font-mono text-[10.5px] uppercase tracking-wider"
              >
                <Filter className="h-3 w-3" />
                Clear ({activeCount})
              </Button>
            ) : null}
          </div>
        </div>
      </div>

      {/* Grid — grouped by category with sticky headers */}
      {loading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 12 }).map((_, i) => (
            <Skeleton key={i} className="h-[138px] rounded-lg" />
          ))}
        </div>
      ) : groups.length === 0 ? (
        <EmptyState
          onReset={clearAll}
          query={query}
          hasCategoryFilter={selectedCategories.size > 0}
        />
      ) : (
        <div className="space-y-6">
          <AnimatePresence initial={false}>
            {groups.map((g, groupIdx) => {
              const CatIcon = categoryIcons[g.category.id] ?? Activity;
              const healthyInGroup = g.tools.filter(
                (t) => t.health_status === 'healthy',
              ).length;
              const downInGroup = g.tools.filter(
                (t) => t.health_status === 'down',
              ).length;
              return (
                <section key={g.category.id} aria-labelledby={`cat-${g.category.id}`}>
                  {/* Sticky category header */}
                  <div
                    className={cn(
                      'sticky top-[56px] z-10 -mx-4 mb-3 flex items-center gap-2 border-b border-border/60 px-4 py-2',
                      'sm:-mx-8 sm:px-8',
                      'glass backdrop-blur-md',
                    )}
                    style={{ top: 56 }}
                  >
                    <CatIcon className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
                    <h2
                      id={`cat-${g.category.id}`}
                      className="font-mono text-[11.5px] font-semibold uppercase tracking-[0.18em] text-foreground/90"
                    >
                      {g.category.name}
                    </h2>
                    <span className="font-mono text-[10.5px] text-muted-foreground tabular-nums">
                      {healthyInGroup}/{g.tools.length}{' '}
                      <span className="opacity-70">healthy</span>
                    </span>
                    {downInGroup > 0 ? (
                      <span className="ml-2 inline-flex items-center gap-1 rounded-full border border-[color-mix(in_oklch,var(--destructive)_40%,var(--border))] bg-[color-mix(in_oklch,var(--destructive)_14%,transparent)] px-1.5 py-0.5 font-mono text-[9.5px] uppercase tracking-wider text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))]">
                        {downInGroup} down
                      </span>
                    ) : null}
                    <span className="ml-auto font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground/70">
                      #{groupIdx + 1}
                    </span>
                  </div>

                  {/* Cards */}
                  <motion.div
                    layout
                    className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
                  >
                    {g.tools.map((t, i) => (
                      <ToolCard
                        key={t.id}
                        tool={t}
                        categoryName={categoryNameMap.get(t.category)}
                        context={context}
                        launchUrl={pickUrl(t)}
                        onDetail={openDetail}
                        onEmbed={onEmbed}
                        style={{ animationDelay: `${Math.min(i * 12, 160)}ms` }}
                      />
                    ))}
                  </motion.div>
                </section>
              );
            })}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}

function EmptyState({
  onReset,
  query,
  hasCategoryFilter,
}: {
  onReset: () => void;
  query: string;
  hasCategoryFilter: boolean;
}): React.ReactElement {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-card/40 px-6 py-16">
      <Search className="h-6 w-6 text-muted-foreground/60" aria-hidden />
      <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
        no tools match the current filter
      </p>
      {query || hasCategoryFilter ? (
        <div className="flex flex-wrap items-center justify-center gap-2 text-[11.5px] text-muted-foreground">
          {query ? (
            <code className="rounded border border-border bg-muted/40 px-1.5 py-0.5">
              q = &ldquo;{query}&rdquo;
            </code>
          ) : null}
          {hasCategoryFilter ? (
            <span className="font-mono text-[10.5px] uppercase tracking-wider">
              · category filter active
            </span>
          ) : null}
          <Button
            variant="outline"
            size="sm"
            onClick={onReset}
            className="ml-2 h-7 gap-1 px-2 text-[11px]"
          >
            <X className="h-3 w-3" />
            Clear
          </Button>
        </div>
      ) : (
        <p className="text-[11.5px] text-muted-foreground">
          Backend returned no tools. Check <code>/api/v1/portal/tools</code>.
        </p>
      )}
    </div>
  );
}
