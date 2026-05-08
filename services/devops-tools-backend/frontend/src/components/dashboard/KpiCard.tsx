/* KPI card — gradient signal sheen, numeric count-up, optional mini trend.
 * Tone drives accent edge + icon color; `trend` feeds a 24-point sparkline. */
import { useMemo, type ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { TrendingDown, TrendingUp, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Card } from '@/components/ui/card';
import { CountUpNumber } from '@/components/common/CountUpNumber';

type Tone = 'default' | 'success' | 'warning' | 'danger' | 'info';

interface KpiCardProps {
  label: string;
  value: number | string;
  hint?: ReactNode;
  icon?: LucideIcon;
  tone?: Tone;
  delta?: number | null;
  deltaLabel?: string;
  /** Percent formatting; only used when `value` is numeric. */
  percent?: boolean;
  /** Optional 8-24 numeric samples for a mini area spark. */
  trend?: number[];
  className?: string;
}

const TONE_EDGE: Record<Tone, string> = {
  default: 'before:bg-primary',
  success: 'before:bg-[var(--success)]',
  warning: 'before:bg-[var(--warning)]',
  danger: 'before:bg-[var(--destructive)]',
  info: 'before:bg-[var(--info)]',
};

const TONE_ICON: Record<Tone, string> = {
  default: 'text-primary bg-primary/10',
  success:
    'text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))] bg-[color-mix(in_oklch,var(--success)_12%,transparent)]',
  warning:
    'text-[color-mix(in_oklch,var(--warning)_92%,var(--foreground))] bg-[color-mix(in_oklch,var(--warning)_15%,transparent)]',
  danger:
    'text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))] bg-[color-mix(in_oklch,var(--destructive)_12%,transparent)]',
  info:
    'text-[color-mix(in_oklch,var(--info)_92%,var(--foreground))] bg-[color-mix(in_oklch,var(--info)_12%,transparent)]',
};

const TONE_SPARK: Record<Tone, string> = {
  default: 'var(--primary)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  danger: 'var(--destructive)',
  info: 'var(--info)',
};

function Spark({ samples, color }: { samples: number[]; color: string }): React.ReactElement {
  const w = 96;
  const h = 30;
  const pad = 2;
  const mn = Math.min(...samples);
  const mx = Math.max(...samples);
  const range = mx - mn || 1;
  const step = (w - pad * 2) / Math.max(samples.length - 1, 1);
  const pts = samples.map((v, i): [number, number] => [
    pad + i * step,
    h - pad - ((v - mn) / range) * (h - pad * 2),
  ]);
  const linePath = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
  const first = pts[0];
  const last = pts[pts.length - 1];
  const area = `${linePath} L${last[0].toFixed(1)} ${h - pad} L${first[0].toFixed(1)} ${h - pad} Z`;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-8 w-[96px]" aria-hidden>
      <defs>
        <linearGradient id={`spark-${color.replace(/[^a-z0-9]/gi, '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.35" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#spark-${color.replace(/[^a-z0-9]/gi, '')})`} />
      <path d={linePath} fill="none" stroke={color} strokeWidth="1.25" strokeLinejoin="round" />
    </svg>
  );
}

export function KpiCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = 'default',
  delta,
  deltaLabel,
  percent,
  trend,
  className,
}: KpiCardProps): React.ReactElement {
  const deltaIcon = delta == null || delta === 0 ? Minus : delta > 0 ? TrendingUp : TrendingDown;
  const DeltaIcon = deltaIcon;
  const deltaColor =
    delta == null || delta === 0
      ? 'text-muted-foreground'
      : delta > 0
        ? 'text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))]'
        : 'text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))]';

  const numeric = useMemo(() => (typeof value === 'number' ? value : NaN), [value]);

  return (
    <Card
      className={cn(
        'group relative isolate overflow-hidden p-5',
        'before:pointer-events-none before:absolute before:inset-y-0 before:left-0 before:w-[3px]',
        TONE_EDGE[tone],
        // conic gradient sheen on hover
        'card-sheen',
        // hover lift
        'transition-transform duration-300 will-change-transform hover:-translate-y-0.5',
        className
      )}
    >
      {/* Large soft gradient halo behind the big number */}
      <div
        aria-hidden
        className="absolute -top-16 right-0 h-48 w-48 rounded-full blur-3xl opacity-40"
        style={{
          background: `radial-gradient(circle, color-mix(in oklch, ${TONE_SPARK[tone]} 22%, transparent), transparent 60%)`,
        }}
      />

      <div className="relative flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1.5">
          <p className="mono-caps text-muted-foreground">{label}</p>
          <p className="font-mono text-3xl font-semibold leading-none tabular-nums">
            {Number.isFinite(numeric) ? (
              <CountUpNumber value={numeric} percent={percent} />
            ) : (
              value
            )}
          </p>
          {hint ? <p className="text-[12px] text-muted-foreground">{hint}</p> : null}
        </div>
        {Icon ? (
          <div
            className={cn(
              'flex size-10 shrink-0 items-center justify-center rounded-md',
              TONE_ICON[tone]
            )}
          >
            <Icon className="h-5 w-5" />
          </div>
        ) : null}
      </div>

      {delta !== undefined && delta !== null ? (
        <div className="relative mt-4 flex items-center gap-1.5 text-xs">
          <DeltaIcon className={cn('h-3.5 w-3.5', deltaColor)} />
          <span className={cn('font-mono tabular-nums', deltaColor)}>
            {delta > 0 ? '+' : ''}
            {delta}
          </span>
          {deltaLabel ? <span className="text-muted-foreground">{deltaLabel}</span> : null}
        </div>
      ) : null}

      {trend && trend.length >= 2 ? (
        <div className="relative mt-3 flex items-end justify-end">
          <Spark samples={trend} color={TONE_SPARK[tone]} />
        </div>
      ) : null}
    </Card>
  );
}
