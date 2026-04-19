import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium tracking-wide transition-colors focus:outline-hidden focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background',
  {
    variants: {
      variant: {
        default:
          'border-transparent bg-primary/15 text-primary',
        secondary:
          'border-transparent bg-secondary text-secondary-foreground',
        outline: 'border-border text-muted-foreground',
        success:
          'border-transparent bg-[color-mix(in_oklch,var(--success)_18%,transparent)] text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))]',
        warning:
          'border-transparent bg-[color-mix(in_oklch,var(--warning)_20%,transparent)] text-[color-mix(in_oklch,var(--warning)_90%,var(--foreground))]',
        danger:
          'border-transparent bg-[color-mix(in_oklch,var(--destructive)_20%,transparent)] text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))]',
        info:
          'border-transparent bg-[color-mix(in_oklch,var(--info)_18%,transparent)] text-[color-mix(in_oklch,var(--info)_92%,var(--foreground))]',
        mono:
          'border-border bg-muted/40 text-foreground font-mono tracking-wider uppercase text-[10px]',
      },
    },
    defaultVariants: { variant: 'default' },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps): React.ReactElement {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
