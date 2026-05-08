/**
 * Search input for the topbar. The "/" shortcut focuses it; Esc clears focus.
 * Writes to URL ?q= so that /tools can read it and filter.
 */
import { useEffect, useRef } from 'react';
import { Search, Command } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { cn } from '@/lib/utils';

export function CommandBar({ className }: { className?: string }): React.ReactElement {
  const [params, setParams] = useSearchParams();
  const inputRef = useRef<HTMLInputElement>(null);
  const q = params.get('q') ?? '';

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === '/') {
        const tag = (e.target as HTMLElement | null)?.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA') return;
        e.preventDefault();
        inputRef.current?.focus();
      }
      if (e.key === 'Escape' && document.activeElement === inputRef.current) {
        inputRef.current?.blur();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <label
      className={cn(
        'relative flex h-9 w-full max-w-[420px] items-center gap-2 rounded-md border border-border bg-muted/40 px-3',
        'transition-colors focus-within:border-ring focus-within:bg-card',
        className
      )}
    >
      <Search className="h-4 w-4 text-muted-foreground" aria-hidden />
      <input
        ref={inputRef}
        type="search"
        value={q}
        placeholder="Search tools, tags, categories…"
        aria-label="Search"
        onChange={(e) => {
          const next = new URLSearchParams(params);
          if (e.target.value) next.set('q', e.target.value);
          else next.delete('q');
          setParams(next, { replace: true });
        }}
        className="h-full w-full bg-transparent text-sm outline-hidden placeholder:text-muted-foreground/80"
      />
      <kbd className="hidden items-center gap-1 rounded border border-border bg-background/70 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground md:inline-flex">
        <Command className="h-2.5 w-2.5" />/
      </kbd>
    </label>
  );
}
