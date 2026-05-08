/**
 * CredentialsPopover — click-to-reveal credentials panel attached to a
 * per-card key icon. Shares the same backend contract as the full
 * `CredentialsPanel` (see src/components/tools/CredentialsPanel.tsx) but
 * renders as a floating popover anchored to the trigger button so the
 * card grid stays at a fixed height.
 *
 * State machine (mirrors the full panel for UX parity):
 *   locked ──click──▶ has token? ── yes ─▶ fetch ──▶ revealed
 *                         │
 *                         └── no ─▶ token-entry ──submit──▶ fetch ──▶ revealed
 *
 *   revealed ──lock──▶ locked (token cached)
 *   fetch 401/403 ──▶ purge token, back to token-entry + toast
 *   fetch 503 ──▶ close popover + toast "Credentials endpoint not configured"
 *
 * Implementation:
 *   - Custom popover (not Radix) so we don't add a dependency; click-outside
 *     + Esc close semantics, focus trap on the text input while open.
 *   - Rendered in a portal so cards don't clip. Positioned near the right
 *     edge of the anchor with automatic flip above-vs-below based on
 *     viewport space.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useMutation } from '@tanstack/react-query';
import {
  Copy,
  Eye,
  EyeOff,
  KeyRound,
  Lock,
  LockOpen,
  ShieldAlert,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import type { CredentialsResponse, Tool } from '@/types/tool';
import { ApiError, fetchCredentials } from '@/lib/api';
import { useUiStore } from '@/store/ui';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn, timeAgo } from '@/lib/utils';

/** Shared "is there a credentials pointer" check — treats 'none' / 'n/a' /
 *  empty string as "no credentials stored". */
export function hasCredentials(tool: Tool): boolean {
  const raw = tool.credentials;
  if (!raw) return false;
  const v = raw.trim().toLowerCase();
  if (v === '' || v === 'none' || v === 'n/a' || v === 'null') return false;
  return true;
}

/** Single row in the revealed panel. Value is masked until hovered / eye
 *  toggle; copy always works regardless of visibility. */
function MaskedRow({ label, value }: { label: string; value: string }): React.ReactElement {
  const [visible, setVisible] = useState(false);

  const copy = (): void => {
    navigator.clipboard.writeText(value).then(
      () => toast.success(`Copied ${label}`),
      () => toast.error('Clipboard blocked'),
    );
  };

  return (
    <div className="grid grid-cols-[90px_1fr_auto_auto] items-center gap-2 border-b border-border/40 py-1.5 last:border-b-0">
      <span className="mono-caps text-muted-foreground">{label}</span>
      <span
        className={cn(
          'truncate font-mono text-[11.5px] break-all text-foreground/90',
          'cursor-text select-text',
          !visible && 'tracking-[0.22em]',
        )}
        aria-label={visible ? `${label} value revealed` : `${label} value hidden`}
      >
        {visible ? value : '••••••••••••'}
      </span>
      <Button
        variant="ghost"
        size="icon-sm"
        type="button"
        aria-label={visible ? `Hide ${label}` : `Show ${label}`}
        className="size-6 opacity-70 hover:opacity-100"
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
        onFocus={() => setVisible(true)}
        onBlur={() => setVisible(false)}
        onClick={() => setVisible((v) => !v)}
      >
        {visible ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
      </Button>
      <Button
        variant="ghost"
        size="icon-sm"
        type="button"
        aria-label={`Copy ${label}`}
        className="size-6 opacity-70 hover:opacity-100"
        onClick={copy}
      >
        <Copy className="h-3 w-3" />
      </Button>
    </div>
  );
}

interface CredentialsPopoverProps {
  tool: Tool;
  open: boolean;
  anchor: HTMLElement | null;
  onClose: () => void;
}

/**
 * The popover body, portalled to document.body and positioned below (or
 * above) the trigger. Only mounted when `open` is true so the DOM stays
 * lean for the grid.
 */
export function CredentialsPopover({
  tool,
  open,
  anchor,
  onClose,
}: CredentialsPopoverProps): React.ReactElement | null {
  const operatorToken = useUiStore((s) => s.operatorToken);
  const setOperatorToken = useUiStore((s) => s.setOperatorToken);

  const [tokenDraft, setTokenDraft] = useState('');
  const [revealed, setRevealed] = useState<CredentialsResponse | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number; width: number } | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const mutation = useMutation<
    CredentialsResponse | null,
    Error,
    { token: string }
  >({
    mutationFn: async ({ token }) => fetchCredentials(tool.id, token),
    onSuccess: (data) => {
      if (data === null) {
        toast.info('No credentials stored for this tool.');
        onClose();
        return;
      }
      setRevealed(data);
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        if (err.status === 401 || err.status === 403) {
          setOperatorToken(null);
          setTokenDraft('');
          toast.error(err.message);
          return;
        }
        if (err.status === 503) {
          toast.error('Credentials endpoint not configured on backend');
          onClose();
          return;
        }
        toast.error(err.message);
        return;
      }
      toast.error('Failed to fetch credentials');
    },
  });

  const fieldList = useMemo(
    () =>
      revealed
        ? Object.entries(revealed.fields).sort(([a], [b]) => a.localeCompare(b))
        : [],
    [revealed],
  );

  // Auto-fire the mutation when the popover opens and we already have a token.
  // Guarded so it only runs once per open cycle.
  const firedRef = useRef(false);
  useEffect(() => {
    if (!open) {
      firedRef.current = false;
      setRevealed(null);
      setTokenDraft('');
      mutation.reset();
      return;
    }
    if (open && !firedRef.current && operatorToken && !revealed) {
      firedRef.current = true;
      mutation.mutate({ token: operatorToken });
    }
    // We intentionally exclude `mutation` and `revealed` here so we don't
    // re-fire on every state change; we only want the one-shot "popover
    // just opened and we have a token" behaviour.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, operatorToken]);

  // Position the popover relative to the anchor.
  useEffect(() => {
    if (!open || !anchor) return;
    const computePosition = (): void => {
      const rect = anchor.getBoundingClientRect();
      const panelW = 340;
      const panelH = panelRef.current?.getBoundingClientRect().height ?? 200;
      const marginX = 12;
      const marginY = 8;
      let left = rect.right - panelW;
      if (left < marginX) left = marginX;
      if (left + panelW > window.innerWidth - marginX)
        left = window.innerWidth - panelW - marginX;
      // Prefer below the anchor; flip above if near viewport bottom.
      const below = rect.bottom + marginY + panelH <= window.innerHeight - 8;
      const top = below ? rect.bottom + marginY : rect.top - marginY - panelH;
      setPos({ top, left, width: panelW });
    };
    computePosition();
    window.addEventListener('resize', computePosition);
    window.addEventListener('scroll', computePosition, true);
    return () => {
      window.removeEventListener('resize', computePosition);
      window.removeEventListener('scroll', computePosition, true);
    };
  }, [open, anchor, revealed]);

  // Click-outside + Esc close.
  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent): void => {
      const t = e.target as Node | null;
      if (!t) return;
      if (panelRef.current && panelRef.current.contains(t)) return;
      if (anchor && anchor.contains(t)) return;
      onClose();
    };
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open, anchor, onClose]);

  const onSubmitToken = (e: React.FormEvent<HTMLFormElement>): void => {
    e.preventDefault();
    const t = tokenDraft.trim();
    if (!t) return;
    setOperatorToken(t);
    mutation.mutate({ token: t });
  };

  const onRelock = (): void => {
    setRevealed(null);
    mutation.reset();
  };

  if (!open || typeof document === 'undefined') return null;

  const isPending = mutation.isPending;

  const body = (
    <div
      ref={panelRef}
      role="dialog"
      aria-modal="false"
      aria-label={`Credentials for ${tool.name}`}
      className={cn(
        'fixed z-[80] overflow-hidden rounded-lg border border-border',
        'bg-popover text-popover-foreground shadow-[0_18px_48px_-18px_rgba(0,0,0,0.55),0_0_0_1px_color-mix(in_oklch,var(--accent-signal)_18%,transparent)]',
        'animate-in fade-in-0 zoom-in-95 duration-150',
      )}
      style={
        pos
          ? { top: pos.top, left: pos.left, width: pos.width }
          : { top: -9999, left: -9999, width: 340, visibility: 'hidden' }
      }
      onClick={(e) => e.stopPropagation()}
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border bg-muted/25 px-3 py-2">
        <div className="flex items-center gap-2">
          {revealed ? (
            <LockOpen className="h-3.5 w-3.5 text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))]" />
          ) : (
            <KeyRound className="h-3.5 w-3.5 text-muted-foreground" />
          )}
          <p className="mono-caps text-foreground/80">
            {revealed ? 'Credentials · unlocked' : 'Credentials · vault'}
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Close credentials popover"
          onClick={onClose}
          className="size-6 opacity-70 hover:opacity-100"
        >
          <X className="h-3 w-3" />
        </Button>
      </div>

      {/* Body */}
      <div className="px-3 py-3">
        {revealed ? (
          <>
            <div className="rounded-md border border-border/60 bg-background/60 px-2">
              {fieldList.length === 0 ? (
                <p className="py-2 text-[11px] text-muted-foreground">
                  Vault returned an empty field map.
                </p>
              ) : (
                fieldList.map(([k, v]) => <MaskedRow key={k} label={k} value={v} />)
              )}
            </div>
            <div className="mt-3 flex items-center justify-between gap-2">
              <p className="font-mono text-[10px] text-muted-foreground">
                from <span className="text-foreground/80">{revealed.source}</span> ·{' '}
                {timeAgo(revealed.retrieved_at)}
              </p>
              <Button
                size="sm"
                variant="outline"
                type="button"
                onClick={onRelock}
                className="h-6 gap-1 px-2 text-[10px]"
                aria-label="Re-lock credentials"
              >
                <Lock className="h-3 w-3" />
                Re-lock
              </Button>
            </div>
          </>
        ) : (
          <>
            <p className="text-[11.5px] text-muted-foreground">
              Pointer:{' '}
              <span className="font-mono text-foreground/80">{tool.credentials}</span>
            </p>
            {operatorToken ? (
              <p className="mt-2 text-[11px] text-muted-foreground">
                {isPending ? 'Fetching credentials…' : 'Ready. Tap Reveal to decrypt.'}
              </p>
            ) : (
              <form onSubmit={onSubmitToken} className="mt-3 flex items-center gap-2">
                <label htmlFor={`creds-token-${tool.id}`} className="sr-only">
                  Operator token
                </label>
                <Input
                  id={`creds-token-${tool.id}`}
                  type="password"
                  autoComplete="off"
                  autoCapitalize="off"
                  spellCheck={false}
                  placeholder="Operator token"
                  value={tokenDraft}
                  onChange={(e) => setTokenDraft(e.target.value)}
                  className="h-7 text-[12px]"
                  disabled={isPending}
                  autoFocus
                />
                <Button
                  size="sm"
                  type="submit"
                  disabled={isPending || !tokenDraft.trim()}
                  className="h-7 px-2 text-[11px]"
                >
                  Unlock
                </Button>
              </form>
            )}

            {operatorToken ? (
              <div className="mt-3 flex items-center justify-end gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  type="button"
                  className="h-7 gap-1 px-2 text-[11px]"
                  onClick={() => {
                    firedRef.current = true;
                    mutation.mutate({ token: operatorToken });
                  }}
                  disabled={isPending}
                >
                  <KeyRound className="h-3 w-3" />
                  {isPending ? 'Unlocking…' : 'Reveal'}
                </Button>
              </div>
            ) : null}

            {mutation.isError ? (
              <p className="mt-2 flex items-center gap-1.5 text-[11px] text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))]">
                <ShieldAlert className="h-3 w-3" aria-hidden />
                <span>{mutation.error.message}</span>
              </p>
            ) : null}
          </>
        )}
      </div>
    </div>
  );

  return createPortal(body, document.body);
}
