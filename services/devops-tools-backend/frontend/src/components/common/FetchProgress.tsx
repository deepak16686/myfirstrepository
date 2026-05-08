/* Thin top progress bar — animates while any TanStack Query is refetching. */
import { useIsFetching, useIsMutating } from '@tanstack/react-query';
import { cn } from '@/lib/utils';

export function FetchProgress({ className }: { className?: string }): React.ReactElement {
  const fetching = useIsFetching();
  const mutating = useIsMutating();
  const active = fetching + mutating > 0;

  return (
    <div
      aria-hidden
      className={cn(
        'pointer-events-none fixed left-0 right-0 top-0 z-[60] h-[3px] overflow-hidden',
        className
      )}
    >
      <div
        className={cn(
          'h-full origin-left transition-opacity duration-300',
          active ? 'opacity-100' : 'opacity-0'
        )}
        style={{
          background:
            'linear-gradient(90deg, transparent, color-mix(in oklch, var(--accent-signal) 75%, transparent), color-mix(in oklch, var(--accent-signal-alt) 80%, transparent), transparent)',
          animation: active
            ? 'progress-indeterminate 1.2s ease-in-out infinite'
            : undefined,
          boxShadow: active
            ? '0 0 8px color-mix(in oklch, var(--accent-signal) 60%, transparent)'
            : undefined,
        }}
      />
    </div>
  );
}
