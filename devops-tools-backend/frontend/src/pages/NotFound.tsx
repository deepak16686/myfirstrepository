import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Home } from 'lucide-react';
import { Button } from '@/components/ui/button';

export function NotFound(): React.ReactElement {
  const navigate = useNavigate();
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 text-center">
      <div className="relative">
        <div className="absolute inset-0 -z-10 flex items-center justify-center">
          <div className="h-40 w-40 rounded-full bg-[radial-gradient(ellipse_at_center,color-mix(in_oklch,var(--primary)_20%,transparent),transparent_70%)]" />
        </div>
        <p className="font-mono text-[120px] font-bold leading-none tracking-tighter text-foreground/15 sm:text-[180px]">
          404
        </p>
      </div>
      <div className="max-w-md space-y-2">
        <h1 className="text-2xl font-semibold">Route not found</h1>
        <p className="text-sm text-muted-foreground">
          The URL you requested is not in the portal's routing table. Use the sidebar to jump to
          Overview, Tools, Pipelines or Chat.
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Button variant="outline" onClick={() => navigate(-1)}>
          <ArrowLeft className="h-3.5 w-3.5" />
          Go back
        </Button>
        <Button asChild>
          <Link to="/">
            <Home className="h-3.5 w-3.5" />
            Overview
          </Link>
        </Button>
      </div>
    </div>
  );
}
