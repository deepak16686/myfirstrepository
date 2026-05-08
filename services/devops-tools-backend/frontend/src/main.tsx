import { StrictMode, lazy, Suspense } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Toaster } from '@/components/ui/sonner';
import { ShortcutsDialog } from '@/components/common/ShortcutsDialog';
import { FetchProgress } from '@/components/common/FetchProgress';
import App from './App';
import './index.css';

// React Query devtools are dev-only — kept out of the production bundle.
const ReactQueryDevtools = import.meta.env.DEV
  ? lazy(() =>
      import('@tanstack/react-query-devtools').then((m) => ({ default: m.ReactQueryDevtools }))
    )
  : null;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      retryDelay: (attempt: number) => Math.min(1000 * 2 ** attempt, 8000),
      refetchOnWindowFocus: false,
      staleTime: 10_000,
    },
    mutations: { retry: 0 },
  },
});

const el = document.getElementById('root');
if (!el) throw new Error('root element missing');

createRoot(el).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delayDuration={150} skipDelayDuration={300}>
        <FetchProgress />
        <App />
        <ShortcutsDialog />
        <Toaster />
        {ReactQueryDevtools ? (
          <Suspense fallback={null}>
            <ReactQueryDevtools buttonPosition="bottom-left" initialIsOpen={false} />
          </Suspense>
        ) : null}
      </TooltipProvider>
    </QueryClientProvider>
  </StrictMode>
);
