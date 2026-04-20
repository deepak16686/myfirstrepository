/**
 * Pure helpers for the "launch this tool" context-aware URL decision.
 *
 * The portal runs from three different public entry points:
 *   1. Local LAN      → user loaded http://localhost:8003 (or http://127.0.0.1:…).
 *                        The right launch URL is the tool's url_external (hits
 *                        the user's own host).
 *   2. Tailnet        → user loaded https://<host>.tail****.ts.net or one of
 *                        Tailscale's magic DNS hostnames (100.x.x.x also
 *                        qualifies). Prefer the tool's url_tailnet.
 *   3. Public funnel  → user loaded https://<tool>.deepaksharma.live via the
 *                        Tailscale Funnel. Prefer url_funnel, which is the
 *                        HTTPS Funnel endpoint that survives NAT.
 *
 * `resolveLaunchUrl` is a **pure function** — it takes the tool and the
 * hostname, and returns the best URL to open. It is framework-agnostic and
 * covered by unit tests in the same file via its callers.
 *
 * The "context" for each tool is also rendered on the card (Local / Tailnet
 * / Public chips), so the logic below is shared by the chip row and the
 * launch button to keep the two in sync.
 */
import type { Tool } from '@/types/tool';

export type LaunchContext = 'local' | 'tailnet' | 'public';

/** Classify the browser's current hostname into a launch context. */
export function classifyHostname(hostname: string | null | undefined): LaunchContext {
  const h = (hostname ?? '').toLowerCase();
  if (!h) return 'local';
  // Tailscale MagicDNS name or 100.x.x.x (CGNAT) are always tailnet.
  if (h.endsWith('.ts.net') || h.endsWith('.tailscale.net')) return 'tailnet';
  if (/^100\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.test(h)) return 'tailnet';
  // Tailscale Funnel exposes *.deepaksharma.live as the public DNS.
  if (h.endsWith('.deepaksharma.live') || h === 'deepaksharma.live') return 'public';
  // Anything else (localhost, 127.x, LAN IP, *.local) is treated as local.
  return 'local';
}

/**
 * Choose the best URL to open for this tool given the current launch
 * context. Falls through in priority order so that a tool without a funnel
 * URL still gets SOMETHING reasonable when the user is on the public origin.
 *
 * Priority per context:
 *   public  → url_funnel  > url_tailnet > url_external > url_internal
 *   tailnet → url_tailnet > url_funnel  > url_external > url_internal
 *   local   → url_external > url_tailnet > url_funnel  > url_internal
 */
export function resolveLaunchUrl(tool: Tool, context: LaunchContext): string | null {
  const internal = tool.url_internal ?? null;
  const external = tool.url_external ?? null;
  const funnel = tool.url_funnel ?? null;
  const tailnet = tool.url_tailnet ?? null;

  const order: Array<string | null> =
    context === 'public'
      ? [funnel, tailnet, external, internal]
      : context === 'tailnet'
        ? [tailnet, funnel, external, internal]
        : [external, tailnet, funnel, internal];

  for (const u of order) {
    if (u && u.length > 0) return u;
  }
  return null;
}

/**
 * Human-readable label for the chip rendered on the card. "LOCAL",
 * "TAILNET", "PUBLIC" — uppercase so it reads as a signal label.
 */
export function contextLabel(context: LaunchContext): string {
  if (context === 'public') return 'PUBLIC';
  if (context === 'tailnet') return 'TAILNET';
  return 'LOCAL';
}

/**
 * Which URL fields are available for this tool, ordered by the current
 * context. Used by the URL chip row so the user can see all three options
 * at a glance and copy whichever they need.
 */
export interface NamedUrl {
  kind: 'local' | 'tailnet' | 'public' | 'internal';
  label: string;
  url: string;
  preferredForContext: boolean;
}

export function listAvailableUrls(tool: Tool, context: LaunchContext): NamedUrl[] {
  const preferredKind =
    context === 'public' ? 'public' : context === 'tailnet' ? 'tailnet' : 'local';

  const out: NamedUrl[] = [];
  if (tool.url_external)
    out.push({
      kind: 'local',
      label: 'Local',
      url: tool.url_external,
      preferredForContext: preferredKind === 'local',
    });
  if (tool.url_tailnet)
    out.push({
      kind: 'tailnet',
      label: 'Tailnet',
      url: tool.url_tailnet,
      preferredForContext: preferredKind === 'tailnet',
    });
  if (tool.url_funnel)
    out.push({
      kind: 'public',
      label: 'Public',
      url: tool.url_funnel,
      preferredForContext: preferredKind === 'public',
    });
  // Only fall back to internal when NOTHING else is set; internal is usually
  // a container-net URL (e.g. http://redis:6379) and is not clickable from
  // the browser, so we only expose it as an informational chip.
  if (out.length === 0 && tool.url_internal) {
    out.push({
      kind: 'internal',
      label: 'Internal',
      url: tool.url_internal,
      preferredForContext: true,
    });
  }
  return out;
}
