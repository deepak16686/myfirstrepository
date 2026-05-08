/**
 * Stub activity feed that synthesizes "events" from the current tool state.
 * When the backend exposes a real event stream, wire this to it.
 */
import { useMemo } from 'react';
import { ArrowUpRight, CheckCircle2, Clock, Sparkles, Terminal } from 'lucide-react';
import type { Tool } from '@/types/tool';
import { Card } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { timeAgo } from '@/lib/utils';

interface ActivityFeedProps {
  tools: Tool[];
}

type Event = {
  id: string;
  title: string;
  detail: string;
  ts: string;
  tone: 'ok' | 'attention' | 'info' | 'event';
};

export function ActivityFeed({ tools }: ActivityFeedProps): React.ReactElement {
  const events: Event[] = useMemo(() => {
    const now = Date.now();
    const recent: Event[] = [];

    // Synthesize an event per tool state transition snapshot.
    tools.slice(0, 8).forEach((t, i) => {
      if (t.health_status === 'down') {
        recent.push({
          id: `down-${t.id}`,
          title: `${t.name} is offline`,
          detail: `Probe failed · container ${t.container_name ?? t.id}`,
          ts: new Date(now - i * 1000 * 60).toISOString(),
          tone: 'attention',
        });
      } else if (t.health_status === 'degraded') {
        recent.push({
          id: `deg-${t.id}`,
          title: `${t.name} latency spike`,
          detail: `Probe returned higher-than-normal latency`,
          ts: new Date(now - i * 1000 * 60).toISOString(),
          tone: 'info',
        });
      } else if (t.health_status === 'healthy') {
        recent.push({
          id: `ok-${t.id}`,
          title: `${t.name} reporting healthy`,
          detail: `Responded to ${t.health?.path ?? 'probe'} successfully`,
          ts: new Date(now - i * 1000 * 60).toISOString(),
          tone: 'ok',
        });
      }
    });

    recent.unshift({
      id: 'evt-boot',
      title: 'Portal warm-started',
      detail: 'Backend loaded 34 tools from config/tools.yaml',
      ts: new Date(now - 1000 * 28).toISOString(),
      tone: 'event',
    });

    return recent.slice(0, 10);
  }, [tools]);

  const toneIcon = {
    ok: { I: CheckCircle2, cls: 'text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))]' },
    attention: {
      I: Terminal,
      cls: 'text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))]',
    },
    info: {
      I: Clock,
      cls: 'text-[color-mix(in_oklch,var(--warning)_92%,var(--foreground))]',
    },
    event: { I: Sparkles, cls: 'text-primary' },
  } as const;

  return (
    <Card className="flex h-full min-h-[320px] flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-2">
          <div className="size-1.5 animate-pulse rounded-full bg-[var(--success)]" />
          <p className="text-sm font-semibold">Activity stream</p>
          <span className="font-mono text-[11px] text-muted-foreground">· synthesised</span>
        </div>
        <a
          href="#"
          onClick={(e) => e.preventDefault()}
          className="inline-flex items-center gap-1 font-mono text-[11px] text-muted-foreground hover:text-foreground"
        >
          see log
          <ArrowUpRight className="h-3 w-3" />
        </a>
      </div>
      <ScrollArea className="flex-1">
        <ul className="divide-y divide-border">
          {events.map((e) => {
            const { I, cls } = toneIcon[e.tone];
            return (
              <li
                key={e.id}
                className="flex items-start gap-3 px-5 py-3 transition-colors hover:bg-muted/20"
              >
                <I className={`mt-0.5 h-4 w-4 ${cls}`} aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{e.title}</p>
                  <p className="truncate font-mono text-[11px] text-muted-foreground">{e.detail}</p>
                </div>
                <time className="shrink-0 font-mono text-[11px] text-muted-foreground">
                  {timeAgo(e.ts)}
                </time>
              </li>
            );
          })}
        </ul>
      </ScrollArea>
    </Card>
  );
}
