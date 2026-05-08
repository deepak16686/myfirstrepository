/* Animated tabular numeral — rAF-driven count-up, honours prefers-reduced-motion. */
import { useEffect, useRef, useState } from 'react';
import { cn, prefersReducedMotion } from '@/lib/utils';

interface CountUpProps {
  value: number;
  /** Animation duration in ms. */
  duration?: number;
  /** Decimal places to render. */
  decimals?: number;
  /** Render as percent ("{n}%"). */
  percent?: boolean;
  /** Optional class. */
  className?: string;
  /** Prefix / suffix wrappers. */
  prefix?: string;
  suffix?: string;
}

export function CountUpNumber({
  value,
  duration = 900,
  decimals = 0,
  percent = false,
  className,
  prefix,
  suffix,
}: CountUpProps): React.ReactElement {
  const [display, setDisplay] = useState<number>(value);
  const fromRef = useRef<number>(value);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    if (prefersReducedMotion()) {
      setDisplay(value);
      fromRef.current = value;
      return;
    }

    const from = fromRef.current;
    const to = value;
    if (from === to) return;

    const start = performance.now();

    const tick = (now: number): void => {
      const t = Math.min(1, (now - start) / duration);
      // ease-out-cubic
      const eased = 1 - Math.pow(1 - t, 3);
      const v = from + (to - from) * eased;
      setDisplay(v);
      if (t < 1) {
        rafRef.current = window.requestAnimationFrame(tick);
      } else {
        fromRef.current = to;
      }
    };
    rafRef.current = window.requestAnimationFrame(tick);
    return () => window.cancelAnimationFrame(rafRef.current);
  }, [value, duration]);

  const formatted = decimals > 0 ? display.toFixed(decimals) : Math.round(display).toLocaleString();

  return (
    <span className={cn('tabular-nums', className)}>
      {prefix}
      {formatted}
      {percent ? '%' : ''}
      {suffix}
    </span>
  );
}
