import { cn } from '@/lib/utils';

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      data-slot="skeleton"
      className={cn(
        'relative overflow-hidden rounded-md bg-muted/60',
        'before:absolute before:inset-0 before:-translate-x-full',
        'before:bg-linear-to-r before:from-transparent before:via-foreground/5 before:to-transparent',
        'before:animate-[shimmer_1.8s_linear_infinite]',
        className
      )}
      {...props}
    />
  );
}

export { Skeleton };
