/* Sticky, blur-backed filter row for the Tools page.
 * View tabs (Grid / Table / Compact) animate an underline via layoutId. */
import { motion } from 'motion/react';
import { LayoutGrid, Rows3, List, Search, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { SavedViewKey, ToolsViewMode } from '@/store/ui';
import { useUiStore } from '@/store/ui';
import { Button } from '@/components/ui/button';

interface FilterBarProps {
  query: string;
  setQuery: (q: string) => void;
  visibleCount: number;
  totalCount: number;
}

const VIEWS: { key: ToolsViewMode; label: string; icon: typeof LayoutGrid }[] = [
  { key: 'grid', label: 'Grid', icon: LayoutGrid },
  { key: 'table', label: 'Table', icon: Rows3 },
  { key: 'compact', label: 'Compact', icon: List },
];

const SAVED: { key: SavedViewKey; label: string }[] = [
  { key: 'all', label: 'All tools' },
  { key: 'ai', label: 'AI' },
  { key: 'cicd', label: 'CI-CD' },
  { key: 'down', label: 'Down now' },
];

export function ToolsFilterBar({
  query,
  setQuery,
  visibleCount,
  totalCount,
}: FilterBarProps): React.ReactElement {
  const view = useUiStore((s) => s.toolsView);
  const setView = useUiStore((s) => s.setToolsView);
  const saved = useUiStore((s) => s.savedView);
  const setSaved = useUiStore((s) => s.setSavedView);

  return (
    <div
      className={cn(
        'sticky top-14 z-20 -mx-4 mb-4 border-b border-border/60 px-4 py-3 sm:-mx-8 sm:px-8',
        'glass'
      )}
    >
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 rounded-md border border-border bg-card/70 p-0.5">
            {VIEWS.map((v) => {
              const I = v.icon;
              const active = view === v.key;
              return (
                <button
                  key={v.key}
                  type="button"
                  onClick={() => setView(v.key)}
                  className={cn(
                    'relative flex items-center gap-1.5 rounded px-2.5 py-1 font-mono text-[11px] uppercase tracking-wider transition-colors',
                    active ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
                  )}
                  aria-pressed={active}
                >
                  <I className="h-3.5 w-3.5" />
                  {v.label}
                  {active ? (
                    <motion.span
                      layoutId="tools-view-underline"
                      className="absolute inset-0 -z-10 rounded bg-muted/80 shadow-[inset_0_0_0_1px_color-mix(in_oklch,var(--ring)_30%,transparent)]"
                      transition={{ type: 'spring', stiffness: 320, damping: 28 }}
                    />
                  ) : null}
                </button>
              );
            })}
          </div>

          <span className="hidden text-[11px] font-mono text-muted-foreground md:inline">
            showing <span className="text-foreground/80">{visibleCount}</span> of {totalCount}
          </span>
        </div>

        <div className="flex min-w-0 flex-1 items-center gap-2 md:max-w-[560px]">
          <label className="relative flex h-9 w-full items-center gap-2 rounded-md border border-border bg-muted/40 px-3 transition-colors focus-within:border-ring focus-within:bg-card">
            <Search className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search name, id, tag, category…"
              aria-label="Filter tools"
              className="h-full w-full bg-transparent text-sm outline-hidden placeholder:text-muted-foreground/80"
            />
            {query ? (
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="Clear search"
                onClick={() => setQuery('')}
              >
                <X className="h-3 w-3" />
              </Button>
            ) : null}
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-1">
          {SAVED.map((s) => {
            const active = saved === s.key;
            return (
              <button
                key={s.key}
                type="button"
                onClick={() => setSaved(s.key)}
                className={cn(
                  'relative rounded-full border px-2.5 py-1 font-mono text-[10.5px] uppercase tracking-wider transition-colors',
                  active
                    ? 'border-ring/50 bg-[color-mix(in_oklch,var(--accent-signal)_10%,var(--card))] text-foreground'
                    : 'border-border text-muted-foreground hover:text-foreground'
                )}
                aria-pressed={active}
              >
                {s.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
