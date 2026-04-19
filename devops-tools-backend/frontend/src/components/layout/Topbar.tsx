/* Topbar — command input, palette trigger, rail toggle, tailscale chip,
 * theme switcher, account chip. Sticky-blurred, lives above the status rail. */
import { Bell, User2, Signal, SignalZero } from 'lucide-react';
import { CommandBar } from '@/components/common/CommandBar';
import { ThemeToggle } from '@/components/common/ThemeToggle';
import { TailscaleChip } from '@/components/common/TailscaleChip';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn, modKey } from '@/lib/utils';
import { useUiStore } from '@/store/ui';

export function Topbar({ className }: { className?: string }): React.ReactElement {
  const openPalette = useUiStore((s) => s.openPalette);
  const toggleStatusRail = useUiStore((s) => s.toggleStatusRail);
  const railVisible = useUiStore((s) => s.statusRailVisible);
  const mk = modKey();

  return (
    <header
      className={cn(
        'sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-background/80 px-4 backdrop-blur-md sm:px-6',
        'glass',
        className
      )}
    >
      <CommandBar className="min-w-0 flex-1" />

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={openPalette}
            className="hidden h-8 shrink-0 items-center gap-1.5 border-border/70 bg-card/60 px-2 font-mono text-[11px] uppercase tracking-wider text-muted-foreground hover:text-foreground md:inline-flex"
            aria-label="Open command palette"
          >
            <span>Command</span>
            <kbd className="flex items-center gap-0.5 rounded border border-border bg-muted/60 px-1 py-0.5 text-[10px] text-foreground/80">
              <span>{mk}</span>
              <span>K</span>
            </kbd>
          </Button>
        </TooltipTrigger>
        <TooltipContent>Command palette · {mk}K</TooltipContent>
      </Tooltip>

      <div className="flex shrink-0 items-center gap-2">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={toggleStatusRail}
              aria-pressed={railVisible}
              aria-label={railVisible ? 'Hide status rail' : 'Show status rail'}
              className={cn(
                'text-muted-foreground hover:text-foreground',
                railVisible && 'text-foreground'
              )}
            >
              {railVisible ? (
                <Signal className="h-4 w-4" />
              ) : (
                <SignalZero className="h-4 w-4" />
              )}
            </Button>
          </TooltipTrigger>
          <TooltipContent>{railVisible ? 'Hide' : 'Show'} status rail</TooltipContent>
        </Tooltip>

        <TailscaleChip />
        <Separator orientation="vertical" className="h-5" />
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Notifications"
              className="relative text-muted-foreground hover:text-foreground"
            >
              <Bell className="h-4 w-4" />
              <span className="absolute right-1.5 top-1.5 size-1.5 rounded-full bg-[var(--warning)]" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>No new alerts</TooltipContent>
        </Tooltip>
        <ThemeToggle />
        <Separator orientation="vertical" className="h-5" />
        <Button
          variant="outline"
          size="sm"
          className="gap-2"
          aria-label="Account"
          title="Tailscale-authenticated operator"
        >
          <span className="flex size-6 items-center justify-center rounded-full bg-muted text-foreground">
            <User2 className="h-3 w-3" />
          </span>
          <span className="hidden font-mono text-[11px] uppercase tracking-wider sm:inline">
            operator
          </span>
        </Button>
      </div>
    </header>
  );
}
