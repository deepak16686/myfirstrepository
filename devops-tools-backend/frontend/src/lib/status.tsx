/* Shared status glyph + chip for HealthStatus across the portal. */
import { AlertTriangle, CheckCircle2, CircleSlash2, HelpCircle, type LucideIcon } from 'lucide-react';
import type { HealthStatus } from '@/types/tool';

export interface StatusMeta {
  label: string;
  shortLabel: string;
  icon: LucideIcon;
  signal: string;
  ring: string;
  bg: string;
  text: string;
}

export const STATUS_META: Record<HealthStatus, StatusMeta> = {
  healthy: {
    label: 'OPERATIONAL',
    shortLabel: 'HEALTHY',
    icon: CheckCircle2,
    signal: 'var(--success)',
    ring: 'border-[color-mix(in_oklch,var(--success)_30%,var(--border))]',
    bg: 'bg-[color-mix(in_oklch,var(--success)_12%,transparent)]',
    text: 'text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))]',
  },
  degraded: {
    label: 'DEGRADED',
    shortLabel: 'DEGRADED',
    icon: AlertTriangle,
    signal: 'var(--warning)',
    ring: 'border-[color-mix(in_oklch,var(--warning)_30%,var(--border))]',
    bg: 'bg-[color-mix(in_oklch,var(--warning)_14%,transparent)]',
    text: 'text-[color-mix(in_oklch,var(--warning)_92%,var(--foreground))]',
  },
  down: {
    label: 'OFFLINE',
    shortLabel: 'DOWN',
    icon: CircleSlash2,
    signal: 'var(--destructive)',
    ring: 'border-[color-mix(in_oklch,var(--destructive)_30%,var(--border))]',
    bg: 'bg-[color-mix(in_oklch,var(--destructive)_12%,transparent)]',
    text: 'text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))]',
  },
  unknown: {
    label: 'NO DATA',
    shortLabel: 'UNKNOWN',
    icon: HelpCircle,
    signal: 'var(--muted-foreground)',
    ring: 'border-border',
    bg: 'bg-muted/40',
    text: 'text-muted-foreground',
  },
};

export function statusMeta(status: HealthStatus | undefined | null): StatusMeta {
  return STATUS_META[status ?? 'unknown'];
}
