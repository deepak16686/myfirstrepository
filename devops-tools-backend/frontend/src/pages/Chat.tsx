/**
 * AI Chat — migration of the legacy chat UI, mapped onto shadcn primitives.
 * Talks to POST /api/v1/chat/ (same contract as the old app.js).
 */
import { useEffect, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ArrowUp, Bot, Loader2, RotateCw, Sparkles, User2 } from 'lucide-react';
import { toast } from 'sonner';
import { PageHeader } from '@/components/common/PageHeader';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { newConversation, sendChat } from '@/lib/api';
import { cn, timeAgo } from '@/lib/utils';

type Msg = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  ts: string;
};

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
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);

  const sendMutation = useMutation({
    mutationFn: (msg: string) => sendChat(msg, convId),
    onSuccess: (res) => {
      setConvId(res.conversation_id);
      setMessages((m) => [
        ...m,
        {
          id: `a-${Date.now()}`,
          role: 'assistant',
          ts: new Date().toISOString(),
          content: res.message,
        },
      ]);
    },
    onError: (err: Error) => {
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
      toast.success('Conversation reset');
    },
    onError: (err: Error) => toast.error(err.message),
  });

  // Auto-scroll on new messages.
  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
  }, [messages, sendMutation.isPending]);

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
    sendMutation.mutate(text);
  };

  return (
    <div className="flex h-[calc(100dvh-160px)] flex-col gap-4">
      <PageHeader
        eyebrow="Assistant"
        title="AI DevOps Chat"
        description="Pipeline generator, tool-catalog Q&A, and infrastructure debugging — powered by your local Ollama + RAG."
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
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} />
            ))}
            {sendMutation.isPending ? (
              <MessageBubble
                message={{
                  id: 'thinking',
                  role: 'assistant',
                  ts: new Date().toISOString(),
                  content: '',
                }}
                thinking
              />
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
