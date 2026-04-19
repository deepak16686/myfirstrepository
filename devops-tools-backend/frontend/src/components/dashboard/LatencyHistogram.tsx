/* Latency distribution — aggregates the newest `latency_ms` per tool into
 * ~12 log-scaled buckets, renders bars via SVG, annotates p50 / p95 / max. */
import { useMemo } from 'react';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import type { Tool } from '@/types/tool';
import { Gauge } from 'lucide-react';

interface HistogramProps {
  tools: Tool[] | undefined;
  className?: string;
}

interface Bucket {
  lo: number;
  hi: number;
  count: number;
  label: string;
}

function percentile(values: number[], p: number): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const rank = (p / 100) * (sorted.length - 1);
  const lo = Math.floor(rank);
  const hi = Math.ceil(rank);
  if (lo === hi) return sorted[lo];
  const frac = rank - lo;
  return sorted[lo] * (1 - frac) + sorted[hi] * frac;
}

function fmtMs(ms: number): string {
  if (ms < 1) return '<1';
  if (ms < 1000) return `${Math.round(ms)}`;
  return `${(ms / 1000).toFixed(1)}k`;
}

function buildBuckets(samples: number[], n: number): Bucket[] {
  if (samples.length === 0) {
    return Array.from({ length: n }, (_, i) => ({ lo: 0, hi: 0, count: 0, label: `b${i}` }));
  }
  const min = Math.max(1, Math.min(...samples));
  const max = Math.max(...samples);
  const logMin = Math.log10(min);
  const logMax = Math.log10(Math.max(max, min * 1.1));
  const step = (logMax - logMin) / n;

  const buckets: Bucket[] = [];
  for (let i = 0; i < n; i++) {
    const loLog = logMin + step * i;
    const hiLog = logMin + step * (i + 1);
    buckets.push({
      lo: Math.round(Math.pow(10, loLog)),
      hi: Math.round(Math.pow(10, hiLog)),
      count: 0,
      label: '',
    });
  }

  for (const v of samples) {
    const idx = Math.min(
      n - 1,
      Math.max(0, Math.floor((Math.log10(Math.max(v, 1)) - logMin) / step))
    );
    buckets[idx].count += 1;
  }
  buckets.forEach((b) => (b.label = `${fmtMs(b.lo)}–${fmtMs(b.hi)}ms`));
  return buckets;
}

export function LatencyHistogram({ tools, className }: HistogramProps): React.ReactElement {
  const { buckets, p50, p95, max, count } = useMemo(() => {
    const samples = (tools ?? [])
      .map((t) => t.latency_ms)
      .filter((x): x is number => typeof x === 'number' && x > 0);
    const b = buildBuckets(samples, 12);
    return {
      buckets: b,
      p50: percentile(samples, 50),
      p95: percentile(samples, 95),
      max: samples.length ? Math.max(...samples) : 0,
      count: samples.length,
    };
  }, [tools]);

  const maxBucketCount = Math.max(1, ...buckets.map((b) => b.count));

  const w = 640;
  const h = 156;
  const padL = 28;
  const padR = 14;
  const padT = 16;
  const padB = 20;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;
  const barGap = 4;
  const barW = (innerW - barGap * (buckets.length - 1)) / buckets.length;

  // Map an ms value to an x position using the bucket boundaries.
  const msToX = (ms: number): number => {
    if (buckets.length === 0 || ms <= 0) return padL;
    const logMin = Math.log10(Math.max(1, buckets[0].lo));
    const logMax = Math.log10(Math.max(buckets[buckets.length - 1].hi, buckets[0].lo + 1));
    const t = (Math.log10(Math.max(ms, 1)) - logMin) / (logMax - logMin);
    return padL + Math.max(0, Math.min(1, t)) * innerW;
  };

  return (
    <Card className={cn('relative overflow-hidden', className)}>
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <div className="flex items-center gap-2">
          <Gauge className="h-4 w-4 text-muted-foreground" />
          <p className="text-sm font-semibold">Latency distribution</p>
          <span className="font-mono text-[11px] text-muted-foreground">
            · {count} probed tools
          </span>
        </div>
        <div className="flex items-center gap-3 font-mono text-[11px]">
          <span className="text-muted-foreground">
            p50 <span className="text-foreground/90">{fmtMs(p50)}ms</span>
          </span>
          <span className="text-muted-foreground">
            p95{' '}
            <span className="text-[color-mix(in_oklch,var(--warning)_92%,var(--foreground))]">
              {fmtMs(p95)}ms
            </span>
          </span>
          <span className="text-muted-foreground">
            max{' '}
            <span className="text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))]">
              {fmtMs(max)}ms
            </span>
          </span>
        </div>
      </div>

      <div className="px-3 py-3">
        <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full">
          <defs>
            <linearGradient id="hist-fill" x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="0"
                stopColor="color-mix(in oklch, var(--accent-signal) 70%, transparent)"
              />
              <stop
                offset="1"
                stopColor="color-mix(in oklch, var(--accent-signal-alt) 20%, transparent)"
              />
            </linearGradient>
          </defs>

          {/* y-axis ticks (2 horizontal rules) */}
          {[0.25, 0.5, 0.75].map((f, i) => (
            <line
              key={`g-${i}`}
              x1={padL}
              x2={w - padR}
              y1={padT + innerH * (1 - f)}
              y2={padT + innerH * (1 - f)}
              stroke="color-mix(in oklch, var(--border) 65%, transparent)"
              strokeDasharray="2 4"
              strokeWidth={0.5}
            />
          ))}

          {/* bars */}
          {buckets.map((b, i) => {
            const barHeight = innerH * (b.count / maxBucketCount);
            const x = padL + i * (barW + barGap);
            const y = padT + innerH - barHeight;
            return (
              <g key={i}>
                <rect
                  x={x}
                  y={y}
                  width={barW}
                  height={Math.max(2, barHeight)}
                  rx={2}
                  fill="url(#hist-fill)"
                  stroke="color-mix(in oklch, var(--accent-signal) 35%, transparent)"
                  strokeWidth={0.5}
                />
                {b.count > 0 ? (
                  <text
                    x={x + barW / 2}
                    y={Math.max(padT + 8, y - 3)}
                    textAnchor="middle"
                    fontFamily="var(--font-mono)"
                    fontSize={9}
                    fill="color-mix(in oklch, var(--foreground) 85%, transparent)"
                  >
                    {b.count}
                  </text>
                ) : null}
              </g>
            );
          })}

          {/* p50 / p95 / max verticals */}
          {count > 0 ? (
            <>
              <Marker x={msToX(p50)} top={padT} bottom={padT + innerH} label="p50" tone="info" />
              <Marker x={msToX(p95)} top={padT} bottom={padT + innerH} label="p95" tone="warning" />
              <Marker x={msToX(max)} top={padT} bottom={padT + innerH} label="max" tone="danger" />
            </>
          ) : null}

          {/* x-axis extremes */}
          <text
            x={padL}
            y={h - 4}
            fontFamily="var(--font-mono)"
            fontSize={9}
            fill="color-mix(in oklch, var(--muted-foreground) 80%, transparent)"
          >
            {fmtMs(buckets[0]?.lo ?? 0)}ms
          </text>
          <text
            x={w - padR}
            y={h - 4}
            textAnchor="end"
            fontFamily="var(--font-mono)"
            fontSize={9}
            fill="color-mix(in oklch, var(--muted-foreground) 80%, transparent)"
          >
            {fmtMs(buckets[buckets.length - 1]?.hi ?? 0)}ms
          </text>
        </svg>

        {count === 0 ? (
          <p className="mono-caps mt-1 text-center text-muted-foreground">
            awaiting first probe wave
          </p>
        ) : null}
      </div>
    </Card>
  );
}

function Marker({
  x,
  top,
  bottom,
  label,
  tone,
}: {
  x: number;
  top: number;
  bottom: number;
  label: string;
  tone: 'info' | 'warning' | 'danger';
}): React.ReactElement {
  const color =
    tone === 'info' ? 'var(--info)' : tone === 'warning' ? 'var(--warning)' : 'var(--destructive)';
  return (
    <g>
      <line
        x1={x}
        x2={x}
        y1={top}
        y2={bottom}
        stroke={color}
        strokeWidth={1}
        strokeDasharray="2 3"
        opacity={0.85}
      />
      <text
        x={x}
        y={top - 4}
        textAnchor="middle"
        fontFamily="var(--font-mono)"
        fontSize={9}
        fill={color}
      >
        {label}
      </text>
    </g>
  );
}
