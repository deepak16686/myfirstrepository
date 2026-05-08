import type { Tool } from '@/types/tool';
import { launchTool } from '@/lib/api';
import { classifyHostname, resolveLaunchUrl } from '@/lib/urls';

function currentHostname(): string {
  return typeof window === 'undefined' ? '' : window.location.hostname;
}

function isPublicDeepakUrl(url: string): boolean {
  try {
    const { hostname } = new URL(url);
    return hostname === 'deepaksharma.live' || hostname.endsWith('.deepaksharma.live');
  } catch {
    return false;
  }
}

export function resolveCurrentLaunchUrl(tool: Tool): string | null {
  return resolveLaunchUrl(tool, classifyHostname(currentHostname()));
}

export async function openToolLaunch(tool: Tool): Promise<boolean> {
  const context = classifyHostname(currentHostname());
  const fallback = resolveLaunchUrl(tool, context);
  if (!fallback) return false;

  try {
    const response = await launchTool(tool.id);
    const redirectUrl = response.redirect_url?.trim() || fallback;
    if (context === 'public' && !isPublicDeepakUrl(redirectUrl)) {
      window.open(fallback, '_blank', 'noopener,noreferrer');
      return true;
    }
    window.open(redirectUrl, '_blank', 'noopener,noreferrer');
    return true;
  } catch {
    window.open(fallback, '_blank', 'noopener,noreferrer');
    return true;
  }
}
