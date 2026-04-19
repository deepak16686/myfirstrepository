import { Toaster as SonnerToaster, type ToasterProps } from 'sonner';

/**
 * Themed Sonner toaster; keeps shadcn tokens.
 * We don't use next-themes provider (we have our own), so force theme via CSS vars.
 */
function Toaster(props: ToasterProps): React.ReactElement {
  return (
    <SonnerToaster
      position="bottom-right"
      richColors
      closeButton
      toastOptions={{
        classNames: {
          toast:
            'group toast group-[.toaster]:bg-card group-[.toaster]:text-foreground group-[.toaster]:border-border group-[.toaster]:shadow-lg',
          description: 'group-[.toast]:text-muted-foreground',
          actionButton: 'group-[.toast]:bg-primary group-[.toast]:text-primary-foreground',
          cancelButton: 'group-[.toast]:bg-muted group-[.toast]:text-muted-foreground',
        },
      }}
      {...props}
    />
  );
}

export { Toaster };
