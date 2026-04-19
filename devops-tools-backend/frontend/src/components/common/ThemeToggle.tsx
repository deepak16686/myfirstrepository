/* Theme switcher — Light / Dark / System / Cyberpunk. Keeps the icon in sync
 * with the resolved theme so the trigger is always a truthful glyph. */
import { Moon, Sun, Monitor, Sparkles } from 'lucide-react';
import { useTheme, type Theme } from '@/hooks/useTheme';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';

const OPTIONS: { v: Theme; label: string; icon: typeof Sun; hint: string }[] = [
  { v: 'light', label: 'Light', icon: Sun, hint: 'crisp · paper-grain' },
  { v: 'dark', label: 'Dark', icon: Moon, hint: 'nocturnal · default' },
  { v: 'system', label: 'System', icon: Monitor, hint: 'follow OS setting' },
  { v: 'cyberpunk', label: 'Cyberpunk', icon: Sparkles, hint: 'neon · maximal signal' },
];

export function ThemeToggle(): React.ReactElement {
  const { theme, resolved, isCyberpunk, setTheme } = useTheme();
  const TriggerIcon = isCyberpunk ? Sparkles : resolved === 'dark' ? Moon : Sun;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={`Theme: ${theme} (${resolved})`}
          className="relative text-muted-foreground hover:text-foreground"
        >
          <TriggerIcon
            className={cn(
              'h-4 w-4 transition-transform duration-300 ease-out',
              isCyberpunk && 'text-[color-mix(in_oklch,var(--accent-signal)_85%,var(--foreground))]'
            )}
          />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>Appearance</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {OPTIONS.map(({ v, label, icon: I, hint }) => {
          const active = theme === v;
          return (
            <DropdownMenuItem
              key={v}
              onClick={() => setTheme(v)}
              className={cn(
                'flex-col items-start gap-0.5',
                active && 'bg-accent text-accent-foreground'
              )}
            >
              <div className="flex w-full items-center gap-2">
                <I className="h-4 w-4" />
                <span className="flex-1">{label}</span>
                {active ? (
                  <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    active
                  </span>
                ) : null}
              </div>
              <span className="pl-6 font-mono text-[10.5px] text-muted-foreground">
                {hint}
              </span>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
