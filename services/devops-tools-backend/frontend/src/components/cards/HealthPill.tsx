/**
 * HealthPill — compact two-part status chip: a coloured dot + a short
 * monospace latency readout. Designed for the header row of the dense
 * ToolCard (≤140px tall), so it packs as much signal as possible into
 * ~56px of width.
 *
 * Visual hierarchy:
 *   • healthy  → cyan-ish "success" signal + live latency (e.g. "31ms")
 *   • degraded → amber "warning" signal + latency
 *   • down     → red "destructive" signal + "DOWN" label (no latency, since
 *                  we don't know what "fast-but-broken" even means)
 *   • unknown  → muted dot + "—"
 *
 * The dot itself uses the existing HealthDot for consistency; the numeric
 * readout is tabular-numeric so adjacent cards line up on the ms digit.
 */
import type { HealthStatus, Tool } from '@/types/tool';
import { HealthDot } from '@/components/tools/HealthDot';
import { cn, formatLatency } from '@/lib/utils';
import { statusMeta } from '@/lib/status';

interface HealthPillProps {
  tool: Pick<Tool, 'health_status' | 'latency_ms' | 'last_checked'>;
  className?: string;
}

export function HealthPill({ tool, className }: HealthPillProps): React.ReactElement {
  const status: HealthStatus = tool.health_status ?? 'unknown';
  const meta = statusMeta(status);
  const latency = formatLatency(tool.latency_ms, tool.last_checked);

  // For down status the latency is either missing or meaningless; show the
  // word "DOWN" instead so the card never displays "down · —".
  const readout: string =
    status === 'down'
      ? 'DOWN'
      : status === 'unknown'
        ? '—'
        : latency;

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5',
        'font-mono text-[10.5px] leading-none tracking-wide tabular-nums',
        meta.ring,
        meta.bg,
        meta.text,
        className,
      )}
      aria-label={`${meta.label}${readout !== '—' && readout !== 'DOWN' ? ` — latency ${readout}` : ''}`}
    >
      <HealthDot status={status} size="xs" pulse={status !== 'unknown'} />
      <span>{readout}</span>
    </span>
  );
}
