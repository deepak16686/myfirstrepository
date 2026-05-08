import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ColumnDef } from '@tanstack/react-table';
import { ExternalLink, GitPullRequestArrow } from 'lucide-react';
import { PageHeader } from '@/components/common/PageHeader';
import { DataTable } from '@/components/ui/data-table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { fetchPipelines } from '@/lib/api';
import type { PipelineRun } from '@/types/tool';
import { timeAgo } from '@/lib/utils';

function StatusBadge({ status }: { status: string }): React.ReactElement {
  const s = status.toLowerCase();
  const variant: 'success' | 'warning' | 'danger' | 'info' | 'outline' =
    s === 'success' || s === 'passed'
      ? 'success'
      : s === 'failed' || s === 'canceled'
        ? 'danger'
        : s === 'running' || s === 'pending'
          ? 'warning'
          : s === 'manual'
            ? 'info'
            : 'outline';
  return <Badge variant={variant}>{status.toUpperCase()}</Badge>;
}

export function Pipelines(): React.ReactElement {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['pipelines'],
    queryFn: fetchPipelines,
    staleTime: 30_000,
    refetchInterval: 45_000,
  });

  const columns = useMemo<ColumnDef<PipelineRun>[]>(
    () => [
      {
        accessorKey: 'id',
        header: 'Pipeline',
        cell: ({ row }) => (
          <div className="flex min-w-0 flex-col">
            <span className="font-mono text-[12px]">#{row.original.id}</span>
            {row.original.project_name ? (
              <span className="truncate text-[11px] text-muted-foreground">
                {row.original.project_name}
              </span>
            ) : null}
          </div>
        ),
      },
      {
        accessorKey: 'status',
        header: 'Status',
        cell: ({ row }) => <StatusBadge status={row.original.status} />,
      },
      {
        accessorKey: 'ref',
        header: 'Ref',
        cell: ({ row }) => (
          <span className="font-mono text-[12px] text-muted-foreground">
            {row.original.ref ?? '—'}
          </span>
        ),
      },
      {
        accessorKey: 'sha',
        header: 'SHA',
        cell: ({ row }) =>
          row.original.sha ? (
            <span className="font-mono text-[12px] text-muted-foreground">
              {row.original.sha.slice(0, 10)}
            </span>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        accessorKey: 'duration',
        header: 'Duration',
        cell: ({ row }) =>
          row.original.duration != null ? (
            <span className="font-mono text-[12px] tabular-nums">
              {Math.round(row.original.duration)}s
            </span>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      },
      {
        accessorKey: 'updated_at',
        header: 'Updated',
        cell: ({ row }) => (
          <span className="font-mono text-[12px] text-muted-foreground">
            {timeAgo(row.original.updated_at)}
          </span>
        ),
      },
      {
        id: 'actions',
        header: '',
        enableSorting: false,
        cell: ({ row }) =>
          row.original.web_url ? (
            <Button variant="ghost" size="icon-sm" asChild aria-label="Open in GitLab">
              <a href={row.original.web_url} target="_blank" rel="noreferrer">
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </Button>
          ) : null,
      },
    ],
    []
  );

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="CI/CD"
        title="Recent pipelines"
        description="Live view of the last GitLab CI runs across all configured projects. Click a row to open it in GitLab."
      />

      {isError ? (
        <Card className="border-destructive/40 bg-destructive/5 p-4 text-sm">
          <p className="font-semibold">Unable to reach the GitLab backend</p>
          <p className="mt-1 text-muted-foreground">
            The portal tried <code className="font-mono">/api/v1/gitlab/pipelines</code> and the
            request failed. Verify that the backend is up and the GitLab integration is configured.
          </p>
        </Card>
      ) : null}

      <DataTable<PipelineRun, unknown>
        columns={columns}
        data={data ?? []}
        loading={isLoading}
        emptyLabel={
          <div className="flex flex-col items-center gap-2 py-4">
            <GitPullRequestArrow className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm font-medium">No pipelines yet</p>
            <p className="text-xs text-muted-foreground">
              When GitLab returns data from <code className="font-mono">/api/v1/gitlab/pipelines</code>
              , runs will appear here.
            </p>
          </div>
        }
      />
    </div>
  );
}
