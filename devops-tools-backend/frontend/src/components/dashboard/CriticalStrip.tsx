import { AlertOctagon } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import type { Tool } from '@/types/tool';
import { resolveIcon } from '@/lib/icons';
import { HealthDot } from '@/components/tools/HealthDot';
import { useUiStore } from '@/store/ui';
import { openToolLaunch, resolveCurrentLaunchUrl } from '@/lib/launch';
import { ScrollArea } from '@/components/ui/scroll-area';
import { formatLatency, timeAgo } from '@/lib/utils';

interface CriticalStripProps {
  tools: Tool[];
}

export function CriticalStrip({ tools }: CriticalStripProps): React.ReactElement {
  const navigate = useNavigate();
  const openDetail = useUiStore((s) => s.openDetail);

  if (tools.length === 0) {
    return (
      <Card className="relative overflow-hidden p-5">
        <div className="flex items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-md bg-[color-mix(in_oklch,var(--success)_12%,transparent)] text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))]">
            <HealthDot status="healthy" pulse size="md" />
          </div>
          <div>
            <p className="font-semibold">All systems nominal</p>
            <p className="text-sm text-muted-foreground">
              Every registered tool is responding healthily. Last refresh moments ago.
            </p>
          </div>
        </div>
      </Card>
    );
  }

  const launch = async (t: Tool): Promise<void> => {
    if (!resolveCurrentLaunchUrl(t)) {
      toast.error('No launch URL configured.');
      return;
    }
    await openToolLaunch(t);
  };

  return (
    <Card className="relative overflow-hidden">
      <div className="flex items-center justify-between border-b border-border bg-muted/20 px-5 py-3">
        <div className="flex items-center gap-2">
          <AlertOctagon className="h-4 w-4 text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))]" />
          <p className="text-sm font-semibold">Critical tools</p>
          <span className="font-mono text-[11px] text-muted-foreground">
            · {tools.length} requiring attention
          </span>
        </div>
        <Button variant="ghost" size="sm" onClick={() => navigate('/tools?health=down')}>
          View all
        </Button>
      </div>
      <ScrollArea className="max-h-[240px]">
        <div className="divide-y divide-border">
          {tools.map((t) => {
            const Icon = resolveIcon(t.icon);
            return (
              <div
                key={t.id}
                className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-muted/20"
              >
                <div className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-background">
                  <Icon className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-sm font-semibold">{t.name}</p>
                    <HealthDot status={t.health_status ?? 'unknown'} size="sm" />
                  </div>
                  <p className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground">
                    {t.container_name ?? t.id} · last seen {timeAgo(t.last_checked)} ·{' '}
                    {formatLatency(t.latency_ms)}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <Button variant="ghost" size="sm" onClick={() => openDetail(t.id)}>
                    Details
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => launch(t)}>
                    Retry
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </ScrollArea>
    </Card>
  );
}
