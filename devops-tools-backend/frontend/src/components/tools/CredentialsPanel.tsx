/**
 * CredentialsPanel — vault-backed credentials reveal panel for a tool.
 *
 * Behaviour:
 *   - Returns `null` when the tool has no `credentials` pointer (or the
 *     pointer is literally `"none"`).
 *   - Starts collapsed with a lock icon.
 *   - First click prompts for the operator token if none is stored in the
 *     UI store; otherwise fires the reveal mutation immediately.
 *   - Successful reveal renders each `fields` entry as a row with the key
 *     on the left and a masked value on the right. Values show as
 *     `••••••••` and are only rendered in plaintext on hover (or when the
 *     row is focused). Clipboard copy always works, regardless of hover.
 *   - 401 / 403 clears the cached operator token (it is either missing or
 *     wrong) and surfaces a toast; the UI falls back to the token entry.
 *   - 503 surfaces a toast explaining the feature is not configured on the
 *     backend; the panel drops back to collapsed.
 *   - A "Re-lock" button clears the rendered fields (keeps the token
 *     cached — the session-long reveal is single-shot, not recurring) and
 *     resets the panel to collapsed.
 *
 * Security notes:
 *   - The operator token and credential field values are NEVER written to
 *     logs or toasts — only generic error messages.
 *   - Copy-to-clipboard uses `navigator.clipboard.writeText`; the toast
 *     success line intentionally shows only the field name, never its
 *     value.
 *   - The mutation result is held in local component state only; it is
 *     NOT persisted to the TanStack Query cache, so other components
 *     (and devtools) cannot observe the plaintext values.
 */
import { useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  Copy,
  Eye,
  EyeOff,
  KeyRound,
  Lock,
  LockOpen,
  ShieldAlert,
} from 'lucide-react';
import { toast } from 'sonner';
import type { CredentialsResponse, Tool } from '@/types/tool';
import { fetchCredentials, ApiError } from '@/lib/api';
import { useUiStore } from '@/store/ui';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn, timeAgo } from '@/lib/utils';

/** Generic "obviously-empty" sentinel used by backends to mean "no creds". */
function hasCredentials(tool: Tool): boolean {
  const raw = tool.credentials;
  if (!raw) return false;
  const v = raw.trim().toLowerCase();
  if (v === '' || v === 'none' || v === 'n/a' || v === 'null') return false;
  return true;
}

/** Single masked field row. Copy button is always active; the plaintext is
 *  only exposed on hover / focus. */
function MaskedField({
  label,
  value,
}: {
  label: string;
  value: string;
}): React.ReactElement {
  const [visible, setVisible] = useState(false);

  const copy = (): void => {
    navigator.clipboard.writeText(value).then(
      () => toast.success(`Copied ${label}`),
      () => toast.error('Clipboard blocked'),
    );
  };

  return (
    <div
      className={cn(
        'group grid grid-cols-[120px_1fr_auto_auto] items-center gap-3 py-2',
        'border-b border-border/50 last:border-b-0',
      )}
    >
      <span className="mono-caps text-muted-foreground">{label}</span>
      <span
        className={cn(
          'truncate font-mono text-[12px] break-all text-foreground/90',
          'cursor-text select-text',
          !visible && 'tracking-[0.2em]',
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
        className="opacity-60 hover:opacity-100"
        onMouseEnter={() => setVisible(true)}
        onMouseLeave={() => setVisible(false)}
        onFocus={() => setVisible(true)}
        onBlur={() => setVisible(false)}
        onClick={() => setVisible((v) => !v)}
      >
        {visible ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
      </Button>
      <Button
        variant="ghost"
        size="icon-sm"
        type="button"
        aria-label={`Copy ${label}`}
        className="opacity-60 hover:opacity-100"
        onClick={copy}
      >
        <Copy className="h-3.5 w-3.5" />
      </Button>
    </div>
  );
}

interface CredentialsPanelProps {
  tool: Tool;
}

export function CredentialsPanel({
  tool,
}: CredentialsPanelProps): React.ReactElement | null {
  const operatorToken = useUiStore((s) => s.operatorToken);
  const setOperatorToken = useUiStore((s) => s.setOperatorToken);

  const [expanded, setExpanded] = useState(false);
  const [tokenDraft, setTokenDraft] = useState('');
  const [revealed, setRevealed] = useState<CredentialsResponse | null>(null);

  const mutation = useMutation<
    CredentialsResponse | null,
    Error,
    { token: string }
  >({
    mutationFn: async ({ token }) => fetchCredentials(tool.id, token),
    onSuccess: (data) => {
      if (data === null) {
        toast.info('No credentials stored for this tool.');
        setExpanded(false);
        return;
      }
      setRevealed(data);
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        if (err.status === 401 || err.status === 403) {
          // Token is missing or wrong — purge it so the next attempt
          // prompts the operator afresh.
          setOperatorToken(null);
          setTokenDraft('');
          toast.error(err.message);
          return;
        }
        if (err.status === 503) {
          toast.error('Credentials endpoint not configured on backend');
          setExpanded(false);
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

  if (!hasCredentials(tool)) return null;

  const isPending = mutation.isPending;

  const onUnlockClick = (): void => {
    if (operatorToken) {
      mutation.mutate({ token: operatorToken });
      return;
    }
    // No token cached — expand so the input is shown.
    setExpanded(true);
  };

  const onSubmitToken = (e: React.FormEvent<HTMLFormElement>): void => {
    e.preventDefault();
    const t = tokenDraft.trim();
    if (!t) return;
    setOperatorToken(t);
    mutation.mutate({ token: t });
  };

  const onRelock = (): void => {
    setRevealed(null);
    setExpanded(false);
    mutation.reset();
  };

  // -----------------------------------------------------------------------
  // Rendered: revealed fields (success state)
  // -----------------------------------------------------------------------
  if (revealed) {
    return (
      <div
        className={cn(
          'mt-4 rounded-lg border p-4',
          'border-[color-mix(in_oklch,var(--success)_22%,var(--border))]',
          'bg-[color-mix(in_oklch,var(--success)_6%,transparent)]',
        )}
        data-testid="credentials-panel"
      >
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <LockOpen className="h-3.5 w-3.5 text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))]" />
            <span className="mono-caps text-[color-mix(in_oklch,var(--success)_92%,var(--foreground))]">
              Credentials revealed
            </span>
          </div>
          <Button
            size="sm"
            variant="outline"
            type="button"
            onClick={onRelock}
            aria-label="Re-lock credentials"
          >
            <Lock className="h-3.5 w-3.5" />
            Re-lock
          </Button>
        </div>
        <div className="rounded-md border border-border/60 bg-background/60 px-3">
          {fieldList.length === 0 ? (
            <p className="py-3 text-xs text-muted-foreground">
              Vault returned an empty field map.
            </p>
          ) : (
            fieldList.map(([k, v]) => <MaskedField key={k} label={k} value={v} />)
          )}
        </div>
        <p className="mt-3 font-mono text-[10.5px] text-muted-foreground">
          Retrieved from <span className="text-foreground/80">{revealed.source}</span>{' '}
          <span aria-hidden>·</span> {timeAgo(revealed.retrieved_at)}
        </p>
      </div>
    );
  }

  // -----------------------------------------------------------------------
  // Rendered: locked (default) state
  // -----------------------------------------------------------------------
  return (
    <div
      className={cn(
        'mt-4 rounded-lg border border-border bg-muted/25 p-4',
        'transition-colors hover:border-ring/50',
      )}
      data-testid="credentials-panel"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            className={cn(
              'flex size-8 shrink-0 items-center justify-center rounded-md',
              'border border-border bg-background text-muted-foreground',
            )}
            aria-hidden
          >
            <KeyRound className="h-4 w-4" />
          </span>
          <div>
            <p className="text-sm font-medium">Credentials stored in Vault</p>
            <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
              Click to reveal — operator token required
            </p>
          </div>
        </div>
        <Button
          size="sm"
          type="button"
          variant="outline"
          onClick={onUnlockClick}
          disabled={isPending}
          aria-label="Reveal credentials"
        >
          <Lock className="h-3.5 w-3.5" />
          {isPending ? 'Unlocking…' : 'Reveal'}
        </Button>
      </div>

      {expanded && !operatorToken ? (
        <form onSubmit={onSubmitToken} className="mt-3 flex items-center gap-2">
          <label htmlFor={`operator-token-${tool.id}`} className="sr-only">
            Operator token
          </label>
          <Input
            id={`operator-token-${tool.id}`}
            type="password"
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
            placeholder="Operator token"
            value={tokenDraft}
            onChange={(e) => setTokenDraft(e.target.value)}
            className="h-8"
            disabled={isPending}
          />
          <Button size="sm" type="submit" disabled={isPending || !tokenDraft.trim()}>
            Unlock
          </Button>
          <Button
            size="sm"
            type="button"
            variant="ghost"
            onClick={() => {
              setExpanded(false);
              setTokenDraft('');
            }}
            disabled={isPending}
          >
            Cancel
          </Button>
        </form>
      ) : null}

      {mutation.isError ? (
        <p className="mt-3 flex items-center gap-2 text-xs text-[color-mix(in_oklch,var(--destructive)_92%,var(--foreground))]">
          <ShieldAlert className="h-3.5 w-3.5" aria-hidden />
          <span>{mutation.error.message}</span>
        </p>
      ) : null}
    </div>
  );
}
