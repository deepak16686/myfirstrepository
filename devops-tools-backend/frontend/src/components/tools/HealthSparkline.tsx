/* SVG sparkline from client-side latency buffer; falls back to shimmer when n < 2. */
import { useMemo } from 'react';
import { getHealthHistory } from '@/hooks/useHealth';
import { cn } from '@/lib/utils';
import type { HealthStatus } from '@/types/tool';

interface SparkProps {
  toolId: string;
  status: HealthStatus;
  size?: 'xs' | 'sm' | 'md';
  showLabels?: boolean;
  className?: string;
}

const DIMENSIONS: Record<NonNullable<SparkProps['size']>, { w: number; h: number; pad: number }> = {
  xs: { w: 120, h: 20, pad: 2 },
  sm: { w: 200, h: 40, pad: 3 },
  md: { w: 280, h: 64, pad: 4 },
};

export function HealthSparkline({
  toolId,
  status,
  size = 'md',
  showLabels,
  className,
}: SparkProps): React.ReactElement {
  const points = useMemo(() => {
    const hist = getHealthHistory(toolId);
    return hist
      .map((h) => h.latency)
      .filter((x): x is number => typeof x === 'number' && x >= 0)
      .slice(-30);
  }, [toolId]);

  const { w, h, pad } = DIMENSIONS[size];

  const color =
    status === 'healthy'
      ? 'var(--success)'
      : status === 'degraded'
        ? 'var(--warning)'
        : status === 'down'
          ? 'var(--destructive)'
          : 'var(--muted-foreground)';

  // Too few samples — render an animated shimmer "awaiting probe" strip.
  if (points.length < 2) {
    return (
      <div
        className={cn(
          'relative flex w-full items-center justify-center overflow-hidden rounded-md border border-dashed border-border/60 bg-muted/20',
          size === 'xs' ? 'h-5' : size === 'sm' ? 'h-10' : 'h-16',
          className
        )}
        aria-label="Awaiting first probe"
      >
        <span
          aria-hidden
          className="absolute inset-0 bg-[linear-gradient(90deg,transparent,color-mix(in_oklch,var(--muted-foreground)_18%,transparent),transparent)] bg-[length:200%_100%] animate-[shimmer_1.8s_linear_infinite]"
        />
        <span className="mono-caps relative text-muted-foreground">awaiting first probe</span>
      </div>
    );
  }

  const { path, area, minV, maxV } = (() => {
    const mn = Math.min(...points);
    const mx = Math.max(...points);
    const range = mx - mn || 1;
    const step = (w - pad * 2) / Math.max(points.length - 1, 1);
    const toPt = (v: number, i: number): [number, number] => {
      const x = pad + i * step;
      const y = h - pad - ((v - mn) / range) * (h - pad * 2);
      return [x, y];
    };
    const pts = points.map(toPt);
    const linePath = pts
      .map(
        ([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`
      )
      .join(' ');
    const first = pts[0];
    const last = pts[pts.length - 1];
    const areaPath = `${linePath} L${last[0].toFixed(1)} ${h - pad} L${first[0].toFixed(1)} ${
      h - pad
    } Z`;
    return { path: linePath, area: areaPath, minV: mn, maxV: mx };
  })();

  return (
    <div className={cn('relative w-full', className)}>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="none"
        className={cn(
          'w-full',
          size === 'xs' ? 'h-5' : size === 'sm' ? 'h-10' : 'h-16'
        )}
        aria-hidden
      >
        <defs>
          <linearGradient id={`g-${toolId}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={color} stopOpacity="0.35" />
            <stop offset="1" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill={`url(#g-${toolId})`} />
        <path d={path} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
      </svg>
      {showLabels ? (
        <div className="absolute inset-x-0 bottom-0 flex justify-between px-1 font-mono text-[10px] text-muted-foreground">
          <span>min {Math.round(minV)}ms</span>
          <span>max {Math.round(maxV)}ms</span>
        </div>
      ) : null}
    </div>
  );
}
