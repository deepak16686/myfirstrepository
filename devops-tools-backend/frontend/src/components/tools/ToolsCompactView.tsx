/* Dense two-line list + xs sparkline. Optimised for the "show me as many
 * tools as possible on one screen" scan pattern. */
import { memo } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ExternalLink, Info, Monitor } from 'lucide-react';
import type { HealthStatus, Tool } from '@/types/tool';
import { Button } from '@/components/ui/button';
import { HealthDot } from './HealthDot';
import { HealthSparkline } from './HealthSparkline';
import { resolveIcon } from '@/lib/icons';
import { statusMeta } from '@/lib/status';
import { cn, formatLatency, timeAgo } from '@/lib/utils';
import { launchTool } from '@/lib/api';
import { useUiStore } from '@/store/ui';

interface ToolsCompactViewProps {
  tools: Tool[];
}

function _ToolsCompactView({ tools }: ToolsCompactViewProps): React.ReactElement {
  const openDetail = useUiStore((s) => s.openDetail);
  const navigate = useNavigate();

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

  if (tools.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-muted/20 px-6 py-16 text-center">
        <p className="mono-caps text-muted-foreground">no tools match these filters</p>
      </div>
    );
  }

  return (
    <ul className="divide-y divide-border/60 overflow-hidden rounded-lg border border-border bg-card/60">
      {tools.map((t) => {
        const Icon = resolveIcon(t.icon);
        const status = (t.health_status ?? 'unknown') as HealthStatus;
        const meta = statusMeta(status);
        return (
          <li
            key={t.id}
            className="group flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-muted/25 focus-within:bg-muted/25"
          >
            <button
              type="button"
              onClick={() => openDetail(t.id)}
              className="flex min-w-0 flex-1 items-center gap-3 text-left outline-none"
              aria-label={`Detail for ${t.name}`}
            >
              <HealthDot status={status} size="sm" />
              <span className="flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-muted/50">
                <Icon className="h-3.5 w-3.5" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <p className="truncate text-[13px] font-medium leading-tight">{t.name}</p>
                  <span className="truncate font-mono text-[10.5px] uppercase tracking-wider text-muted-foreground">
                    {t.category} · {t.id}
                  </span>
                </div>
                <p className="mt-0.5 flex items-center gap-2 font-mono text-[10.5px] text-muted-foreground">
                  <span className={cn(meta.text)}>{meta.shortLabel}</span>
                  <span className="opacity-60">·</span>
                  <span>{formatLatency(t.latency_ms, t.last_checked)} rtt</span>
                  <span className="opacity-60">·</span>
                  <span>last probe {timeAgo(t.last_checked)}</span>
                </p>
              </div>
            </button>

            <div className="hidden w-[140px] shrink-0 md:block">
              <HealthSparkline toolId={t.id} status={status} size="xs" />
            </div>

            <div className="flex shrink-0 items-center gap-1">
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
                onClick={() => onLaunch(t)}
                disabled={!t.url_external}
              >
                Launch
                <ExternalLink className="h-3 w-3" />
              </Button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export const ToolsCompactView = memo(_ToolsCompactView);
