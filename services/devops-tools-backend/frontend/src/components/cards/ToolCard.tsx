/**
 * Dense ToolCard — the centerpiece of the portal grid. Constraint: the
 * card MUST stay ≤140px tall so 34 tools fit into roughly two scroll-
 * heights on a 1440p display. Every pixel is budgeted.
 *
 * Layout (top-to-bottom):
 *   row1  icon │ name ················· [health pill] ·· [⋮]
 *         ░░░░ category · container_name
 *   row2  description (line-clamp-2, muted, dense leading)
 *   row3  [🔑 creds]  [📄 docs]  [📺 embed]  ───────  [Launch ↗]
 *
 * Interaction:
 *   - Clicking the card body opens the detail drawer.
 *   - Clicking any icon button stops propagation so the drawer does NOT
 *     open for that action.
 *   - Keyboard: Enter / Space opens the drawer; focusable icon buttons
 *     have their own tab stops.
 *
 * Aesthetic (Mission Control / Flight Deck):
 *   - Thin hairline borders (1px, `signal-border`)
 *   - Tabular numeric latency readout
 *   - Accent edge on the left in the status colour
 *   - `card-sheen` — subtle conic sheen on hover
 *   - mono-caps micro-labels for category / id
 *   - No gratuitous drop shadow; only a thin ring on hover
 */
import { memo, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { FileText, Globe, Info, KeyRound, Monitor, Wifi, WifiOff } from 'lucide-react';
import type { Tool } from '@/types/tool';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { HealthPill } from './HealthPill';
import { LaunchButton } from './LaunchButton';
import { CredentialsPopover, hasCredentials } from '@/components/panels/CredentialsPopover';
import { resolveIcon } from '@/lib/icons';
import { statusMeta } from '@/lib/status';
import { cn } from '@/lib/utils';
import type { LaunchContext } from '@/lib/urls';

interface ToolCardProps {
  tool: Tool;
  categoryName?: string;
  context: LaunchContext;
  launchUrl: string | null;
  onDetail: (id: string) => void;
  onEmbed: (tool: Tool) => void;
  style?: React.CSSProperties;
}

function _ToolCard({
  tool,
  categoryName,
  context,
  launchUrl,
  onDetail,
  onEmbed,
  style,
}: ToolCardProps): React.ReactElement {
  const Icon = resolveIcon(tool.icon);
  const status = tool.health_status ?? 'unknown';
  const meta = statusMeta(status);

  const [credsOpen, setCredsOpen] = useState(false);
  const credsAnchorRef = useRef<HTMLButtonElement | null>(null);

  const accentEdge =
    status === 'healthy'
      ? 'before:bg-[var(--success)]'
      : status === 'degraded'
        ? 'before:bg-[var(--warning)]'
        : status === 'down'
          ? 'before:bg-[var(--destructive)]'
          : 'before:bg-muted-foreground/40';

  const hasCreds = hasCredentials(tool);
  const contextIcon =
    context === 'public' ? Globe : context === 'tailnet' ? Wifi : WifiOff;
  const ContextIcon = contextIcon;

  return (
    <motion.div
      layout="position"
      layoutId={`tool-card-${tool.id}`}
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4, scale: 0.98 }}
      transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ y: -1 }}
      style={style}
    >
      <Card
        data-tool-id={tool.id}
        className={cn(
          'group relative isolate flex h-[138px] flex-col overflow-hidden p-0',
          'card-sheen signal-border',
          'cursor-pointer transition-[border-color,box-shadow] duration-150',
          'hover:border-ring/50',
          'hover:shadow-[0_0_0_1px_color-mix(in_oklch,var(--ring)_22%,transparent),0_10px_24px_-14px_color-mix(in_oklch,var(--accent-signal)_30%,transparent)]',
          'before:pointer-events-none before:absolute before:inset-y-0 before:left-0 before:w-[3px]',
          'before:opacity-85',
          accentEdge,
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
        aria-label={`${tool.name} — ${meta.label}. Press Enter to open detail.`}
      >
        {/* Row 1 — icon, name, health pill */}
        <div className="flex items-start justify-between gap-2 px-3 pt-2.5">
          <div className="flex min-w-0 items-start gap-2.5">
            <div
              className={cn(
                'flex size-8 shrink-0 items-center justify-center rounded-md',
                'border border-border bg-muted/50 text-foreground',
                'transition-colors group-hover:bg-accent group-hover:text-accent-foreground',
              )}
              aria-hidden
            >
              <Icon className="h-4 w-4" />
            </div>
            <div className="min-w-0 pt-0.5">
              <h3 className="truncate text-[13.5px] font-semibold leading-tight tracking-tight">
                {tool.name}
              </h3>
              <p className="mt-0.5 flex items-center gap-1.5 font-mono text-[10px] leading-tight text-muted-foreground">
                <span className="uppercase tracking-wider">
                  {categoryName ?? tool.category}
                </span>
                {tool.container_name ? (
                  <>
                    <span className="opacity-60" aria-hidden>
                      ·
                    </span>
                    <span className="truncate">{tool.container_name}</span>
                  </>
                ) : null}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            <HealthPill tool={tool} />
          </div>
        </div>

        {/* Row 2 — description */}
        <p className="line-clamp-2 px-3 pt-1.5 text-[11.5px] leading-snug text-muted-foreground">
          {tool.description}
        </p>

        {/* Spacer pushes row3 to the bottom */}
        <div className="flex-1" />

        {/* Row 3 — action bar */}
        <div
          className={cn(
            'mt-auto flex items-center justify-between gap-1 border-t border-border/60 bg-muted/15 px-2 py-1.5',
          )}
        >
          {/* Left side — secondary icon actions */}
          <div className="flex items-center gap-0.5">
            {hasCreds ? (
              <Button
                ref={credsAnchorRef}
                type="button"
                variant="ghost"
                size="icon-sm"
                className="size-6 text-muted-foreground hover:text-foreground"
                aria-label={`Credentials for ${tool.name}`}
                aria-expanded={credsOpen}
                aria-haspopup="dialog"
                title="Credentials"
                onClick={(e) => {
                  e.stopPropagation();
                  setCredsOpen((v) => !v);
                }}
              >
                <KeyRound className="h-3 w-3" />
              </Button>
            ) : null}
            {tool.docs_url ? (
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="size-6 text-muted-foreground hover:text-foreground"
                aria-label={`${tool.name} docs`}
                title="Docs"
                asChild
              >
                <a
                  href={tool.docs_url}
                  target="_blank"
                  rel="noreferrer"
                  onClick={(e) => e.stopPropagation()}
                >
                  <FileText className="h-3 w-3" />
                </a>
              </Button>
            ) : null}
            {tool.embed ? (
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="size-6 text-muted-foreground hover:text-foreground"
                aria-label={`Embed ${tool.name}`}
                title="Embed in portal"
                onClick={(e) => {
                  e.stopPropagation();
                  onEmbed(tool);
                }}
              >
                <Monitor className="h-3 w-3" />
              </Button>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className="size-6 text-muted-foreground hover:text-foreground"
              aria-label={`Details for ${tool.name}`}
              title="Details"
              onClick={(e) => {
                e.stopPropagation();
                onDetail(tool.id);
              }}
            >
              <Info className="h-3 w-3" />
            </Button>
            <span
              className={cn(
                'ml-1 inline-flex items-center gap-1 font-mono text-[9.5px] uppercase tracking-wider text-muted-foreground/80',
              )}
              title={`Reachable via ${context}`}
              aria-hidden
            >
              <ContextIcon className="h-2.5 w-2.5" />
              {context === 'public' ? 'pub' : context === 'tailnet' ? 'tail' : 'loc'}
            </span>
          </div>

          {/* Right side — primary launch */}
          <LaunchButton tool={tool} context={context} url={launchUrl} />
        </div>
      </Card>

      {/* Credentials popover — portalled, anchored to the key button */}
      <CredentialsPopover
        tool={tool}
        open={credsOpen}
        anchor={credsAnchorRef.current}
        onClose={() => setCredsOpen(false)}
      />
    </motion.div>
  );
}

export const ToolCard = memo(_ToolCard);
