/* Tool card — hover lift, signal hairline, conic sheen on hover, layout-stable
 * across filter transitions, keyboard-operable, reveals tags on hover. */
import { memo } from 'react';
import { ExternalLink, FileText, Globe, Monitor, Info } from 'lucide-react';
import { motion } from 'motion/react';
import type { HealthStatus, Tool } from '@/types/tool';
import { resolveIcon } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { HealthDot } from './HealthDot';
import { cn, formatLatency } from '@/lib/utils';
import { statusMeta } from '@/lib/status';
import { resolveCurrentLaunchUrl } from '@/lib/launch';

interface ToolCardProps {
  tool: Tool;
  categoryName?: string;
  onDetail: (id: string) => void;
  onLaunch: (tool: Tool) => void;
  onEmbed: (tool: Tool) => void;
  style?: React.CSSProperties;
}

function _ToolCard({
  tool,
  categoryName,
  onDetail,
  onLaunch,
  onEmbed,
  style,
}: ToolCardProps): React.ReactElement {
  const Icon = resolveIcon(tool.icon);
  const status: HealthStatus = tool.health_status ?? 'unknown';
  const meta = statusMeta(status);
  const latency = formatLatency(tool.latency_ms, tool.last_checked);

  const accentEdge =
    status === 'healthy'
      ? 'before:bg-[var(--success)]'
      : status === 'degraded'
        ? 'before:bg-[var(--warning)]'
        : status === 'down'
          ? 'before:bg-[var(--destructive)]'
          : 'before:bg-muted-foreground/40';

  return (
    <motion.div
      layout="position"
      layoutId={`tool-card-${tool.id}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4, scale: 0.98 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ y: -2, scale: 1.005 }}
      style={style}
    >
      <Card
        className={cn(
          'group relative isolate flex h-full min-h-[180px] flex-col overflow-hidden',
          'card-sheen signal-border',
          'cursor-pointer transition-[border-color,box-shadow] duration-200',
          'hover:border-ring/60 hover:shadow-[0_0_0_1px_color-mix(in_oklch,var(--ring)_25%,transparent),0_12px_32px_-14px_color-mix(in_oklch,var(--accent-signal)_25%,transparent)]',
          'before:pointer-events-none before:absolute before:inset-y-0 before:left-0 before:w-[3px] before:opacity-85',
          accentEdge
        )}
        onClick={() => onDetail(tool.id)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onDetail(tool.id);
          }
        }}
        tabIndex={0}
        role="button"
        aria-label={`${tool.name} — ${meta.label}. Open detail.`}
      >
        {/* Header row */}
        <div className="flex items-start justify-between gap-3 p-5 pb-2.5">
          <div className="flex min-w-0 items-start gap-3">
            <div
              className={cn(
                'flex size-9 shrink-0 items-center justify-center rounded-md',
                'border border-border bg-muted/60 text-foreground',
                'transition-colors group-hover:bg-accent group-hover:text-accent-foreground',
                'shadow-[inset_0_0_0_1px_color-mix(in_oklch,var(--border)_80%,transparent)]'
              )}
            >
              <Icon className="h-[18px] w-[18px]" />
            </div>
            <div className="min-w-0 pt-0.5">
              <h3 className="truncate text-[15px] font-semibold leading-tight tracking-tight">
                {tool.name}
              </h3>
              <div className="mt-1 flex items-center gap-2 text-[11px] font-medium text-muted-foreground">
                <span className="uppercase tracking-wider">{categoryName ?? tool.category}</span>
                <span className="inline-block size-1 rounded-full bg-border" aria-hidden />
                <span className="font-mono">{tool.id}</span>
                {tool.url_funnel ? (
                  <span
                    className={cn(
                      'ml-1 inline-flex items-center gap-1 rounded-full border px-1.5 py-px',
                      'border-[color-mix(in_oklch,var(--success)_25%,var(--border))]',
                      'bg-[color-mix(in_oklch,var(--success)_10%,transparent)]',
                      'text-[9.5px] uppercase tracking-wider',
                      'text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))]',
                    )}
                    title="Publicly reachable via Tailscale Funnel"
                    aria-label="Publicly reachable"
                  >
                    <Globe className="h-2.5 w-2.5" aria-hidden />
                    Public
                  </span>
                ) : null}
              </div>
            </div>
          </div>

          <div className="flex shrink-0 flex-col items-end gap-1">
            <HealthDot status={status} size="md" />
            <span className={cn('mono-caps', meta.text)}>{meta.shortLabel}</span>
          </div>
        </div>

        {/* Description */}
        <p className="line-clamp-2 flex-1 px-5 text-[13px] leading-relaxed text-muted-foreground">
          {tool.description}
        </p>

        {/* Tags — hidden by default, visible on hover */}
        <div
          className={cn(
            'flex flex-wrap gap-1 px-5 pt-3 text-[10px]',
            'max-h-0 opacity-0 transition-[max-height,opacity] duration-300',
            'group-hover:max-h-16 group-hover:opacity-100 group-focus-within:max-h-16 group-focus-within:opacity-100'
          )}
          aria-hidden
        >
          {tool.tags.slice(0, 4).map((t) => (
            <span
              key={t}
              className="rounded border border-border bg-muted/40 px-1.5 py-0.5 font-mono lowercase text-muted-foreground"
            >
              #{t}
            </span>
          ))}
        </div>

        {/* Actions */}
        <div className="mt-3 flex items-center justify-between gap-2 border-t border-border/70 bg-muted/20 px-4 py-2.5">
          <span className="font-mono text-[11px] text-muted-foreground">
            {tool.latency_ms != null ? (
              <>
                <span className="text-foreground/80">{latency}</span>
                <span className="ml-1 text-muted-foreground">rtt</span>
              </>
            ) : (
              'awaiting probe'
            )}
          </span>
          <div className="flex items-center gap-1">
            {tool.embed ? (
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`Embed ${tool.name}`}
                title="Embed in portal"
                onClick={(e) => {
                  e.stopPropagation();
                  onEmbed(tool);
                }}
              >
                <Monitor className="h-3.5 w-3.5" />
              </Button>
            ) : null}
            {tool.docs_url ? (
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={`${tool.name} docs`}
                title="Open docs"
                asChild
              >
                <a
                  href={tool.docs_url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}
                >
                  <FileText className="h-3.5 w-3.5" />
                </a>
              </Button>
            ) : null}
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={`Info for ${tool.name}`}
              title="Details"
              onClick={(e) => {
                e.stopPropagation();
                onDetail(tool.id);
              }}
            >
              <Info className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="signal"
              size="sm"
              className="h-7 gap-1.5 px-2.5 font-mono text-[11px] uppercase tracking-wider"
              aria-label={`Launch ${tool.name}`}
              onClick={(e) => {
                e.stopPropagation();
                onLaunch(tool);
              }}
              disabled={!resolveCurrentLaunchUrl(tool)}
            >
              Launch
              <ExternalLink className="h-3 w-3" />
            </Button>
          </div>
        </div>
      </Card>
    </motion.div>
  );
}

export const ToolCard = memo(_ToolCard);
