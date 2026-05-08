import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  className?: string;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: PageHeaderProps): React.ReactElement {
  return (
    <header
      className={cn(
        'flex flex-col gap-4 pb-6 sm:flex-row sm:items-end sm:justify-between sm:gap-6',
        className
      )}
    >
      <div className="min-w-0 space-y-1.5">
        {eyebrow ? (
          <p className="mono-caps text-muted-foreground">
            <span className="mr-2 inline-block size-1.5 translate-y-[-2px] rounded-full bg-primary" />
            {eyebrow}
          </p>
        ) : null}
        <h1 className="text-[28px] font-semibold leading-tight tracking-tight sm:text-[32px]">
          {title}
        </h1>
        {description ? (
          <p className="max-w-2xl text-sm text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </header>
  );
}
