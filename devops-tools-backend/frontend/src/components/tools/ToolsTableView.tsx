/* Virtualised Tools table (TanStack Table + @tanstack/react-virtual).
 * Engages the virtualizer only when row count > 25 — otherwise a normal
 * DOM render is cheaper and lets built-in scroll momentum work. */
import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import { toast } from 'sonner';
import { ArrowDown, ArrowUp, ArrowUpDown, ExternalLink, Info, Monitor } from 'lucide-react';
import type { Category, HealthStatus, Tool } from '@/types/tool';
import { Button } from '@/components/ui/button';
import { HealthDot } from './HealthDot';
import { resolveIcon } from '@/lib/icons';
import { statusMeta } from '@/lib/status';
import { cn, formatLatency, timeAgo } from '@/lib/utils';
import { openToolLaunch, resolveCurrentLaunchUrl } from '@/lib/launch';
import { useUiStore } from '@/store/ui';

interface ToolsTableViewProps {
  tools: Tool[];
  categories: Category[] | undefined;
}

function SortHeader({
  label,
  order,
  onClick,
  align = 'left',
}: {
  label: string;
  order: 'asc' | 'desc' | false;
  onClick: () => void;
  align?: 'left' | 'right';
}): React.ReactElement {
  const Icon = order === 'asc' ? ArrowUp : order === 'desc' ? ArrowDown : ArrowUpDown;
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'group inline-flex items-center gap-1.5 text-muted-foreground transition-colors hover:text-foreground',
        align === 'right' && 'flex-row-reverse'
      )}
    >
      <span className="mono-caps">{label}</span>
      <Icon className={cn('h-3 w-3 transition-opacity', order === false && 'opacity-40')} />
    </button>
  );
}

export function ToolsTableView({
  tools,
  categories,
}: ToolsTableViewProps): React.ReactElement {
  const openDetail = useUiStore((s) => s.openDetail);
  const navigate = useNavigate();

  const [sorting, setSorting] = useState<SortingState>([{ id: 'name', desc: false }]);

  const categoryNameMap = useMemo(() => {
    const m = new Map<string, string>();
    (categories ?? []).forEach((c) => m.set(c.id, c.name));
    return m;
  }, [categories]);

  const columns = useMemo<ColumnDef<Tool>[]>(
    () => [
      {
        id: 'status',
        header: () => <span className="mono-caps text-muted-foreground">Status</span>,
        size: 110,
        cell: ({ row }) => {
          const s = (row.original.health_status ?? 'unknown') as HealthStatus;
          const meta = statusMeta(s);
          return (
            <div className="flex items-center gap-2">
              <HealthDot status={s} size="sm" pulse={false} />
              <span className={cn('mono-caps', meta.text)}>{meta.shortLabel}</span>
            </div>
          );
        },
        accessorFn: (t) => t.health_status ?? 'unknown',
        sortingFn: (a, b, columnId) => {
          const order: HealthStatus[] = ['down', 'degraded', 'unknown', 'healthy'];
          return (
            order.indexOf(a.getValue(columnId) as HealthStatus) -
            order.indexOf(b.getValue(columnId) as HealthStatus)
          );
        },
      },
      {
        id: 'name',
        header: () => <span className="mono-caps text-muted-foreground">Tool</span>,
        accessorFn: (t) => t.name,
        cell: ({ row }) => {
          const t = row.original;
          const Icon = resolveIcon(t.icon);
          return (
            <div className="flex min-w-0 items-center gap-2.5">
              <span className="flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-muted/50">
                <Icon className="h-3.5 w-3.5" />
              </span>
              <div className="min-w-0">
                <p className="truncate text-[13px] font-medium leading-tight">{t.name}</p>
                <p className="truncate font-mono text-[10.5px] uppercase tracking-wider text-muted-foreground">
                  {t.id}
                </p>
              </div>
            </div>
          );
        },
      },
      {
        id: 'category',
        header: () => <span className="mono-caps text-muted-foreground">Category</span>,
        accessorFn: (t) => t.category,
        size: 140,
        cell: ({ getValue }) => {
          const id = String(getValue());
          return (
            <span className="font-mono text-[12px] uppercase tracking-wider text-muted-foreground">
              {categoryNameMap.get(id) ?? id}
            </span>
          );
        },
      },
      {
        id: 'latency',
        header: () => <span className="mono-caps text-right text-muted-foreground">Latency</span>,
        accessorFn: (t) => t.latency_ms ?? -1,
        size: 90,
        cell: ({ row }) => (
          <span className="font-mono text-[12px] tabular-nums">
            {formatLatency(row.original.latency_ms, row.original.last_checked)}
          </span>
        ),
      },
      {
        id: 'last_checked',
        header: () => <span className="mono-caps text-muted-foreground">Last probe</span>,
        accessorFn: (t) =>
          t.last_checked ? new Date(t.last_checked).getTime() : 0,
        size: 110,
        cell: ({ row }) => (
          <span className="font-mono text-[11px] text-muted-foreground">
            {timeAgo(row.original.last_checked)}
          </span>
        ),
      },
      {
        id: 'container',
        header: () => <span className="mono-caps text-muted-foreground">Container</span>,
        accessorFn: (t) => t.container_name ?? '',
        size: 160,
        cell: ({ getValue }) => (
          <span className="truncate font-mono text-[11px] text-muted-foreground">
            {(getValue() as string) || '—'}
          </span>
        ),
      },
      {
        id: 'actions',
        header: () => <span className="mono-caps text-right text-muted-foreground">Actions</span>,
        size: 200,
        enableSorting: false,
        cell: ({ row }) => {
          const t = row.original;
          const launch = async (): Promise<void> => {
            if (!resolveCurrentLaunchUrl(t)) {
              toast.error('No launch URL configured');
              return;
            }
            await openToolLaunch(t);
          };
          return (
            <div className="flex items-center justify-end gap-1">
              {t.embed ? (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Embed ${t.name}`}
                  onClick={() => navigate(`/embed/${t.id}`)}
                >
                  <Monitor className="h-3.5 w-3.5" />
                </Button>
              ) : null}
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Detail for ${t.name}`}
                onClick={() => openDetail(t.id)}
              >
                <Info className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="signal"
                size="sm"
                className="h-7 gap-1.5 px-2.5 font-mono text-[11px] uppercase tracking-wider"
                onClick={launch}
                disabled={!resolveCurrentLaunchUrl(t)}
              >
                Launch
                <ExternalLink className="h-3 w-3" />
              </Button>
            </div>
          );
        },
      },
    ],
    [categoryNameMap, navigate, openDetail]
  );

  const table = useReactTable({
    data: tools,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const rows = table.getRowModel().rows;
  const useVirtual = rows.length > 25;
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 52,
    overscan: 8,
    enabled: useVirtual,
  });

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card/60">
      {/* Header (mono caps) */}
      <div
        className="grid border-b border-border bg-muted/30 px-4 py-2.5 text-[11px]"
        style={{ gridTemplateColumns: '110px 1fr 140px 90px 110px 160px 200px' }}
      >
        {table.getHeaderGroups()[0].headers.map((h) => {
          const sortable = h.column.getCanSort();
          const order = h.column.getIsSorted();
          return (
            <div key={h.id} className="flex items-center">
              {sortable ? (
                <SortHeader
                  label={
                    typeof h.column.columnDef.header === 'string'
                      ? String(h.column.columnDef.header)
                      : (h.id === 'latency' ? 'Latency' : h.id.replace(/_/g, ' ')).toUpperCase()
                  }
                  order={order as 'asc' | 'desc' | false}
                  onClick={() => h.column.toggleSorting()}
                  align={h.id === 'latency' || h.id === 'actions' ? 'right' : 'left'}
                />
              ) : (
                flexRender(h.column.columnDef.header, h.getContext())
              )}
            </div>
          );
        })}
      </div>

      {/* Body */}
      <div
        ref={parentRef}
        className="max-h-[70vh] overflow-y-auto"
        role="grid"
        aria-rowcount={rows.length}
      >
        {useVirtual ? (
          <div
            style={{
              height: `${virtualizer.getTotalSize()}px`,
              width: '100%',
              position: 'relative',
            }}
          >
            {virtualizer.getVirtualItems().map((vi) => {
              const row = rows[vi.index];
              return (
                <div
                  key={row.id}
                  className={cn(
                    'absolute left-0 right-0 grid items-center border-b border-border/60 bg-card/40 px-4 py-2.5',
                    'transition-colors hover:bg-muted/30 focus-within:bg-muted/30 cursor-pointer'
                  )}
                  style={{
                    transform: `translateY(${vi.start}px)`,
                    height: `${vi.size}px`,
                    gridTemplateColumns: '110px 1fr 140px 90px 110px 160px 200px',
                  }}
                  onClick={() => openDetail(row.original.id)}
                  role="row"
                >
                  {row.getVisibleCells().map((cell) => (
                    <div key={cell.id} className="min-w-0 pr-3">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        ) : (
          rows.map((row) => (
            <div
              key={row.id}
              className={cn(
                'grid items-center border-b border-border/60 bg-card/40 px-4 py-2.5',
                'transition-colors hover:bg-muted/30 focus-within:bg-muted/30 cursor-pointer'
              )}
              style={{ gridTemplateColumns: '110px 1fr 140px 90px 110px 160px 200px' }}
              onClick={() => openDetail(row.original.id)}
              role="row"
            >
              {row.getVisibleCells().map((cell) => (
                <div key={cell.id} className="min-w-0 pr-3">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </div>
              ))}
            </div>
          ))
        )}

        {rows.length === 0 ? (
          <div className="p-8 text-center">
            <p className="mono-caps text-muted-foreground">no tools match these filters</p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
