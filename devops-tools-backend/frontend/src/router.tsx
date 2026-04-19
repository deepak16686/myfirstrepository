/* Router — core shell + Dashboard + Tools render eagerly (they're the fast
 * path). EmbedView, Pipelines, Chat, NotFound are code-split via React.lazy
 * so the initial bundle stays lean. Each lazy route gets a Suspense fallback
 * that matches the shell's max width and spacing. */
import { lazy, Suspense } from 'react';
import { createBrowserRouter } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';
import { Dashboard } from '@/pages/Dashboard';
import { Tools } from '@/pages/Tools';
import { Skeleton } from '@/components/ui/skeleton';

const EmbedView = lazy(() =>
  import('@/pages/EmbedView').then((m) => ({ default: m.EmbedView }))
);
const Pipelines = lazy(() =>
  import('@/pages/Pipelines').then((m) => ({ default: m.Pipelines }))
);
const Chat = lazy(() => import('@/pages/Chat').then((m) => ({ default: m.Chat })));
const NotFound = lazy(() =>
  import('@/pages/NotFound').then((m) => ({ default: m.NotFound }))
);

function PageFallback(): React.ReactElement {
  return (
    <div className="space-y-5" aria-busy="true" aria-live="polite">
      <Skeleton className="h-10 w-64 rounded-md" />
      <Skeleton className="h-[200px] w-full rounded-lg" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Skeleton className="h-[160px] rounded-lg lg:col-span-2" />
        <Skeleton className="h-[160px] rounded-lg" />
      </div>
    </div>
  );
}

function Suspended({ children }: { children: React.ReactNode }): React.ReactElement {
  return <Suspense fallback={<PageFallback />}>{children}</Suspense>;
}

export const router = createBrowserRouter([
  {
    element: <AppShell />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: '/tools', element: <Tools /> },
      {
        path: '/embed/:toolId',
        element: (
          <Suspended>
            <EmbedView />
          </Suspended>
        ),
      },
      {
        path: '/pipelines',
        element: (
          <Suspended>
            <Pipelines />
          </Suspended>
        ),
      },
      {
        path: '/chat',
        element: (
          <Suspended>
            <Chat />
          </Suspended>
        ),
      },
      {
        path: '*',
        element: (
          <Suspended>
            <NotFound />
          </Suspended>
        ),
      },
    ],
  },
]);
