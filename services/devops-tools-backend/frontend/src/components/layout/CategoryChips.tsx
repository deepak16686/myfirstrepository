/**
 * CategoryChips — horizontal multi-select chip row for filtering the tool
 * grid by category. Lives below the stats strip at the top of the dense
 * dashboard.
 *
 * Behaviour:
 *   - Click a chip to toggle that category on/off.
 *   - "All" chip is a separate fast-path that clears the multi-select.
 *   - Each chip shows (category name · count-of-tools-in-category · healthy-in-category)
 *     so operators can see at a glance which categories have active
 *     incidents.
 *   - Category chips animate an underline via framer-motion `layoutId` when
 *     the selection changes — subtle, but it makes the filter feel like a
 *     real instrument.
 *   - Chips are keyboard-accessible (Enter / Space to toggle).
 *   - Horizontally scrollable on narrow viewports without wrapping; the
 *     scrollbar is styled by `index.css` to be nearly invisible.
 */
import { memo, useMemo } from 'react';
import { motion } from 'motion/react';
import type { Category, CategoryId, Tool } from '@/types/tool';
import { categoryIcons } from '@/lib/icons';
import { useFilterStore } from '@/stores/useFilterStore';
import { cn } from '@/lib/utils';
import { Boxes, Sparkles } from 'lucide-react';

interface CategoryChipsProps {
  tools: Tool[];
  categories: Category[];
}

interface Stat {
  total: number;
  healthy: number;
  degraded: number;
  down: number;
}

function _CategoryChips({ tools, categories }: CategoryChipsProps): React.ReactElement {
  const selectedCategories = useFilterStore((s) => s.selectedCategories);
  const toggleCategory = useFilterStore((s) => s.toggleCategory);
  const setCategories = useFilterStore((s) => s.setCategories);

  const statsByCategory = useMemo<Map<CategoryId, Stat>>(() => {
    const m = new Map<CategoryId, Stat>();
    tools.forEach((t) => {
      const cur = m.get(t.category) ?? { total: 0, healthy: 0, degraded: 0, down: 0 };
      cur.total += 1;
      const s = t.health_status ?? 'unknown';
      if (s === 'healthy') cur.healthy += 1;
      if (s === 'degraded') cur.degraded += 1;
      if (s === 'down') cur.down += 1;
      m.set(t.category, cur);
    });
    return m;
  }, [tools]);

  const sorted = useMemo(
    () =>
      [...categories]
        .filter((c) => (statsByCategory.get(c.id)?.total ?? 0) > 0)
        .sort((a, b) => a.order - b.order),
    [categories, statsByCategory],
  );

  const allSelected = selectedCategories.size === 0;

  return (
    <div
      role="toolbar"
      aria-label="Filter by category"
      className="no-scrollbar -mx-1 flex items-center gap-1.5 overflow-x-auto px-1 py-1"
    >
      {/* "All" chip */}
      <button
        type="button"
        onClick={() => setCategories([])}
        className={cn(
          'relative inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1',
          'font-mono text-[10.5px] uppercase tracking-wider transition-colors',
          allSelected
            ? 'border-ring/40 bg-[color-mix(in_oklch,var(--accent-signal)_12%,var(--card))] text-foreground'
            : 'border-border text-muted-foreground hover:text-foreground',
        )}
        aria-pressed={allSelected}
      >
        <Sparkles className="h-3 w-3" aria-hidden />
        <span>All</span>
        <span className="rounded-sm border border-border/70 bg-background/60 px-1 text-[9.5px]">
          {tools.length}
        </span>
        {allSelected ? (
          <motion.span
            layoutId="cat-chip-underline"
            className="absolute inset-0 -z-10 rounded-full border border-ring/50"
            transition={{ type: 'spring', stiffness: 320, damping: 26 }}
          />
        ) : null}
      </button>

      {sorted.map((c) => {
        const I = categoryIcons[c.id] ?? Boxes;
        const stat = statsByCategory.get(c.id) ?? {
          total: 0,
          healthy: 0,
          degraded: 0,
          down: 0,
        };
        const active = selectedCategories.has(c.id);
        const hasFailing = stat.down > 0;
        return (
          <button
            key={c.id}
            type="button"
            onClick={() => toggleCategory(c.id)}
            className={cn(
              'relative inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1',
              'font-mono text-[10.5px] uppercase tracking-wider transition-colors',
              active
                ? 'border-ring/40 bg-[color-mix(in_oklch,var(--accent-signal)_12%,var(--card))] text-foreground'
                : 'border-border text-muted-foreground hover:text-foreground',
              hasFailing &&
                'shadow-[inset_0_0_0_1px_color-mix(in_oklch,var(--destructive)_22%,transparent)]',
            )}
            aria-pressed={active}
            title={`${c.name}: ${stat.healthy}/${stat.total} healthy`}
          >
            <I className="h-3 w-3" aria-hidden />
            <span>{c.name}</span>
            <span
              className={cn(
                'rounded-sm border px-1 text-[9.5px]',
                hasFailing
                  ? 'border-[color-mix(in_oklch,var(--destructive)_40%,var(--border))] bg-[color-mix(in_oklch,var(--destructive)_14%,transparent)] text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))]'
                  : 'border-border/70 bg-background/60',
              )}
            >
              {stat.healthy}/{stat.total}
            </span>
            {active ? (
              <motion.span
                layoutId={`cat-chip-active-${c.id}`}
                className="absolute inset-0 -z-10 rounded-full border border-ring/50"
                transition={{ type: 'spring', stiffness: 320, damping: 26 }}
              />
            ) : null}
          </button>
        );
      })}
    </div>
  );
}

export const CategoryChips = memo(_CategoryChips);
