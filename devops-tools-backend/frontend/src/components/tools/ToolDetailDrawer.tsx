/**
 * Slide-in right drawer with full tool detail, live sparkline, and actions.
 * Reads selected id from the UI store; the drawer is part of the app shell.
 */
import { useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Copy,
  ExternalLink,
  FileText as DocsIcon,
  Monitor,
  RefreshCw,
  Tag as TagIcon,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
  DrawerDescription,
} from '@/components/ui/drawer';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { HealthDot } from './HealthDot';
import { HealthSparkline } from './HealthSparkline';
import { CredentialsPanel } from './CredentialsPanel';
import { UrlChips } from './UrlChips';
import { useTools } from '@/hooks/useTools';
import { useHealth } from '@/hooks/useHealth';
import { useUiStore } from '@/store/ui';
import { resolveIcon, categoryIcons } from '@/lib/icons';
import { formatLatency, timeAgo } from '@/lib/utils';
import { launchTool } from '@/lib/api';
import type { HealthStatus } from '@/types/tool';

function KeyValue({
  label,
  children,
  mono,
  copyValue,
}: {
  label: string;
  children: React.ReactNode;
  mono?: boolean;
  copyValue?: string;
}): React.ReactElement {
  const copy = (): void => {
    if (!copyValue) return;
    navigator.clipboard.writeText(copyValue).then(
      () => toast.success('Copied to clipboard'),
      () => toast.error('Clipboard blocked')
    );
  };
  return (
    <div className="grid grid-cols-[120px_1fr_auto] items-center gap-3 py-2">
      <span className="mono-caps text-muted-foreground">{label}</span>
      <span className={mono ? 'font-mono text-[12px] break-all text-foreground/90' : 'text-sm'}>
        {children}
      </span>
      {copyValue ? (
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={copy}
          aria-label={`Copy ${label}`}
          className="opacity-60 hover:opacity-100"
        >
          <Copy className="h-3.5 w-3.5" />
        </Button>
      ) : (
        <span />
      )}
    </div>
  );
}

export function ToolDetailDrawer(): React.ReactElement | null {
  const navigate = useNavigate();
  const { selectedToolId, closeDetail } = useUiStore();
  const { data: tools } = useTools();
  const { data: healthMap, reprobe } = useHealth();

  const tool = useMemo(
    () => (tools ?? []).find((t) => t.id === selectedToolId),
    [tools, selectedToolId]
  );

  const isOpen = !!selectedToolId;

  // Auto-close if the selected id no longer matches a loaded tool (stale state).
  useEffect(() => {
    if (isOpen && tools && !tool) {
      closeDetail();
    }
  }, [isOpen, tools, tool, closeDetail]);

  if (!isOpen || !tool) return null;

  const live = healthMap?.[tool.id];
  const status: HealthStatus =
    (live?.status as HealthStatus | undefined) ?? tool.health_status ?? 'unknown';
  const latency = live?.latency_ms ?? tool.latency_ms ?? null;
  const checked = live?.last_checked ?? tool.last_checked ?? null;

  const Icon = resolveIcon(tool.icon);
  const CategoryIcon = categoryIcons[tool.category] ?? Icon;

  const handleLaunch = async (): Promise<void> => {
    if (!tool.url_external) {
      toast.error('No external URL configured.');
      return;
    }
    try {
      const r = await launchTool(tool.id);
      window.open(r.redirect_url || tool.url_external, '_blank', 'noopener,noreferrer');
    } catch {
      window.open(tool.url_external, '_blank', 'noopener,noreferrer');
    }
  };

  const handleEmbed = (): void => {
    if (!tool.embed) {
      toast.error(`${tool.name} cannot be embedded.`);
      return;
    }
    closeDetail();
    navigate(`/embed/${tool.id}`);
  };

  const statusMeta = {
    healthy: { label: 'OPERATIONAL', variant: 'success' as const },
    degraded: { label: 'DEGRADED', variant: 'warning' as const },
    down: { label: 'OFFLINE', variant: 'danger' as const },
    unknown: { label: 'NO DATA', variant: 'outline' as const },
  }[status];

  return (
    <Drawer open={isOpen} onOpenChange={(o) => (!o ? closeDetail() : null)}>
      <DrawerContent>
        <DrawerHeader>
          <div className="flex items-start gap-3">
            <div className="flex size-11 shrink-0 items-center justify-center rounded-md border border-border bg-muted/60">
              <Icon className="h-5 w-5" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <DrawerTitle className="truncate">{tool.name}</DrawerTitle>
                <Badge variant={statusMeta.variant} className="shrink-0">
                  <HealthDot status={status} pulse={false} className="mr-1" />
                  {statusMeta.label}
                </Badge>
              </div>
              <DrawerDescription className="mt-0.5 flex items-center gap-1.5 font-mono text-[11px]">
                <CategoryIcon className="h-3 w-3" />
                <span className="uppercase tracking-wider">{tool.category}</span>
                <span className="text-border">/</span>
                <span>{tool.id}</span>
              </DrawerDescription>
            </div>
          </div>
        </DrawerHeader>

        <DrawerBody>
          <p className="text-sm leading-relaxed text-foreground/90">{tool.description}</p>

          {/* Sparkline card */}
          <div className="mt-5 rounded-lg border border-border bg-muted/20 p-4">
            <div className="mb-2 flex items-center justify-between">
              <div>
                <p className="mono-caps text-muted-foreground">Latency trend</p>
                <p className="mt-0.5 font-mono text-lg font-semibold tabular-nums">
                  {formatLatency(latency)}
                </p>
              </div>
              <div className="text-right">
                <p className="mono-caps text-muted-foreground">Last probe</p>
                <p className="mt-0.5 font-mono text-sm tabular-nums">{timeAgo(checked)}</p>
              </div>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => {
                  reprobe(tool.id);
                  toast.info('Re-probing…');
                }}
                aria-label="Re-probe now"
                className="text-muted-foreground hover:text-foreground"
              >
                <RefreshCw className="h-3.5 w-3.5" />
              </Button>
            </div>
            <HealthSparkline toolId={tool.id} status={status} />
          </div>

          <Separator className="my-5" />

          {/* Reachability chips — one per surfaced URL (local / tailnet /
              funnel). Rendered above the key/value block so the at-a-glance
              shortcut is the first thing a reader sees. */}
          <UrlChips tool={tool} />

          <div className="space-y-1">
            {tool.url_internal ? (
              <KeyValue label="Internal URL" mono copyValue={tool.url_internal}>
                {tool.url_internal}
              </KeyValue>
            ) : null}
            {tool.container_name ? (
              <KeyValue label="Container" mono copyValue={tool.container_name}>
                {tool.container_name}
              </KeyValue>
            ) : null}
            {tool.compose_project ? (
              <KeyValue label="Compose" mono>
                {tool.compose_project}
              </KeyValue>
            ) : null}
            {tool.credentials ? (
              <KeyValue label="Credentials" mono>
                {tool.credentials}
              </KeyValue>
            ) : null}
            {tool.docs_url ? (
              <KeyValue label="Docs" mono copyValue={tool.docs_url}>
                {tool.docs_url}
              </KeyValue>
            ) : null}
          </div>

          {/* Vault-backed reveal panel. Renders nothing if the tool has no
              `credentials` pointer; otherwise shows a collapsed lock that
              expands on demand. Complements the pointer shown in the
              KeyValue block above. */}
          <CredentialsPanel tool={tool} />

          {tool.tags.length > 0 ? (
            <>
              <Separator className="my-5" />
              <div className="flex items-center gap-2">
                <TagIcon className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="mono-caps text-muted-foreground">Tags</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {tool.tags.map((t) => (
                  <Badge key={t} variant="mono">
                    {t}
                  </Badge>
                ))}
              </div>
            </>
          ) : null}
        </DrawerBody>

        <DrawerFooter>
          <div className="flex items-center gap-1.5">
            {tool.docs_url ? (
              <Button variant="outline" size="sm" asChild>
                <a href={tool.docs_url} target="_blank" rel="noreferrer">
                  <DocsIcon className="h-3.5 w-3.5" />
                  Docs
                </a>
              </Button>
            ) : null}
            {tool.embed ? (
              <Button variant="outline" size="sm" onClick={handleEmbed}>
                <Monitor className="h-3.5 w-3.5" />
                Embed
              </Button>
            ) : null}
          </div>
          <Button size="sm" onClick={handleLaunch} disabled={!tool.url_external}>
            Launch
            <ExternalLink className="h-3.5 w-3.5" />
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}
