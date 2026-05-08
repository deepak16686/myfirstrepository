import { useMemo } from 'react';
import { AnimatePresence } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import type { Category, HealthStatus, Tool } from '@/types/tool';
import { ToolCard } from './ToolCard';
import { useUiStore } from '@/store/ui';
import { openToolLaunch, resolveCurrentLaunchUrl } from '@/lib/launch';
import { Skeleton } from '@/components/ui/skeleton';
import { Search } from 'lucide-react';

interface ToolGridProps {
  tools: Tool[] | undefined;
  categories: Category[] | undefined;
  loading?: boolean;
  query?: string;
  categoryFilter?: Set<string>;
  healthFilter?: Set<HealthStatus>;
}

export function ToolGrid({
  tools,
  categories,
  loading,
  query,
  categoryFilter,
  healthFilter,
}: ToolGridProps): React.ReactElement {
  const openDetail = useUiStore((s) => s.openDetail);
  const navigate = useNavigate();

  const categoryNameMap = useMemo(() => {
    const m = new Map<string, string>();
    (categories ?? []).forEach((c) => m.set(c.id, c.name));
    return m;
  }, [categories]);

  const filtered = useMemo(() => {
    if (!tools) return [] as Tool[];
    const q = (query ?? '').trim().toLowerCase();
    return tools.filter((t) => {
      if (categoryFilter && categoryFilter.size > 0 && !categoryFilter.has(t.category)) return false;
      if (healthFilter && healthFilter.size > 0) {
        const s = (t.health_status ?? 'unknown') as HealthStatus;
        if (!healthFilter.has(s)) return false;
      }
      if (!q) return true;
      const hay = [t.name, t.id, t.description, t.category, ...(t.tags ?? [])]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return hay.includes(q);
    });
  }, [tools, query, categoryFilter, healthFilter]);

  const onLaunch = async (tool: Tool): Promise<void> => {
    if (!resolveCurrentLaunchUrl(tool)) {
      toast.error('No launch URL configured for this tool.');
      return;
    }
    await openToolLaunch(tool);
  };

  const onEmbed = (tool: Tool): void => {
    if (!tool.embed) {
      toast.error(`${tool.name} cannot be embedded; opening externally.`);
      onLaunch(tool);
      return;
    }
    navigate(`/embed/${tool.id}`);
  };

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-[172px] rounded-lg" />
        ))}
      </div>
    );
  }

  if (filtered.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-muted/20 px-6 py-16 text-center">
        <div className="mb-3 flex size-12 items-center justify-center rounded-full border border-border bg-background">
          <Search className="h-5 w-5 text-muted-foreground" />
        </div>
        <h3 className="text-base font-semibold">No tools match these filters</h3>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          Try a different search term, clear the category or health filters, or press{' '}
          <kbd className="mx-0.5 rounded border border-border bg-background px-1.5 py-0.5 font-mono text-[10px]">
            /
          </kbd>{' '}
          to focus search again.
        </p>
      </div>
    );
  }

  return (
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
  );
}
