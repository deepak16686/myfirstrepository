/**
 * Integration test for the Chat page — focused on the new self-healing
 * pipeline-monitor wiring.
 *
 * What's covered here:
 *   1. When `sendChat` returns `monitoring: {project_id, branch}`, a
 *      PipelineProgressCard is rendered immediately below the assistant
 *      message and `fetchPipelineProgress` is polled.
 *   2. Regex fallback: when `monitoring` is absent but the message text
 *      contains the `[monitoring project_id=N branch=B]` marker, the
 *      same wiring fires.
 *   3. When `sendChat` returns NO monitoring hint and no marker, no
 *      PipelineProgressCard is rendered.
 *
 * `fetchPipelineProgress` is mocked so we don't actually exercise the
 * 2s polling loop end-to-end — we just assert it was called for the
 * expected (project_id, branch) tuple.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement, ReactNode } from 'react';

vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    sendChat: vi.fn(),
    newConversation: vi.fn(),
    fetchPipelineProgress: vi.fn(),
  };
});

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

import { sendChat, fetchPipelineProgress } from '@/lib/api';
import { Chat } from '../Chat';

const mockSendChat = vi.mocked(sendChat);
const mockFetchProgress = vi.mocked(fetchPipelineProgress);

function renderWithQuery(ui: ReactElement): void {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  render(ui, { wrapper });
}

beforeEach(() => {
  mockSendChat.mockReset();
  mockFetchProgress.mockReset();
});

describe('Chat — pipeline monitoring wiring', () => {
  it('renders a PipelineProgressCard when the chat response includes a monitoring hint', async () => {
    const user = userEvent.setup();
    mockSendChat.mockResolvedValueOnce({
      conversation_id: 'conv-1',
      message:
        "Pipeline committed to branch feature/ai-pipeline-abc. I'm now monitoring it...",
      monitoring: { project_id: 12, branch: 'feature/ai-pipeline-abc' },
    });
    mockFetchProgress.mockResolvedValue({
      found: true,
      project_id: 12,
      branch: 'feature/ai-pipeline-abc',
      status: 'monitoring',
      current_message: 'Waiting for pipeline...',
      attempt: 0,
      max_attempts: 10,
      pipeline_id: 4711,
      completed: false,
      model_used: 'chromadb-direct',
      events: [
        {
          timestamp: '11:00:01',
          stage: 'monitoring',
          message: 'Pipeline committed.',
          attempt: 0,
          max_attempts: 10,
        },
      ],
    });

    renderWithQuery(<Chat />);

    const ta = screen.getByPlaceholderText(/Ask me to generate/i);
    await user.type(ta, 'Commit and run');
    await user.click(screen.getByRole('button', { name: /^Send$/i }));

    // The assistant message text appears.
    await waitFor(() => {
      expect(
        screen.getByText(/Pipeline committed to branch/),
      ).toBeInTheDocument();
    });

    // The polling helper is called for the (project_id, branch) tuple.
    await waitFor(() => {
      expect(mockFetchProgress).toHaveBeenCalledWith(
        12,
        'feature/ai-pipeline-abc',
      );
    });

    // The progress card renders with the polled data.
    await waitFor(() => {
      expect(screen.getByText('#4711')).toBeInTheDocument();
    });
    expect(screen.getByText('feature/ai-pipeline-abc')).toBeInTheDocument();
    expect(screen.getByText('RAG template')).toBeInTheDocument();
  });

  it('falls back to the regex marker when `monitoring` is absent', async () => {
    const user = userEvent.setup();
    mockSendChat.mockResolvedValueOnce({
      conversation_id: 'conv-2',
      message:
        'Pipeline committed. [monitoring project_id=99 branch=feature/legacy ]',
    });
    mockFetchProgress.mockResolvedValue({
      found: true,
      project_id: 99,
      branch: 'feature/legacy',
      status: 'build_running',
      current_message: 'Running...',
      attempt: 0,
      max_attempts: 10,
      pipeline_id: 1234,
      completed: false,
      model_used: 'pipeline-generator-v5',
      events: [],
    });

    renderWithQuery(<Chat />);

    const ta = screen.getByPlaceholderText(/Ask me to generate/i);
    await user.type(ta, 'Commit');
    await user.click(screen.getByRole('button', { name: /^Send$/i }));

    await waitFor(() => {
      expect(mockFetchProgress).toHaveBeenCalledWith(99, 'feature/legacy');
    });
  });

  it('does NOT render a progress card when the response has neither monitoring nor a marker', async () => {
    const user = userEvent.setup();
    mockSendChat.mockResolvedValueOnce({
      conversation_id: 'conv-3',
      message: 'Here is a quick answer — no pipeline action taken.',
    });

    renderWithQuery(<Chat />);

    const ta = screen.getByPlaceholderText(/Ask me to generate/i);
    await user.type(ta, 'What is Grafana?');
    await user.click(screen.getByRole('button', { name: /^Send$/i }));

    await waitFor(() => {
      expect(screen.getByText(/no pipeline action taken/)).toBeInTheDocument();
    });

    // No polling, no progress card.
    expect(mockFetchProgress).not.toHaveBeenCalled();
    expect(screen.queryByText(/^Stage timeline/)).not.toBeInTheDocument();
  });
});
