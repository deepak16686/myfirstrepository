/* ?-triggered keyboard shortcut overlay. Source of truth is GlobalShortcuts.tsx. */
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useUiStore } from '@/store/ui';
import { cn, modKey } from '@/lib/utils';
import { Keyboard } from 'lucide-react';

interface ShortcutItem {
  keys: string[];
  label: string;
  detail?: string;
}

interface ShortcutSection {
  title: string;
  items: ShortcutItem[];
}

function useSections(): ShortcutSection[] {
  const mk = modKey();
  return [
    {
      title: 'Navigation',
      items: [
        { keys: ['g', 'd'], label: 'Go to Overview' },
        { keys: ['g', 't'], label: 'Go to Tools' },
        { keys: ['g', 'p'], label: 'Go to Pipelines' },
        { keys: ['g', 'c'], label: 'Go to AI Chat' },
      ],
    },
    {
      title: 'Global',
      items: [
        { keys: [mk, 'K'], label: 'Command palette', detail: 'Search everything, run actions, launch tools' },
        { keys: ['/'], label: 'Focus search bar' },
        { keys: ['?'], label: 'Open this shortcut reference' },
        { keys: ['Esc'], label: 'Close the topmost overlay / drawer' },
      ],
    },
    {
      title: 'Layout',
      items: [
        { keys: ['\\'], label: 'Collapse / expand sidebar' },
        { keys: ['t'], label: 'Toggle dark / light theme' },
        { keys: [mk, 'Shift', 'R'], label: 'Refresh all queries' },
      ],
    },
    {
      title: 'Command palette modifiers',
      items: [
        { keys: ['Enter'], label: 'Launch in a new tab' },
        { keys: [mk, 'Enter'], label: 'Embed inside portal (if supported)' },
        { keys: ['Alt', 'Enter'], label: 'Open detail drawer' },
      ],
    },
  ];
}

function Kbd({ children }: { children: React.ReactNode }): React.ReactElement {
  return (
    <kbd
      className={cn(
        'inline-flex h-6 min-w-[24px] items-center justify-center rounded-md border border-border bg-muted/60 px-1.5',
        'font-mono text-[11px] uppercase tracking-wider text-foreground/90',
        'shadow-[inset_0_-1px_0_color-mix(in_oklch,var(--border)_70%,transparent)]'
      )}
    >
      {children}
    </kbd>
  );
}

export function ShortcutsDialog(): React.ReactElement {
  const open = useUiStore((s) => s.shortcutsOpen);
  const close = useUiStore((s) => s.closeShortcuts);
  const sections = useSections();

  return (
    <Dialog open={open} onOpenChange={(o) => (!o ? close() : null)}>
      <DialogContent className="max-w-[640px] p-0">
        <DialogHeader className="border-b border-border px-6 py-4">
          <div className="flex items-center gap-2.5">
            <span className="flex size-8 items-center justify-center rounded-md border border-border bg-muted/60">
              <Keyboard className="h-4 w-4" />
            </span>
            <div>
              <DialogTitle>Keyboard shortcuts</DialogTitle>
              <DialogDescription className="mt-0.5">
                Navigate the portal without touching the mouse.
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="max-h-[70vh] overflow-y-auto px-6 py-4">
          {sections.map((s) => (
            <section key={s.title} className="mb-6 last:mb-2">
              <h3 className="mono-caps mb-2 text-muted-foreground">{s.title}</h3>
              <ul className="divide-y divide-border/60 overflow-hidden rounded-lg border border-border">
                {s.items.map((it) => (
                  <li
                    key={it.label}
                    className="flex items-center gap-3 px-4 py-2.5 hover:bg-muted/30"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{it.label}</p>
                      {it.detail ? (
                        <p className="truncate font-mono text-[11px] text-muted-foreground">
                          {it.detail}
                        </p>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      {it.keys.map((k, i) => (
                        <span key={`${k}-${i}`} className="flex items-center gap-1">
                          <Kbd>{k}</Kbd>
                          {i < it.keys.length - 1 ? (
                            <span className="font-mono text-[10px] text-muted-foreground">+</span>
                          ) : null}
                        </span>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))}
          <p className="mono-caps pt-2 text-muted-foreground/70">
            Press <Kbd>Esc</Kbd> to close
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
