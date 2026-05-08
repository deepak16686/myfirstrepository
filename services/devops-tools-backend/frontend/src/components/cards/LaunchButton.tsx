/**
 * LaunchButton — the card's primary action. Picks the correct URL based on
 * the current browser origin (Local / Tailnet / Public) and opens the tool
 * in a new tab.
 *
 * The button also tries the backend's `/launch/:id` endpoint first — that
 * endpoint may return a rewritten `redirect_url` (e.g. SSO-wrapped). If the
 * endpoint is unavailable or fails, we fall back to the context-resolved
 * URL and open it directly. Users should never see the button "do nothing".
 *
 * The subtitle below the label shows the exact kind of URL that will be
 * opened ("LOCAL", "TAILNET", or "PUBLIC") so operators know which face
 * of the service they're about to hit.
 */
import { ExternalLink } from 'lucide-react';
import { toast } from 'sonner';
import type { Tool } from '@/types/tool';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { contextLabel, type LaunchContext } from '@/lib/urls';
import { openToolLaunch } from '@/lib/launch';

interface LaunchButtonProps {
  tool: Tool;
  context: LaunchContext;
  url: string | null;
  className?: string;
}

export function LaunchButton({
  tool,
  context,
  url,
  className,
}: LaunchButtonProps): React.ReactElement {
  const disabled = !url;
  const ctxLabel = contextLabel(context);

  const onClick = async (e: React.MouseEvent<HTMLButtonElement>): Promise<void> => {
    e.stopPropagation();
    if (!url) {
      toast.error(`No launch URL configured for ${tool.name}`);
      return;
    }
    const opened = await openToolLaunch(tool);
    if (!opened) toast.error(`No launch URL configured for ${tool.name}`);
  };

  return (
    <Button
      variant="signal"
      size="sm"
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={`Launch ${tool.name} (${ctxLabel.toLowerCase()})`}
      title={url ?? 'No launch URL configured'}
      className={cn(
        'group/launch h-7 shrink-0 gap-1.5 px-2.5',
        'font-mono text-[11px] uppercase tracking-wider',
        className,
      )}
    >
      <span className="flex items-center gap-1.5">
        Launch
        <span
          className={cn(
            'rounded-sm border px-1 py-px text-[9px] leading-none',
            'border-[color-mix(in_oklch,var(--primary)_30%,transparent)]',
            'bg-[color-mix(in_oklch,var(--primary)_12%,transparent)]',
            'text-[color-mix(in_oklch,var(--primary)_92%,var(--foreground))]',
          )}
          aria-hidden
        >
          {ctxLabel}
        </span>
      </span>
      <ExternalLink
        className="h-3 w-3 transition-transform duration-150 group-hover/launch:translate-x-[1px] group-hover/launch:-translate-y-[1px]"
        aria-hidden
      />
    </Button>
  );
}
