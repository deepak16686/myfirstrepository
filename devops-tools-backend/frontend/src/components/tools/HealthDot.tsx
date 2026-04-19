/* Three-layer health indicator: halo ring, mid ring, solid dot, with status-specific motion. */
import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import type { HealthStatus } from '@/types/tool';

interface HealthDotProps {
  status: HealthStatus;
  size?: 'xs' | 'sm' | 'md' | 'lg';
  pulse?: boolean;
  className?: string;
  'aria-label'?: string;
}

const COLOR_MAP: Record<HealthStatus, { signal: string; label: string }> = {
  healthy: { signal: 'var(--success)', label: 'healthy' },
  degraded: { signal: 'var(--warning)', label: 'degraded' },
  down: { signal: 'var(--destructive)', label: 'down' },
  unknown: { signal: 'var(--muted-foreground)', label: 'unknown' },
};

const SIZE_PX: Record<NonNullable<HealthDotProps['size']>, number> = {
  xs: 6,
  sm: 8,
  md: 12,
  lg: 16,
};

export function HealthDot({
  status,
  size = 'sm',
  pulse = true,
  className,
  'aria-label': ariaLabel,
}: HealthDotProps): React.ReactElement {
  const { signal, label } = COLOR_MAP[status];
  const diameter = SIZE_PX[size];
  const prev = useRef<HealthStatus>(status);
  const [shake, setShake] = useState(false);

  useEffect(() => {
    if (prev.current !== status) {
      if (status === 'down') {
        setShake(true);
        const t = window.setTimeout(() => setShake(false), 460);
        return () => window.clearTimeout(t);
      }
      prev.current = status;
    }
    return undefined;
  }, [status]);

  const pulsing = pulse && status === 'healthy';
  const throbbing = pulse && status === 'degraded';

  return (
    <span
      className={cn(
        'relative inline-flex shrink-0 items-center justify-center',
        shake && 'animate-[shake-once_0.45s_cubic-bezier(0.36,0,0.22,1)]',
        className
      )}
      style={{ width: diameter, height: diameter, ['--tw-signal-color' as string]: signal }}
      role="status"
      aria-label={ariaLabel ?? `Status: ${label}`}
    >
      {/* Outer halo (only on healthy / degraded) */}
      {(pulsing || throbbing) && (
        <span
          aria-hidden
          className={cn(
            'absolute inset-[-40%] rounded-full',
            pulsing && 'animate-[pulse-signal_2.4s_cubic-bezier(0.4,0,0.6,1)_infinite]'
          )}
          style={{
            background: `radial-gradient(circle, color-mix(in oklch, ${signal} 35%, transparent) 0%, transparent 70%)`,
          }}
        />
      )}

      {/* Middle ring */}
      <span
        aria-hidden
        className={cn(
          'absolute rounded-full',
          throbbing && 'animate-[throb_1.6s_ease-in-out_infinite]'
        )}
        style={{
          inset: '-20%',
          border: `1px solid color-mix(in oklch, ${signal} 45%, transparent)`,
        }}
      />

      {/* Solid dot */}
      <span
        aria-hidden
        className="rounded-full"
        style={{
          width: '100%',
          height: '100%',
          background: signal,
          boxShadow:
            status === 'down'
              ? `0 0 0 1px color-mix(in oklch, ${signal} 70%, transparent), 0 0 8px 1px color-mix(in oklch, ${signal} 55%, transparent)`
              : `0 0 4px color-mix(in oklch, ${signal} 55%, transparent)`,
          opacity: status === 'unknown' ? 0.55 : 1,
        }}
      />
    </span>
  );
}
