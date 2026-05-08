/**
 * PipelineProgressCard — live pipeline monitor.
 *
 * Rendered immediately below an assistant chat bubble whenever the chat
 * response contains a `monitoring: { project_id, branch }` hint (or the
 * regex fallback fires). Polls `/api/v1/pipeline/progress/...` every 2s
 * via TanStack Query, animates new events, and stops polling when the
 * backend reports `completed === true`, a clean success, or after the
 * 30-min wall-clock cap. A failed pipeline can still be an active
 * self-heal run, so it must not look terminal while attempts remain.
 *
 * Layout:
 *   row1  Pipeline #{id} on `branch`              [status pill]
 *   row2  [source badge]  [self-heal badge]       [live dot · ATT n/N]
 *   row3  ─── attempt progress bar (non-RAG only) ──────────────
 *   row4  current_message  +  optional [View Pipeline ↗] CTA
 *   row5  vertical event timeline (last 12, "show all" toggle)
 *
 * Token usage:
 *   - bg-card / border-border / muted/* — no new CSS variables introduced.
 *   - status-pill colour-mix() values match the existing HealthPill chip.
 *   - animations: animate-pulse for live dot; animate-[fade-up_…] for new
 *     events (defined in index.css under @theme inline).
 */
import { memo, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleDashed,
  ExternalLink,
  GitBranch,
  Loader2,
  Sparkles,
  Wrench,
  XCircle,
  type LucideIcon,
} from 'lucide-react';
import type { PipelineProgress, PipelineProgressEvent } from '@/types/tool';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/* ------------------------------------------------------------------------ */
/* Status mapping                                                              */
/* ------------------------------------------------------------------------ */
type StatusKey =
  | 'monitoring'
  | 'build_running'
  | 'build_failed'
  | 'success'
  | 'failed'
  | 'unknown';

interface StatusVisual {
  label: string;
  icon: LucideIcon;
  // Tailwind class fragments for the status pill (border + bg + text).
  pillRing: string;
  pillBg: string;
  pillText: string;
  // Live-dot colour (background var()).
  dotColor: string;
  pulse: boolean;
}

const STATUS_VISUALS: Record<StatusKey, StatusVisual> = {
  monitoring: {
    label: 'Monitoring',
    icon: CircleDashed,
    pillRing: 'border-[color-mix(in_oklch,var(--info)_30%,var(--border))]',
    pillBg: 'bg-[color-mix(in_oklch,var(--info)_14%,transparent)]',
    pillText: 'text-[color-mix(in_oklch,var(--info)_92%,var(--foreground))]',
    dotColor: 'var(--info)',
    pulse: true,
  },
  build_running: {
    label: 'Running',
    icon: Loader2,
    pillRing: 'border-[color-mix(in_oklch,var(--info)_30%,var(--border))]',
    pillBg: 'bg-[color-mix(in_oklch,var(--info)_14%,transparent)]',
    pillText: 'text-[color-mix(in_oklch,var(--info)_92%,var(--foreground))]',
    dotColor: 'var(--info)',
    pulse: true,
  },
  build_failed: {
    label: 'Running',
    icon: Wrench,
    pillRing: 'border-[color-mix(in_oklch,var(--warning)_30%,var(--border))]',
    pillBg: 'bg-[color-mix(in_oklch,var(--warning)_14%,transparent)]',
    pillText: 'text-[color-mix(in_oklch,var(--warning)_92%,var(--foreground))]',
    dotColor: 'var(--warning)',
    pulse: true,
  },
  success: {
    label: 'Success',
    icon: CheckCircle2,
    pillRing: 'border-[color-mix(in_oklch,var(--success)_30%,var(--border))]',
    pillBg: 'bg-[color-mix(in_oklch,var(--success)_14%,transparent)]',
    pillText: 'text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))]',
    dotColor: 'var(--success)',
    pulse: false,
  },
  failed: {
    label: 'Failed',
    icon: XCircle,
    pillRing: 'border-[color-mix(in_oklch,var(--destructive)_30%,var(--border))]',
    pillBg: 'bg-[color-mix(in_oklch,var(--destructive)_14%,transparent)]',
    pillText:
      'text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))]',
    dotColor: 'var(--destructive)',
    pulse: false,
  },
  unknown: {
    label: 'Pending',
    icon: CircleDashed,
    pillRing: 'border-border',
    pillBg: 'bg-muted/40',
    pillText: 'text-muted-foreground',
    dotColor: 'var(--muted-foreground)',
    pulse: true,
  },
};

function statusVisualOf(status: string | undefined): StatusVisual {
  if (!status) return STATUS_VISUALS.unknown;
  if (status in STATUS_VISUALS) {
    return STATUS_VISUALS[status as StatusKey];
  }
  return STATUS_VISUALS.unknown;
}

/* ------------------------------------------------------------------------ */
/* Source-of-pipeline badge                                                    */
/* ------------------------------------------------------------------------ */
/**
 * Visual representation of the pipeline generator source. The label is
 * derived from `progress.model_used` per the backend convention:
 *   • `chromadb-direct`            → cyan "RAG template" (info)
 *   • contains "Codex Code"|...    → orange "LLM-generated" (warning)
 *     Legacy Claude Code labels are still accepted for old progress records.
 *   • `template-only`/`default`    → gray "Default template" (mono)
 *   • anything else                → fall through to outline badge.
 */
interface SourceVisual {
  label: string;
  variant: 'info' | 'warning' | 'outline' | 'mono';
  title: string;
}

function sourceFromModel(model: string | null | undefined): SourceVisual {
  if (!model) {
    return {
      label: 'Source: pending',
      variant: 'outline',
      title: 'Pipeline source not yet reported',
    };
  }
  if (model === 'chromadb-direct') {
    return {
      label: 'RAG template',
      variant: 'info',
      title: 'Generated from ChromaDB-stored success template (no LLM call)',
    };
  }
  if (
    model.includes('Codex Code') ||
    model.includes('Claude Code') ||
    model.includes('Ollama') ||
    model.includes('pipeline-generator')
  ) {
    return {
      label: 'LLM-generated',
      variant: 'warning',
      title: `Generated by LLM: ${model}`,
    };
  }
  if (model.includes('template-only') || model === 'default') {
    return {
      label: 'Default template',
      variant: 'mono',
      title: 'Built from the default-language template (no analysis tier)',
    };
  }
  return {
    label: model,
    variant: 'outline',
    title: `Generator: ${model}`,
  };
}

/* ------------------------------------------------------------------------ */
/* Markdown link extraction (for the View Pipeline CTA)                        */
/* ------------------------------------------------------------------------ */
const LINK_RE = /\[([^\]]+)\]\((https?:\/\/[^)]+)\)/;

function extractCtaLink(message: string | undefined): { label: string; url: string } | null {
  if (!message) return null;
  const m = message.match(LINK_RE);
  if (!m) return null;
  return { label: m[1], url: m[2] };
}

function stripMarkdownLink(message: string | undefined): string {
  if (!message) return '';
  return message.replace(LINK_RE, '').replace(/\s{2,}/g, ' ').trim();
}

/* ------------------------------------------------------------------------ */
/* Event timeline icon                                                         */
/* ------------------------------------------------------------------------ */
function eventGlyph(stage: string): { icon: LucideIcon; color: string } {
  switch (stage) {
    case 'success':
      return { icon: CheckCircle2, color: 'var(--success)' };
    case 'failed':
      return { icon: XCircle, color: 'var(--destructive)' };
    case 'build_failed':
      return { icon: AlertTriangle, color: 'var(--warning)' };
    case 'build_running':
      return { icon: Loader2, color: 'var(--info)' };
    case 'monitoring':
      return { icon: CircleDashed, color: 'var(--muted-foreground)' };
    default:
      return { icon: Sparkles, color: 'var(--info)' };
  }
}

/* ------------------------------------------------------------------------ */
/* Props + sub-components                                                      */
/* ------------------------------------------------------------------------ */
interface PipelineProgressCardProps {
  progress: PipelineProgress;
  /** Truthy while the polling loop is still active. */
  polling: boolean;
  /** Friendly placeholder when the backend hasn't created the monitor yet. */
  fallbackBranch?: string;
  fallbackProjectId?: number;
}

function _PipelineProgressCard({
  progress,
  polling,
  fallbackBranch,
  fallbackProjectId,
}: PipelineProgressCardProps): React.ReactElement {
  const [showAll, setShowAll] = useState(false);

  // ---- header derivations ------------------------------------------------
  const branch = progress.branch ?? fallbackBranch ?? '';
  const pipelineId = progress.pipeline_id ?? null;
  const found = progress.found;
  // The status enum is permissive — back-end may add a new stage and we
  // shouldn't blow up. Default to "monitoring" when found-but-statusless.
  const reportedStatus = progress.status ?? (found ? 'monitoring' : 'unknown');
  const rawStatus =
    reportedStatus === 'failed' && progress.completed !== true
      ? 'build_running'
      : reportedStatus;
  const visual = statusVisualOf(rawStatus);
  const StatusIcon = visual.icon;

  const completed = !!progress.completed;
  const isTerminal =
    rawStatus === 'success' || rawStatus === 'failed' || completed;
  const isSuccess = rawStatus === 'success';
  const isFailed = rawStatus === 'failed';

  const attempt = progress.attempt ?? 0;
  const maxAttempts = progress.max_attempts ?? 10;
  const attemptPct = Math.min(
    100,
    Math.max(0, (attempt / Math.max(1, maxAttempts)) * 100),
  );

  const source = useMemo(
    () => sourceFromModel(progress.model_used),
    [progress.model_used],
  );
  const isRagTemplate = progress.model_used === 'chromadb-direct';

  // Prefer the structured URL fields the backend now populates as soon as
  // the monitor learns the pipeline_id. They give a clean click-through
  // even before any progress event has rendered. Fall back to the
  // markdown link embedded in `current_message` for older deploys.
  const cta = useMemo(() => {
    if (progress.pipeline_web_url) {
      return {
        label: pipelineId
          ? `Watch run #${pipelineId} in GitLab`
          : 'Watch in GitLab',
        url: progress.pipeline_web_url,
      };
    }
    if (progress.pipelines_browser_url) {
      return {
        label: 'Open pipelines list',
        url: progress.pipelines_browser_url,
      };
    }
    return extractCtaLink(progress.current_message);
  }, [
    progress.pipeline_web_url,
    progress.pipelines_browser_url,
    progress.current_message,
    pipelineId,
  ]);
  const messageBody = useMemo(
    () => stripMarkdownLink(progress.current_message),
    [progress.current_message],
  );

  // ---- events ------------------------------------------------------------
  const allEvents: PipelineProgressEvent[] = progress.events ?? [];
  const trimmedEvents = showAll ? allEvents : allEvents.slice(-12);
  const hiddenCount = Math.max(0, allEvents.length - 12);

  // Live indicator: green pulse while polling, red dot if failed,
  // checkmark if success, plain muted dot otherwise.
  const liveLabel = isSuccess
    ? 'Completed'
    : isFailed
      ? 'Failed'
      : polling
        ? 'Live'
        : 'Idle';

  // Use the originally-provided project_id when the backend hasn't
  // populated the field yet (race between poll start and monitor create).
  const headerProjectId = progress.project_id ?? fallbackProjectId ?? null;

  return (
    <div
      className={cn(
        'mt-2 ml-10 mr-0 max-w-[min(760px,88%)]',
        'animate-[fade-up_0.4s_cubic-bezier(0.22,1,0.36,1)_both]',
      )}
      role="status"
      aria-live="polite"
      aria-label={`Pipeline monitor for branch ${branch}: ${visual.label}`}
    >
      <div
        className={cn(
          'rounded-lg border border-border bg-card text-card-foreground shadow-sm',
          'overflow-hidden',
        )}
      >
        {/* ------ Row 1: header ------------------------------------------- */}
        <div className="flex items-start justify-between gap-3 px-3.5 pt-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <div
              className={cn(
                'flex size-7 shrink-0 items-center justify-center rounded-md',
                'border border-border bg-muted/50 text-foreground',
              )}
              aria-hidden
            >
              <Bot className="h-3.5 w-3.5" />
            </div>
            <div className="min-w-0">
              <h3 className="flex flex-wrap items-center gap-1.5 text-[13px] font-semibold leading-tight tracking-tight">
                <span>Pipeline</span>
                <span className="font-mono text-[12px] text-muted-foreground">
                  #{pipelineId ?? '...'}
                </span>
                <span className="text-muted-foreground/70">on</span>
                <span className="inline-flex items-center gap-1 rounded-md border border-border bg-muted/40 px-1.5 py-0.5 font-mono text-[11px] text-foreground">
                  <GitBranch className="h-3 w-3 opacity-70" />
                  {branch || '—'}
                </span>
              </h3>
              <p className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                {headerProjectId !== null
                  ? `project ${headerProjectId}`
                  : 'project pending'}
                {' · '}
                {isRagTemplate
                  ? 'RAG status-only monitor'
                  : `self-heal up to ${maxAttempts} attempts`}
              </p>
            </div>
          </div>
          <span
            className={cn(
              'inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5',
              'font-mono text-[10.5px] uppercase leading-none tracking-wider tabular-nums',
              visual.pillRing,
              visual.pillBg,
              visual.pillText,
            )}
          >
            <StatusIcon
              className={cn(
                'h-3 w-3',
                rawStatus === 'build_running' ? 'animate-spin' : '',
              )}
            />
            {visual.label}
          </span>
        </div>

        {/* ------ Row 2: badges + live indicator --------------------------- */}
        <div className="flex flex-wrap items-center justify-between gap-2 px-3.5 pt-2">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge variant={source.variant} title={source.title}>
              <Sparkles className="h-3 w-3 opacity-70" />
              {source.label}
            </Badge>
            {progress.fixer_model_used ? (
              <Badge
                variant="warning"
                title={`Self-heal model: ${progress.fixer_model_used}`}
              >
                <Wrench className="h-3 w-3 opacity-70" />
                Self-heal: {progress.fixer_model_used}
              </Badge>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 font-mono text-[10.5px] uppercase tracking-wider text-muted-foreground">
              <span
                className={cn(
                  'inline-block size-1.5 rounded-full',
                  visual.pulse && polling ? 'animate-pulse' : '',
                )}
                style={{ background: visual.dotColor }}
                aria-hidden
              />
              {liveLabel}
            </span>
            {!isRagTemplate ? (
              <span className="font-mono text-[10.5px] uppercase tracking-wider text-muted-foreground tabular-nums">
                ATT {attempt}/{maxAttempts}
              </span>
            ) : null}
          </div>
        </div>

        {/* ------ Row 3: attempt progress bar ------------------------------ */}
        {!isRagTemplate ? (
          <div className="px-3.5 pt-2">
          <div
            className="h-1 w-full overflow-hidden rounded-full bg-muted/50"
            aria-label={`Attempt ${attempt} of ${maxAttempts}`}
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={maxAttempts}
            aria-valuenow={attempt}
          >
            <div
              className="h-full rounded-full transition-[width] duration-500 ease-out"
              style={{
                width: `${attemptPct}%`,
                background: isFailed
                  ? 'var(--destructive)'
                  : isSuccess
                    ? 'var(--success)'
                    : isTerminal
                      ? 'var(--warning)'
                      : 'var(--info)',
              }}
            />
          </div>
          </div>
        ) : null}

        {/* ------ Row 4: current message + CTA ----------------------------- */}
        {messageBody || cta ? (
          <div className="flex flex-wrap items-start justify-between gap-2 px-3.5 pt-2.5">
            {messageBody ? (
              <p className="min-w-0 flex-1 text-[12px] leading-snug text-foreground/90">
                {messageBody}
              </p>
            ) : (
              <span className="flex-1" />
            )}
            {cta ? (
              <Button
                asChild
                size="sm"
                variant="outline"
                className="h-7 gap-1.5 rounded-md text-[11px]"
              >
                <a href={cta.url} target="_blank" rel="noreferrer">
                  <ExternalLink className="h-3 w-3" />
                  {cta.label || 'View Pipeline'}
                </a>
              </Button>
            ) : null}
          </div>
        ) : null}

        {/* ------ Row 5: events timeline ----------------------------------- */}
        <div className="border-t border-border/60 bg-muted/15 px-3.5 py-2.5">
          {allEvents.length === 0 ? (
            <p className="font-mono text-[10.5px] uppercase tracking-wider text-muted-foreground">
              {found
                ? 'No events yet — waiting for first stage…'
                : polling
                  ? 'Connecting to monitor…'
                  : 'Monitor not started.'}
            </p>
          ) : (
            <>
              <div className="flex items-center justify-between pb-1.5">
                <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Stage timeline ({allEvents.length})
                </span>
                {hiddenCount > 0 ? (
                  <button
                    type="button"
                    onClick={() => setShowAll((v) => !v)}
                    className={cn(
                      'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5',
                      'font-mono text-[10px] uppercase tracking-wider',
                      'text-muted-foreground hover:bg-accent hover:text-foreground',
                      'transition-colors',
                    )}
                    aria-expanded={showAll}
                    aria-label={showAll ? 'Show last 12 events' : 'Show all events'}
                  >
                    {showAll ? (
                      <>
                        <ChevronUp className="h-3 w-3" />
                        last 12
                      </>
                    ) : (
                      <>
                        <ChevronDown className="h-3 w-3" />
                        show all (+{hiddenCount})
                      </>
                    )}
                  </button>
                ) : null}
              </div>
              <ol className="relative space-y-1 border-l border-border/70 pl-3">
                {trimmedEvents.map((ev, idx) => {
                  const { icon: Glyph, color } = eventGlyph(ev.stage);
                  const isLatest = idx === trimmedEvents.length - 1;
                  const animation = isLatest
                    ? 'animate-[fade-up_0.3s_cubic-bezier(0.22,1,0.36,1)_both]'
                    : '';
                  return (
                    <li
                      key={`${ev.timestamp}-${idx}`}
                      className={cn(
                        'group flex items-start gap-2 pl-1 pr-1 py-0.5',
                        animation,
                      )}
                    >
                      <span
                        className={cn(
                          'mt-[3px] -ml-[14px] flex size-3 shrink-0 items-center justify-center rounded-full border border-border bg-card',
                          isLatest && visual.pulse ? 'ring-2 ring-offset-1 ring-offset-card' : '',
                        )}
                        style={
                          isLatest && visual.pulse
                            ? ({
                                ['--tw-ring-color' as string]: color,
                              } as React.CSSProperties)
                            : undefined
                        }
                        aria-hidden
                      >
                        <Glyph
                          className={cn(
                            'h-2 w-2',
                            ev.stage === 'build_running' ? 'animate-spin' : '',
                          )}
                          style={{ color }}
                        />
                      </span>
                      <span className="font-mono text-[10.5px] tabular-nums text-muted-foreground">
                        {ev.timestamp}
                      </span>
                      <span className="min-w-0 flex-1 text-[11.5px] leading-snug text-foreground/90 [overflow-wrap:anywhere]">
                        <EventText text={ev.message} />
                        {ev.attempt > 0 ? (
                          <span className="ml-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                            · att {ev.attempt}/{ev.max_attempts}
                          </span>
                        ) : null}
                      </span>
                    </li>
                  );
                })}
              </ol>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export const PipelineProgressCard = memo(_PipelineProgressCard);

/* ------------------------------------------------------------------------ */
/* EventText — light render of inline `code` and [label](url) links            */
/* ------------------------------------------------------------------------ */
/**
 * Hand-rolled to avoid `dangerouslySetInnerHTML` for the dynamic backend
 * messages — events are tokenised and rendered as plain spans / anchors,
 * so any markdown-injection in a backend log line is harmless. We support
 * just two minimal markdown forms because backend `current_message`
 * already uses them: `[label](url)` and emoji-prefixed plain text.
 */
function EventText({ text }: { text: string }): React.ReactElement {
  const parts = useMemo(() => splitMarkdown(text), [text]);
  return (
    <>
      {parts.map((p, i) => {
        if (p.kind === 'link') {
          return (
            <a
              key={i}
              href={p.url}
              target="_blank"
              rel="noreferrer"
              className="text-primary underline decoration-dotted underline-offset-2 hover:decoration-solid"
            >
              {p.label}
            </a>
          );
        }
        if (p.kind === 'code') {
          return (
            <code
              key={i}
              className="rounded-sm border border-border bg-muted/40 px-1 py-[1px] font-mono text-[10.5px]"
            >
              {p.text}
            </code>
          );
        }
        return <span key={i}>{p.text}</span>;
      })}
    </>
  );
}

type Token =
  | { kind: 'text'; text: string }
  | { kind: 'link'; label: string; url: string }
  | { kind: 'code'; text: string };

function splitMarkdown(text: string): Token[] {
  const tokens: Token[] = [];
  let cursor = 0;
  // Combined pattern: links first (longer), then inline code.
  const re = /\[([^\]]+)\]\((https?:\/\/[^)]+)\)|`([^`]+)`/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > cursor) {
      tokens.push({ kind: 'text', text: text.slice(cursor, m.index) });
    }
    if (m[1] !== undefined && m[2] !== undefined) {
      tokens.push({ kind: 'link', label: m[1], url: m[2] });
    } else if (m[3] !== undefined) {
      tokens.push({ kind: 'code', text: m[3] });
    }
    cursor = re.lastIndex;
  }
  if (cursor < text.length) {
    tokens.push({ kind: 'text', text: text.slice(cursor) });
  }
  return tokens.length > 0 ? tokens : [{ kind: 'text', text }];
}
