/**
 * AI Chat — migration of the legacy chat UI, mapped onto shadcn primitives.
 * Talks to POST /api/v1/chat/ (same contract as the old app.js).
 *
 * Self-healing pipeline monitoring:
 *   When `commit_pipeline` succeeds the backend returns a
 *   `monitoring: {project_id, branch}` hint on the chat response. The
 *   chat then begins polling `GET /api/v1/pipeline/progress/{id}/{branch}`
 *   every 2 seconds and renders a live PipelineProgressCard immediately
 *   below the originating assistant message. Polling stops when the
 *   backend reports `completed===true`, status is `success`/`failed`,
 *   or 30 minutes (900 polls) have elapsed.
 *
 *   Older deploys may omit `monitoring`; we fall back to a single regex
 *   over the assistant's `message` text — see `parseMonitoringFromMessage`.
 */
import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  ArrowUp,
  Bot,
  CheckCircle2,
  Database,
  GitCommit,
  Loader2,
  RotateCw,
  Search,
  Sparkles,
  User2,
  Wrench,
  XCircle,
} from 'lucide-react';
import { toast } from 'sonner';
import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  fetchChatInflight,
  fetchPipelineProgress,
  newConversation,
  sendChat,
} from '@/lib/api';
import type { ChatInflight } from '@/lib/api';
import { cn, timeAgo } from '@/lib/utils';
import { PipelineProgressCard } from '@/components/cards/PipelineProgressCard';
import type {
  ChatGenerationInfo,
  ChatMonitoringHint,
  PipelineProgress,
} from '@/types/tool';

type Msg = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  ts: string;
};

/**
 * Per-message pipeline-monitoring slot. Stored in a `Map<msgId, target>`
 * so each assistant bubble that triggered a commit can show its own
 * progress card, even when the user fires several commits back-to-back.
 */
type MonitoringTarget = {
  project_id: number;
  branch: string;
  /** Wall-clock ms when polling started; used to enforce the 30-min cap. */
  startedAt: number;
};

/**
 * Maximum polls (2s interval × 900 = 30 min). Matches the spec.
 */
const MAX_POLL_COUNT = 900;
const POLL_INTERVAL_MS = 2000;

/**
 * Regex fallback: backend may embed `[monitoring project_id=12 branch=...]`
 * in the LLM-formatted reply for older deploys that don't yet populate
 * the structured `monitoring` field. We accept the marker with or
 * without the surrounding brackets so the LLM has flexibility.
 */
const MONITORING_RE =
  /monitoring\s+project_id\s*=\s*(\d+)\s+branch\s*=\s*([^\s\]]+)/i;

function parseMonitoringFromMessage(message: string): ChatMonitoringHint | null {
  const m = message.match(MONITORING_RE);
  if (!m) return null;
  const id = Number(m[1]);
  if (!Number.isFinite(id)) return null;
  return { project_id: id, branch: m[2] };
}

function renderMarkdown(text: string): string {
  // Lightweight markdown to HTML: code fences + inline code + bold + headings + lists + links.
  const esc = (s: string): string =>
    s.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
  const lines = text.split('\n');
  let out = '';
  let inCode: string | null = null;
  let inList: 'ul' | 'ol' | null = null;

  const closeList = (): void => {
    if (inList) {
      out += `</${inList}>`;
      inList = null;
    }
  };

  for (const line of lines) {
    const fence = line.match(/^```\s*([\w-]*)\s*$/);
    if (fence) {
      closeList();
      if (inCode === null) {
        inCode = fence[1] || '';
        out += `<pre><code class="language-${inCode}">`;
      } else {
        inCode = null;
        out += `</code></pre>`;
      }
      continue;
    }
    if (inCode !== null) {
      out += esc(line) + '\n';
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      if (inList !== 'ul') {
        closeList();
        inList = 'ul';
        out += '<ul>';
      }
      out += `<li>${inlineMd(esc(line.replace(/^\s*[-*]\s+/, '')))}</li>`;
      continue;
    }
    if (/^\s*\d+\.\s+/.test(line)) {
      if (inList !== 'ol') {
        closeList();
        inList = 'ol';
        out += '<ol>';
      }
      out += `<li>${inlineMd(esc(line.replace(/^\s*\d+\.\s+/, '')))}</li>`;
      continue;
    }
    const h = line.match(/^(#{1,3})\s+(.+)$/);
    if (h) {
      closeList();
      const level = h[1].length;
      out += `<h${level}>${inlineMd(esc(h[2]))}</h${level}>`;
      continue;
    }
    if (line.trim() === '') {
      closeList();
      out += '<br/>';
      continue;
    }
    closeList();
    out += `<p>${inlineMd(esc(line))}</p>`;
  }
  closeList();
  if (inCode !== null) out += '</code></pre>';
  return out;
}

function inlineMd(s: string): string {
  return s
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
}

export function Chat(): React.ReactElement {
  const [messages, setMessages] = useState<Msg[]>([
    {
      id: 'welcome',
      role: 'assistant',
      ts: new Date().toISOString(),
      content:
        'Hello — I am your DevOps copilot. Give me a GitLab repository URL and I will generate an appropriate Dockerfile and .gitlab-ci.yml, or ask about any tool in the portal.\n\n**Example:** `Generate a pipeline for http://gitlab-server/root/golang-sample-app`',
    },
  ]);
  const [value, setValue] = useState('');
  const [convId, setConvId] = useState<string | null>(null);
  // msgId → MonitoringTarget. State (not ref) so re-renders pick up new
  // monitors and React re-mounts the polling <PipelineMonitorBlock/>.
  const [monitorings, setMonitorings] = useState<Map<string, MonitoringTarget>>(
    () => new Map(),
  );
  // msgId → generation metadata (RAG hit / fixer attempts / persisted).
  // Rendered as a `GenerationBadge` directly under the assistant bubble
  // so users can visually distinguish RAG-served vs LLM+fixer pipelines.
  const [generations, setGenerations] = useState<Map<string, ChatGenerationInfo>>(
    () => new Map(),
  );
  // Request id of the in-flight chat POST, used to poll
  // `/api/v1/chat/inflight/{requestId}` while the user waits for the
  // response so we can render a live phase card (Checking RAG, LLM
  // generating, fixer attempt N, etc.). Cleared after each response.
  const [pendingRequestId, setPendingRequestId] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);

  const sendMutation = useMutation({
    mutationFn: ({ msg, requestId }: { msg: string; requestId: string }) =>
      sendChat(msg, convId, requestId),
    onSuccess: (res) => {
      // The chat POST resolved — drop the pending request_id so the
      // inflight poll loop stops and the live phase card disappears.
      setPendingRequestId(null);
      setConvId(res.conversation_id);
      const msgId = `a-${Date.now()}`;
      setMessages((m) => [
        ...m,
        {
          id: msgId,
          role: 'assistant',
          ts: new Date().toISOString(),
          content: res.message,
        },
      ]);

      // Detect a monitoring trigger:
      //   1. Preferred — structured `monitoring` field on the response.
      //   2. Fallback — regex over the message text for older deploys.
      const hint =
        res.monitoring ??
        parseMonitoringFromMessage(res.message ?? '');
      if (hint) {
        setMonitorings((prev) => {
          const next = new Map(prev);
          next.set(msgId, {
            project_id: hint.project_id,
            branch: hint.branch,
            startedAt: Date.now(),
          });
          return next;
        });
        const monitorText = hint.self_healing_enabled
          ? `Monitoring pipeline on branch ${hint.branch} — self-heal up to ${hint.max_heal_attempts ?? 10} attempts.`
          : `Monitoring RAG pipeline on branch ${hint.branch} — status-only, no LLM/self-heal.`;
        toast.success(monitorText);
      }

      // Surface generation metadata (RAG hit / fixer attempts / persisted)
      // emitted by `_tool_generate_pipeline` via the chat response.
      const gen = res.generation;
      if (gen) {
        setGenerations((prev) => {
          const next = new Map(prev);
          next.set(msgId, gen);
          return next;
        });
        if (gen.rag_hit) {
          toast.success('Pipeline served from RAG cache (instant).');
        } else if (gen.validation_passed) {
          const attempts = gen.fix_attempts ?? 0;
          if (attempts > 1) {
            toast.success(
              `Pipeline validated after ${attempts} LLM-fixer attempts; it will save to RAG after GitLab success.`,
            );
          } else if (gen.persisted_to_rag) {
            toast.success('Pipeline validated on first try; persisted to RAG.');
          } else {
            toast.success('Pipeline validated on first try; it will save to RAG after GitLab success.');
          }
        } else if (gen.fix_attempts && gen.fix_attempts >= 10) {
          toast.warning(
            'LLM-fixer exhausted 10 attempts — review the pipeline before committing.',
          );
        }
      }
    },
    onError: (err: Error) => {
      setPendingRequestId(null);
      toast.error(`Chat error: ${err.message}`);
      setMessages((m) => [
        ...m,
        {
          id: `e-${Date.now()}`,
          role: 'assistant',
          ts: new Date().toISOString(),
          content: `**Error:** ${err.message}\n\nPlease confirm the backend is running.`,
        },
      ]);
    },
  });

  const startNewMutation = useMutation({
    mutationFn: () => newConversation(),
    onSuccess: (res) => {
      setConvId(res.conversation_id);
      setMessages([
        {
          id: 'welcome-new',
          role: 'assistant',
          ts: new Date().toISOString(),
          content: `New conversation started. Ask anything about the registered tools.`,
        },
      ]);
      // Drop active monitors when the user explicitly resets the session;
      // they're stale anyway and the visual would mislead.
      setMonitorings(new Map());
      setGenerations(new Map());
      toast.success('Conversation reset');
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // Auto-scroll on new messages or when a new monitor appears.
  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, [messages, monitorings.size, sendMutation.isPending]);

  // Auto-grow textarea.
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 180)}px`;
  }, [value]);

  const onSubmit = (): void => {
    const text = value.trim();
    if (!text || sendMutation.isPending) return;
    setMessages((m) => [
      ...m,
      { id: `u-${Date.now()}`, role: 'user', ts: new Date().toISOString(), content: text },
    ]);
    setValue('');
    // Generate a per-send request_id so the backend can key its in-flight
    // phase store under it and the frontend can start polling immediately
    // without waiting for the conversation_id to come back.
    const requestId =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    setPendingRequestId(requestId);
    sendMutation.mutate({ msg: text, requestId });
  };

  return (
    <div className="flex h-[calc(100dvh-160px)] flex-col gap-4">
      <PageHeader
        eyebrow="Assistant"
        title="AI DevOps Chat"
        description="Pipeline generator, tool-catalog Q&A, and infrastructure debugging — powered by Codex Code + RAG."
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => startNewMutation.mutate()}
            disabled={startNewMutation.isPending}
          >
            {startNewMutation.isPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RotateCw className="h-3.5 w-3.5" />
            )}
            New chat
          </Button>
        }
      />

      <Card className="flex min-h-0 flex-1 flex-col overflow-hidden p-0">
        <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="size-1.5 animate-pulse rounded-full bg-[var(--success)]" />
            <span className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
              Live session
            </span>
          </div>
          <span className="font-mono text-[11px] text-muted-foreground">
            {convId ? `session ${convId.slice(0, 8)}…` : 'no session yet'}
          </span>
        </div>

        <ScrollArea className="flex-1">
          <div ref={scrollerRef} className="space-y-4 px-4 py-6 sm:px-6">
            {messages.map((m) => {
              const target = monitorings.get(m.id);
              const gen = generations.get(m.id);
              return (
                <div key={m.id} className="space-y-2">
                  <MessageBubble message={m} />
                  {gen ? <GenerationBadge info={gen} /> : null}
                  {target ? <PipelineMonitorBlock target={target} /> : null}
                </div>
              );
            })}
            {sendMutation.isPending ? (
              <div className="space-y-2">
                <MessageBubble
                  message={{
                    id: 'thinking',
                    role: 'assistant',
                    ts: new Date().toISOString(),
                    content: '',
                  }}
                  thinking
                />
                {pendingRequestId ? (
                  <InflightPhaseCard requestId={pendingRequestId} />
                ) : null}
              </div>
            ) : null}
          </div>
        </ScrollArea>

        <div className="border-t border-border bg-muted/20 px-3 py-3 sm:px-5">
          <div className="relative flex items-end gap-2 rounded-lg border border-border bg-card px-3 py-2 shadow-sm focus-within:border-ring">
            <Sparkles className="mt-1.5 h-4 w-4 shrink-0 text-primary" />
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  onSubmit();
                }
              }}
              placeholder="Ask me to generate a pipeline, debug a failing build, or explain a tool…"
              rows={1}
              className="max-h-[180px] flex-1 resize-none bg-transparent text-sm outline-hidden placeholder:text-muted-foreground/80"
              disabled={sendMutation.isPending}
            />
            <Button
              type="button"
              size="icon-sm"
              onClick={onSubmit}
              disabled={!value.trim() || sendMutation.isPending}
              aria-label="Send"
              className="rounded-full"
            >
              {sendMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowUp className="h-4 w-4" />
              )}
            </Button>
          </div>
          <p className="mt-2 px-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            Enter to send · Shift+Enter for newline · backend: /api/v1/chat/
          </p>
        </div>
      </Card>
    </div>
  );
}

function MessageBubble({
  message,
  thinking = false,
}: {
  message: Msg;
  thinking?: boolean;
}): React.ReactElement {
  const isUser = message.role === 'user';
  const html = thinking ? '' : renderMarkdown(message.content);
  return (
    <div
      className={cn(
        'flex items-start gap-3',
        isUser ? 'flex-row-reverse' : 'flex-row',
        'animate-[fade-up_0.4s_cubic-bezier(0.22,1,0.36,1)_both]'
      )}
    >
      <div
        className={cn(
          'flex size-7 shrink-0 items-center justify-center rounded-md border',
          isUser
            ? 'border-primary/30 bg-primary/10 text-primary'
            : 'border-border bg-muted/50 text-foreground'
        )}
      >
        {isUser ? <User2 className="h-3.5 w-3.5" /> : <Bot className="h-3.5 w-3.5" />}
      </div>
      <div
        className={cn(
          'min-w-0 max-w-[min(760px,88%)] rounded-2xl px-4 py-2.5 text-[13.5px] leading-relaxed',
          isUser
            ? 'rounded-br-md bg-primary text-primary-foreground'
            : 'rounded-bl-md border border-border bg-card'
        )}
      >
        {thinking ? (
          <div className="flex items-center gap-1.5">
            <span className="size-1.5 animate-[pulse_1.2s_ease-in-out_infinite] rounded-full bg-primary" />
            <span
              className="size-1.5 animate-[pulse_1.2s_ease-in-out_infinite] rounded-full bg-primary"
              style={{ animationDelay: '0.15s' }}
            />
            <span
              className="size-1.5 animate-[pulse_1.2s_ease-in-out_infinite] rounded-full bg-primary"
              style={{ animationDelay: '0.3s' }}
            />
            <span className="ml-1.5 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
              thinking
            </span>
          </div>
        ) : (
          <div
            className="prose-chat break-words"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        )}
        <div
          className={cn(
            'mt-1.5 font-mono text-[10px] uppercase tracking-wider',
            isUser ? 'text-primary-foreground/70' : 'text-muted-foreground'
          )}
        >
          {timeAgo(message.ts)}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------------ */
/* PipelineMonitorBlock — per-message polling wrapper                          */
/* ------------------------------------------------------------------------ */
/**
 * Owns the polling lifecycle for a single (project_id, branch) target.
 * Uses TanStack Query's `refetchInterval` for the 2s cadence and a
 * lightweight derived `polling` flag so the card renders the right
 * "live" indicator state.
 *
 * Stop conditions (in order):
 *   1. Backend reports `completed === true`
 *   2. Status is `success`
 *   3. 30 minutes elapsed (MAX_POLL_COUNT polls × POLL_INTERVAL_MS)
 *
 * On any of those, `refetchInterval` returns `false`, which TanStack
 * Query interprets as "stop polling".
 */
function PipelineMonitorBlock({
  target,
}: {
  target: MonitoringTarget;
}): React.ReactElement {
  // Hard ceiling timer — guarantees polling stops even if the backend
  // forever returns `completed=false` (e.g. monitor crash). The state
  // flips once and triggers a final refetch then halts.
  const [forcedStop, setForcedStop] = useState(false);
  useEffect(() => {
    const remaining =
      MAX_POLL_COUNT * POLL_INTERVAL_MS - (Date.now() - target.startedAt);
    if (remaining <= 0) {
      setForcedStop(true);
      return;
    }
    const t = window.setTimeout(() => setForcedStop(true), remaining);
    return () => window.clearTimeout(t);
  }, [target.startedAt]);

  const query = useQuery<PipelineProgress, Error>({
    queryKey: ['pipeline-progress', target.project_id, target.branch],
    queryFn: () => fetchPipelineProgress(target.project_id, target.branch),
    refetchInterval: (q) => {
      if (forcedStop) return false;
      const data = q.state.data;
      if (!data) return POLL_INTERVAL_MS;
      if (data.completed === true) return false;
      if (data.status === 'success') return false;
      return POLL_INTERVAL_MS;
    },
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
    refetchOnMount: true,
    retry: 2,
    staleTime: 0,
  });

  const data = query.data;
  const stopped =
    forcedStop ||
    (!!data && (data.completed === true ||
      data.status === 'success'));
  const polling = !stopped && !query.isError;

  // First-poll skeleton: query has not returned yet — show a placeholder
  // with the known target so the user gets immediate feedback.
  if (!data) {
    if (query.isError) {
      return (
        <div
          className={cn(
            'mt-2 ml-10 max-w-[min(760px,88%)] rounded-lg border border-border',
            'bg-[color-mix(in_oklch,var(--destructive)_8%,var(--card))] px-3 py-2',
            'text-[12px] text-foreground/90',
          )}
          role="alert"
        >
          <p className="font-mono text-[10.5px] uppercase tracking-wider text-muted-foreground">
            Pipeline monitor — error
          </p>
          <p className="mt-1">{query.error?.message ?? 'Failed to load progress.'}</p>
        </div>
      );
    }
    return (
      <PipelineProgressCard
        progress={{ found: false, project_id: target.project_id, branch: target.branch }}
        polling
        fallbackBranch={target.branch}
        fallbackProjectId={target.project_id}
      />
    );
  }

  return (
    <PipelineProgressCard
      progress={data}
      polling={polling}
      fallbackBranch={target.branch}
      fallbackProjectId={target.project_id}
    />
  );
}

/* ------------------------------------------------------------------------ */
/* InflightPhaseCard — live "what is the chatbot doing right now" card        */
/* ------------------------------------------------------------------------ */
/**
 * Polls `GET /api/v1/chat/inflight/{requestId}` every 1.5s while the user's
 * chat POST is still in flight, so the user sees exactly which phase the
 * pipeline-runner tool is in (rather than a featureless "thinking" spinner):
 *
 *   analyzing       → "Analyzing repository..."
 *   checking_rag    → "Checking RAG cache for proven template..."
 *   rag_hit         → "Template found in RAG. No LLM call."  (green)
 *   llm_validated   → "Codex Code validated on first try."    (amber)
 *   llm_fixed       → "LLM + auto-fixer converged after N/10 attempts." (amber)
 *   committing      → "Validated. Committing & starting pipeline..."   (info)
 *   monitoring      → "Pipeline running on branch X." (info)
 *   validation_failed → "LLM fixer exhausted 10 attempts." (red)
 *
 * Stops polling automatically once the chat POST resolves (the parent
 * unmounts this component when sendMutation.isPending flips to false).
 */
function InflightPhaseCard({
  requestId,
}: {
  requestId: string;
}): React.ReactElement | null {
  const query = useQuery<ChatInflight, Error>({
    queryKey: ['chat-inflight', requestId],
    queryFn: () => fetchChatInflight(requestId),
    refetchInterval: 1500,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: false,
    refetchOnMount: true,
    retry: 1,
    staleTime: 0,
  });
  const data = query.data;
  if (!data || data.phase === 'idle') return null;
  const v = phaseVisualOf(data);
  const Icon = v.icon;
  return (
    <div
      data-testid="chat-inflight-card"
      data-phase={data.phase}
      className={cn(
        'mt-2 ml-10 flex max-w-[min(760px,88%)] items-start gap-2 rounded-lg border px-3 py-2',
        v.tone,
      )}
    >
      <Icon
        className={cn('mt-0.5 h-3.5 w-3.5 shrink-0', v.spin ? 'animate-spin' : 'animate-pulse')}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <p className="font-mono text-[10.5px] uppercase tracking-wider opacity-80">
          {v.label}
        </p>
        <p className="mt-0.5 text-[12.5px] font-medium leading-tight">
          {data.message ?? '...'}
        </p>
        {Array.isArray(data.errors) && data.errors.length > 0 ? (
          <ul className="mt-1 list-disc pl-4 text-[11px] opacity-80">
            {data.errors.slice(0, 3).map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}

interface PhaseVisual {
  label: string;
  icon: typeof Loader2;
  tone: string;
  spin: boolean;
}

function phaseVisualOf(d: ChatInflight): PhaseVisual {
  const success =
    'border-[color-mix(in_oklch,var(--success)_30%,var(--border))] bg-[color-mix(in_oklch,var(--success)_8%,var(--card))] text-[color-mix(in_oklch,var(--success)_70%,var(--foreground))]';
  const warn =
    'border-[color-mix(in_oklch,var(--warning,#d97706)_30%,var(--border))] bg-[color-mix(in_oklch,var(--warning,#d97706)_8%,var(--card))] text-[color-mix(in_oklch,var(--warning,#d97706)_70%,var(--foreground))]';
  const danger =
    'border-[color-mix(in_oklch,var(--destructive)_30%,var(--border))] bg-[color-mix(in_oklch,var(--destructive)_8%,var(--card))] text-[color-mix(in_oklch,var(--destructive)_70%,var(--foreground))]';
  const info =
    'border-[color-mix(in_oklch,var(--info)_30%,var(--border))] bg-[color-mix(in_oklch,var(--info)_8%,var(--card))] text-[color-mix(in_oklch,var(--info)_70%,var(--foreground))]';
  switch (d.phase) {
    case 'analyzing':
      return { label: 'Analyzing repo', icon: Search, tone: info, spin: true };
    case 'checking_rag':
      return { label: 'Checking RAG', icon: Database, tone: info, spin: true };
    case 'rag_hit':
      return { label: 'RAG cache hit', icon: Database, tone: success, spin: false };
    case 'calling_llm':
      return { label: 'Calling LLM', icon: Sparkles, tone: warn, spin: true };
    case 'fixer_starting':
      return { label: 'Fixer starting', icon: Wrench, tone: warn, spin: true };
    case 'fixer_attempt':
    case 'fixer_fixing':
      return { label: `Fixer attempt ${d.fix_attempts ?? '?'}/10`, icon: Wrench, tone: warn, spin: true };
    case 'llm_validated':
      return { label: 'LLM validated', icon: CheckCircle2, tone: warn, spin: false };
    case 'llm_fixed':
      return { label: `LLM + auto-fixer (${d.fix_attempts ?? '?'} attempts)`, icon: Wrench, tone: warn, spin: false };
    case 'committing':
      return { label: 'Committing', icon: GitCommit, tone: info, spin: true };
    case 'monitoring':
      return { label: 'Monitoring', icon: Loader2, tone: info, spin: true };
    case 'validation_failed':
      return { label: 'Fixer exhausted', icon: XCircle, tone: danger, spin: false };
    case 'error':
      return { label: 'Error', icon: XCircle, tone: danger, spin: false };
    default:
      return { label: d.phase, icon: Loader2, tone: info, spin: true };
  }
}

/* ------------------------------------------------------------------------ */
/* GenerationBadge — RAG-hit / LLM+fixer status pill under assistant bubbles  */
/* ------------------------------------------------------------------------ */
/**
 * Renders the outcome of `generate_pipeline`:
 *   - RAG hit          → instant template from ChromaDB (no LLM call)
 *   - LLM + fixer loop → first attempt invalid; fixer iterated up to 10×
 *   - Persisted to RAG → fixer succeeded; future requests hit RAG instead
 *   - Validation failed → fixer exhausted 10 attempts; user must review
 *
 * The colour scheme is:
 *   green  = RAG-served or fully validated + persisted
 *   amber  = LLM + fixer loop ran but completed
 *   red    = fixer exhausted attempts, manual review required
 *
 * `data-testid="generation-badge"` is set so chrome-devtools E2E tests can
 * assert both code paths end-to-end.
 */
function GenerationBadge({
  info,
}: {
  info: ChatGenerationInfo;
}): React.ReactElement {
  const ragHit = info.rag_hit === true;
  const validated = info.validation_passed === true;
  const persisted = info.persisted_to_rag === true;
  const attempts = info.fix_attempts ?? 0;
  const failed =
    info.fix_attempts !== null &&
    info.fix_attempts !== undefined &&
    attempts >= 10 &&
    !validated;

  let tone: 'success' | 'warn' | 'danger' = 'success';
  let Icon = Database;
  let label = info.template_source ?? 'Pipeline generated';
  let detail = '';

  if (ragHit) {
    tone = 'success';
    Icon = Database;
    label = 'RAG cache hit';
    detail = `Served instantly from ChromaDB — no LLM call (${info.language ?? 'unknown'}/${info.framework ?? 'generic'})`;
  } else if (failed) {
    tone = 'danger';
    Icon = XCircle;
    label = `LLM-fixer exhausted ${attempts} attempts`;
    detail = 'Pipeline did not pass validation — review before committing.';
  } else if (validated && attempts > 1) {
    tone = 'warn';
    Icon = Wrench;
    label = `LLM + auto-fixer (${attempts} attempts)`;
    detail = persisted
      ? `Validated and persisted to RAG — next request for ${info.language ?? '?'}/${info.framework ?? '?'} will be instant.`
      : 'Validated; RAG persistence skipped.';
  } else if (validated) {
    tone = 'success';
    Icon = CheckCircle2;
    label = 'LLM-generated, validated on first try';
    detail = persisted
      ? `Persisted to RAG — next request for ${info.language ?? '?'}/${info.framework ?? '?'} will be instant.`
      : 'Validated; RAG persistence skipped.';
  } else {
    tone = 'warn';
    Icon = Wrench;
    label = info.template_source ?? 'Pipeline generated';
    detail = 'Validator did not run or failed; review before committing.';
  }

  const toneClasses: Record<typeof tone, string> = {
    success:
      'border-[color-mix(in_oklch,var(--success)_30%,var(--border))] bg-[color-mix(in_oklch,var(--success)_8%,var(--card))] text-[color-mix(in_oklch,var(--success)_70%,var(--foreground))]',
    warn:
      'border-[color-mix(in_oklch,var(--warning,#d97706)_30%,var(--border))] bg-[color-mix(in_oklch,var(--warning,#d97706)_8%,var(--card))] text-[color-mix(in_oklch,var(--warning,#d97706)_70%,var(--foreground))]',
    danger:
      'border-[color-mix(in_oklch,var(--destructive)_30%,var(--border))] bg-[color-mix(in_oklch,var(--destructive)_8%,var(--card))] text-[color-mix(in_oklch,var(--destructive)_70%,var(--foreground))]',
  };

  return (
    <div
      data-testid="generation-badge"
      data-rag-hit={ragHit ? 'true' : 'false'}
      data-validated={validated ? 'true' : 'false'}
      data-persisted={persisted ? 'true' : 'false'}
      data-attempts={String(attempts)}
      data-source-token={info.source_token ?? ''}
      className={cn(
        'mt-2 ml-10 flex max-w-[min(760px,88%)] items-start gap-2 rounded-lg border px-3 py-2',
        toneClasses[tone],
      )}
    >
      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="font-mono text-[10.5px] uppercase tracking-wider opacity-80">
          Pipeline source
        </p>
        <p className="mt-0.5 text-[12.5px] font-medium leading-tight">
          {label}
        </p>
        {detail ? (
          <p className="mt-0.5 text-[11.5px] opacity-80 leading-snug">{detail}</p>
        ) : null}
      </div>
    </div>
  );
}
