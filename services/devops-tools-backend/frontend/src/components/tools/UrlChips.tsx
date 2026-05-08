/**
 * UrlChips — compact row of URL chips for a tool, showing where it is
 * reachable. One chip per available reachability plane:
 *
 *   - `url_external` → grey "LOCAL" chip
 *   - `url_tailnet`  → blue  "TAILNET" chip (only if the field is present)
 *   - `url_funnel`   → green "PUBLIC" chip with a Globe icon (only if present)
 *
 * Each chip is the click target — it opens the URL in a new tab — and has
 * a sibling copy button. Color tokens mirror TailscaleChip's
 * `var(--success)/var(--info)/var(--muted-foreground)` palette so the two
 * pieces stay visually coherent.
 */
import { Copy, ExternalLink, Globe } from 'lucide-react';
import { toast } from 'sonner';
import type { Tool } from '@/types/tool';
import { cn } from '@/lib/utils';

type Tone = 'local' | 'tailnet' | 'public';

interface ChipSpec {
  tone: Tone;
  label: string;
  url: string;
  icon?: typeof Globe;
}

const toneClasses: Record<Tone, { wrap: string; dot: string }> = {
  local: {
    wrap: 'border-border bg-muted/50 text-muted-foreground hover:bg-muted/80',
    dot: 'bg-muted-foreground/60',
  },
  tailnet: {
    wrap:
      'border-[color-mix(in_oklch,var(--info)_25%,var(--border))] ' +
      'bg-[color-mix(in_oklch,var(--info)_10%,transparent)] ' +
      'text-[color-mix(in_oklch,var(--info)_92%,var(--foreground))] ' +
      'hover:bg-[color-mix(in_oklch,var(--info)_16%,transparent)]',
    dot: 'bg-[var(--info)]',
  },
  public: {
    wrap:
      'border-[color-mix(in_oklch,var(--success)_25%,var(--border))] ' +
      'bg-[color-mix(in_oklch,var(--success)_10%,transparent)] ' +
      'text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))] ' +
      'hover:bg-[color-mix(in_oklch,var(--success)_16%,transparent)]',
    dot: 'bg-[var(--success)]',
  },
};

function UrlChip({ spec }: { spec: ChipSpec }): React.ReactElement {
  const { tone, label, url, icon: Icon } = spec;
  const tc = toneClasses[tone];

  const copy = (e: React.MouseEvent<HTMLButtonElement>): void => {
    e.stopPropagation();
    e.preventDefault();
    navigator.clipboard.writeText(url).then(
      () => toast.success(`${label} URL copied`),
      () => toast.error('Clipboard blocked'),
    );
  };

  return (
    <span
      className={cn(
        'inline-flex h-7 items-center gap-1.5 rounded-full border pr-1 pl-2.5',
        'font-mono text-[10.5px] uppercase tracking-wider transition-colors',
        tc.wrap,
      )}
    >
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-full"
        aria-label={`Open ${label} URL: ${url}`}
        title={url}
      >
        {Icon ? (
          <Icon className="h-3 w-3" aria-hidden />
        ) : (
          <span className={cn('size-1.5 rounded-full', tc.dot)} aria-hidden />
        )}
        <span>{label}</span>
        <ExternalLink className="h-3 w-3 opacity-70" aria-hidden />
      </a>
      <button
        type="button"
        onClick={copy}
        aria-label={`Copy ${label} URL`}
        className={cn(
          'inline-flex size-5 items-center justify-center rounded-full',
          'text-current/70 hover:bg-background/60 hover:text-current',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        )}
      >
        <Copy className="h-3 w-3" />
      </button>
    </span>
  );
}

interface UrlChipsProps {
  tool: Tool;
}

export function UrlChips({ tool }: UrlChipsProps): React.ReactElement | null {
  const chips: ChipSpec[] = [];
  if (tool.url_external) {
    chips.push({ tone: 'local', label: 'Local', url: tool.url_external });
  }
  if (tool.url_tailnet) {
    chips.push({ tone: 'tailnet', label: 'Tailnet', url: tool.url_tailnet });
  }
  if (tool.url_funnel) {
    chips.push({ tone: 'public', label: 'Public', url: tool.url_funnel, icon: Globe });
  }
  if (chips.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2 py-1">
      {chips.map((c) => (
        <UrlChip key={`${c.tone}-${c.url}`} spec={c} />
      ))}
    </div>
  );
}
