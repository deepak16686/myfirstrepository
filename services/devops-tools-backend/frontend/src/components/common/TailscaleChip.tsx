import { Globe2, ShieldOff, ShieldCheck, Signal } from 'lucide-react';
import { useTailscale } from '@/hooks/useTools';
import { cn } from '@/lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

type State = 'live' | 'local' | 'down';

export function TailscaleChip(): React.ReactElement {
  const { data, isLoading } = useTailscale();
  const state: State = (data?.state as State | undefined) ?? 'local';
  const funnelEnabled = data?.funnel_enabled ?? false;

  // "live + funnel enabled" is treated as a stronger, brighter state than
  // "live + funnel off" — the UI surfaces both.
  const tone =
    state === 'live' && funnelEnabled
      ? 'funnel'
      : state === 'live'
        ? 'tailnet'
        : state === 'down'
          ? 'down'
          : 'local';

  const meta = {
    funnel: {
      label: 'Funnel live',
      icon: ShieldCheck,
      dot: 'bg-[var(--success)]',
      text: 'text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))]',
      border: 'border-[color-mix(in_oklch,var(--success)_25%,var(--border))]',
      bg: 'bg-[color-mix(in_oklch,var(--success)_10%,transparent)]',
    },
    tailnet: {
      label: 'Tailnet only',
      icon: Globe2,
      dot: 'bg-[var(--info)]',
      text: 'text-[color-mix(in_oklch,var(--info)_92%,var(--foreground))]',
      border: 'border-[color-mix(in_oklch,var(--info)_25%,var(--border))]',
      bg: 'bg-[color-mix(in_oklch,var(--info)_10%,transparent)]',
    },
    local: {
      label: 'Local only',
      icon: Signal,
      dot: 'bg-muted-foreground/60',
      text: 'text-muted-foreground',
      border: 'border-border',
      bg: 'bg-muted/50',
    },
    down: {
      label: 'Tailscale down',
      icon: ShieldOff,
      dot: 'bg-[var(--destructive)]',
      text: 'text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))]',
      border: 'border-[color-mix(in_oklch,var(--destructive)_25%,var(--border))]',
      bg: 'bg-[color-mix(in_oklch,var(--destructive)_10%,transparent)]',
    },
  }[tone];

  const Icon = meta.icon;
  const host = data?.magic_dns ?? data?.hostname ?? undefined;

  return (
    <TooltipProvider delayDuration={120}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={cn(
              'inline-flex h-8 items-center gap-2 rounded-full border px-3 font-mono text-[11px] uppercase tracking-wider transition-colors',
              meta.border,
              meta.bg,
              meta.text
            )}
            role="status"
            aria-label={`Tailscale status: ${meta.label}`}
          >
            <span className={cn('size-1.5 rounded-full', meta.dot)} />
            <Icon className="h-3.5 w-3.5" aria-hidden />
            <span>{meta.label}</span>
          </span>
        </TooltipTrigger>
        <TooltipContent side="bottom" className="max-w-[280px] text-xs">
          {isLoading ? (
            <>Fetching Tailscale status…</>
          ) : tone === 'funnel' ? (
            <>
              Publicly reachable via Funnel
              {host ? (
                <>
                  {' '}at <code className="font-mono text-[11px]">https://{host}</code>
                </>
              ) : null}
              .
            </>
          ) : tone === 'tailnet' ? (
            <>
              Tailnet is up, Funnel is off. Reachable from other tailnet devices
              {host ? (
                <>
                  {' '}at <code className="font-mono text-[11px]">{host}</code>
                </>
              ) : null}
              . Run <code className="font-mono text-[11px]">tailscale funnel 443 on</code> to expose
              publicly.
            </>
          ) : tone === 'local' ? (
            <>
              Tailscale is not active. Portal is reachable on localhost only.
              {data?.error ? (
                <>
                  <br />
                  <span className="text-muted-foreground">{data.error}</span>
                </>
              ) : null}
            </>
          ) : (
            <>
              Tailscale daemon is logged out or stopped. Run{' '}
              <code className="font-mono">tailscale up</code>.
            </>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
