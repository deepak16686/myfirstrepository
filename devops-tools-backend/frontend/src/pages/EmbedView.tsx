/**
 * Iframe embed wrapper. Only tools with `embed: true` may be shown here;
 * otherwise we force the user out to an external tab.
 */
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, ExternalLink, Maximize2, Minimize2, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useTool } from '@/hooks/useTools';
import { resolveIcon } from '@/lib/icons';
import { HealthDot } from '@/components/tools/HealthDot';

export function EmbedView(): React.ReactElement {
  const { toolId } = useParams<{ toolId: string }>();
  const navigate = useNavigate();
  const { data: tool, isLoading, isError } = useTool(toolId);
  const [loading, setLoading] = useState(true);
  const [fs, setFs] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const frameRef = useRef<HTMLIFrameElement>(null);

  useEffect(() => {
    // If tool is loaded and not embeddable, bounce externally.
    if (!tool) return;
    if (!tool.embed) {
      if (tool.url_external) {
        window.open(tool.url_external, '_blank', 'noopener,noreferrer');
      }
      navigate('/tools', { replace: true });
    }
  }, [tool, navigate]);

  const src = tool?.url_external ?? undefined;
  const Icon = resolveIcon(tool?.icon);

  return (
    <div
      className={`flex flex-col gap-3 ${
        fs ? 'fixed inset-0 z-40 bg-background p-4' : ''
      }`}
    >
      {/* Sub-header */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-2.5">
        <div className="flex min-w-0 items-center gap-3">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => navigate(-1)}
            aria-label="Back"
            className="text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="flex min-w-0 items-center gap-2">
            <div className="flex size-8 items-center justify-center rounded-md border border-border bg-muted/50">
              <Icon className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              {isLoading ? (
                <Skeleton className="h-4 w-40" />
              ) : isError || !tool ? (
                <p className="text-sm font-semibold">Unknown tool</p>
              ) : (
                <p className="truncate text-sm font-semibold">{tool.name}</p>
              )}
              {tool ? (
                <p className="truncate font-mono text-[11px] text-muted-foreground">
                  embed · {tool.url_external}
                </p>
              ) : null}
            </div>
          </div>
          {tool ? (
            <Badge variant="mono" className="hidden sm:inline-flex">
              <HealthDot status={tool.health_status ?? 'unknown'} pulse={false} className="mr-1" />
              {(tool.health_status ?? 'unknown').toUpperCase()}
            </Badge>
          ) : null}
        </div>

        <div className="flex items-center gap-1.5">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setReloadKey((k) => k + 1)}
            aria-label="Reload iframe"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Reload
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setFs((v) => !v)}
            aria-label={fs ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {fs ? (
              <Minimize2 className="h-3.5 w-3.5" />
            ) : (
              <Maximize2 className="h-3.5 w-3.5" />
            )}
            {fs ? 'Exit' : 'Fullscreen'}
          </Button>
          {tool?.url_external ? (
            <Button size="sm" asChild>
              <a href={tool.url_external} target="_blank" rel="noreferrer">
                Open external
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </Button>
          ) : null}
        </div>
      </div>

      {/* Frame */}
      <div
        className={`relative flex-1 overflow-hidden rounded-lg border border-border bg-card ${
          fs ? 'min-h-0' : 'h-[calc(100dvh-220px)]'
        }`}
      >
        {loading ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-card/60 backdrop-blur-sm">
            <div className="relative size-10">
              <div className="absolute inset-0 animate-spin rounded-full border-2 border-border border-t-primary" />
            </div>
            <p className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
              loading embed…
            </p>
          </div>
        ) : null}
        {src ? (
          <iframe
            ref={frameRef}
            key={`${toolId}-${reloadKey}`}
            src={src}
            title={tool?.name ?? 'Embedded tool'}
            className="h-full w-full border-0"
            onLoad={() => setLoading(false)}
            onError={() => setLoading(false)}
            referrerPolicy="no-referrer-when-downgrade"
            sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads allow-modals"
          />
        ) : null}
      </div>
    </div>
  );
}
