/**
 * Unit tests for PipelineProgressCard.
 *
 * The card is purely presentational — it consumes a `PipelineProgress`
 * snapshot and a `polling` flag, nothing else. So these tests cover the
 * pixel-level branches rather than data fetching:
 *
 *   1. Header — pipeline id + branch render correctly, including the
 *      `...` placeholder when pipeline_id is missing.
 *   2. Status pill — labels switch with status (Monitoring / Running /
 *      Running / Success / Failed).
 *   3. Source badge — model_used is parsed into RAG / LLM / Default.
 *   4. Self-heal badge — only rendered when fixer_model_used is set.
 *   5. Attempt counter + progress bar reflect attempt/max_attempts.
 *   6. Markdown link in current_message becomes a "View Pipeline" CTA.
 *   7. Event timeline shows last 12 + "show all" toggle for older items.
 *   8. Found:false renders the "waiting for monitor" placeholder.
 */
import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PipelineProgressCard } from '../PipelineProgressCard';
import type { PipelineProgress, PipelineProgressEvent } from '@/types/tool';

function makeEvent(
  ts: string,
  stage: string,
  message: string,
  attempt = 0,
): PipelineProgressEvent {
  return { timestamp: ts, stage, message, attempt, max_attempts: 10 };
}

function makeProgress(
  overrides: Partial<PipelineProgress> = {},
): PipelineProgress {
  return {
    found: true,
    project_id: 12,
    branch: 'feature/ai-pipeline-abc',
    status: 'monitoring',
    current_message: 'Pipeline committed. Waiting for pipeline to start...',
    attempt: 0,
    max_attempts: 10,
    pipeline_id: 4711,
    completed: false,
    model_used: 'chromadb-direct',
    fixer_model_used: null,
    events: [makeEvent('11:00:01', 'monitoring', 'Pipeline committed. Waiting...')],
    ...overrides,
  };
}

describe('PipelineProgressCard', () => {
  it('renders header with pipeline id and branch', () => {
    render(<PipelineProgressCard progress={makeProgress()} polling />);
    expect(screen.getByText('#4711')).toBeInTheDocument();
    expect(screen.getByText('feature/ai-pipeline-abc')).toBeInTheDocument();
    expect(screen.getByText(/project 12/i)).toBeInTheDocument();
  });

  it('falls back to ... when pipeline_id is missing', () => {
    render(
      <PipelineProgressCard
        progress={makeProgress({ pipeline_id: null })}
        polling
      />,
    );
    expect(screen.getByText('#...')).toBeInTheDocument();
  });

  it('shows the Monitoring status pill for status=monitoring', () => {
    render(<PipelineProgressCard progress={makeProgress()} polling />);
    expect(screen.getByText('Monitoring')).toBeInTheDocument();
  });

  it('keeps the status pill Running for status=build_failed while polling', () => {
    render(
      <PipelineProgressCard
        progress={makeProgress({ status: 'build_failed', attempt: 3 })}
        polling
      />,
    );
    expect(screen.getByText('Running')).toBeInTheDocument();
  });

  it('shows the Success status pill for status=success', () => {
    render(
      <PipelineProgressCard
        progress={makeProgress({ status: 'success', completed: true })}
        polling={false}
      />,
    );
    expect(screen.getByText('Success')).toBeInTheDocument();
  });

  it('shows the Failed status pill for status=failed', () => {
    render(
      <PipelineProgressCard
        progress={makeProgress({ status: 'failed', completed: true })}
        polling={false}
      />,
    );
    // Both the status pill and the live indicator say "Failed" — that's
    // intentional (one is the formal status, the other is the live mark).
    const matches = screen.getAllByText('Failed');
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it('does not show terminal Failed while backend has not completed monitoring', () => {
    render(
      <PipelineProgressCard
        progress={makeProgress({ status: 'failed', completed: false, attempt: 1 })}
        polling
      />,
    );
    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(screen.queryByText('Failed')).not.toBeInTheDocument();
  });

  it('renders the RAG-template source badge for model_used=chromadb-direct', () => {
    render(
      <PipelineProgressCard
        progress={makeProgress({ model_used: 'chromadb-direct' })}
        polling
      />,
    );
    expect(screen.getByText('RAG template')).toBeInTheDocument();
  });

  it('renders the LLM-generated badge when model_used contains "Codex Code"', () => {
    render(
      <PipelineProgressCard
        progress={makeProgress({ model_used: 'Codex Code (gpt-5.5)' })}
        polling
      />,
    );
    expect(screen.getByText('LLM-generated')).toBeInTheDocument();
  });

  it('renders the Default-template badge for model_used=template-only', () => {
    render(
      <PipelineProgressCard
        progress={makeProgress({ model_used: 'template-only' })}
        polling
      />,
    );
    expect(screen.getByText('Default template')).toBeInTheDocument();
  });

  it('renders the self-heal badge when fixer_model_used is set', () => {
    render(
      <PipelineProgressCard
        progress={makeProgress({ fixer_model_used: 'Codex Code (gpt-5.5)' })}
        polling
      />,
    );
    expect(screen.getByText(/self-heal: codex code/i)).toBeInTheDocument();
  });

  it('does not render the self-heal badge when fixer_model_used is null', () => {
    render(
      <PipelineProgressCard
        progress={makeProgress({ fixer_model_used: null })}
        polling
      />,
    );
    expect(screen.queryByText(/^self-heal:/i)).not.toBeInTheDocument();
  });

  it('shows the attempt counter and progress bar with correct aria values', () => {
    render(
      <PipelineProgressCard
        progress={makeProgress({
          attempt: 4,
          max_attempts: 10,
          model_used: 'Codex Code (gpt-5.5)',
        })}
        polling
      />,
    );
    expect(screen.getByText(/ATT 4\/10/)).toBeInTheDocument();
    const progressbar = screen.getByRole('progressbar');
    expect(progressbar).toHaveAttribute('aria-valuenow', '4');
    expect(progressbar).toHaveAttribute('aria-valuemax', '10');
  });

  it('extracts a markdown link from current_message and renders the CTA', () => {
    render(
      <PipelineProgressCard
        progress={makeProgress({
          current_message:
            'Build started [View Pipeline](https://example.com/pipeline/4711)',
        })}
        polling
      />,
    );
    const cta = screen.getByRole('link', { name: /view pipeline/i });
    expect(cta).toHaveAttribute('href', 'https://example.com/pipeline/4711');
    // The square-bracket markdown should NOT leak into the body text.
    expect(
      screen.queryByText(/\[View Pipeline\]\(/),
    ).not.toBeInTheDocument();
  });

  it('renders the event timeline with the count', () => {
    const events: PipelineProgressEvent[] = [
      makeEvent('11:00:01', 'monitoring', 'Started'),
      makeEvent('11:00:30', 'build_running', 'Build #4711 running'),
      makeEvent('11:01:00', 'build_failed', 'Build failed', 1),
    ];
    render(
      <PipelineProgressCard
        progress={makeProgress({ events, attempt: 1 })}
        polling
      />,
    );
    expect(screen.getByText('Stage timeline (3)')).toBeInTheDocument();
    expect(screen.getByText('Started')).toBeInTheDocument();
    expect(screen.getByText('Build #4711 running')).toBeInTheDocument();
    expect(screen.getByText('Build failed')).toBeInTheDocument();
  });

  it('truncates to last 12 events and toggles "show all"', async () => {
    const user = userEvent.setup();
    const events: PipelineProgressEvent[] = Array.from({ length: 18 }, (_, i) =>
      makeEvent(`12:00:${String(i).padStart(2, '0')}`, 'monitoring', `Event ${i + 1}`),
    );
    render(
      <PipelineProgressCard
        progress={makeProgress({ events })}
        polling
      />,
    );
    expect(screen.getByText('Event 18')).toBeInTheDocument();
    expect(screen.queryByText('Event 1')).not.toBeInTheDocument();

    const toggle = screen.getByRole('button', { name: /show all/i });
    await user.click(toggle);
    expect(screen.getByText('Event 1')).toBeInTheDocument();
    expect(screen.getByText('Event 18')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /last 12/i }));
    expect(screen.queryByText('Event 1')).not.toBeInTheDocument();
  });

  it('renders the not-yet-found placeholder for found=false', () => {
    render(
      <PipelineProgressCard
        progress={{ found: false, branch: 'feature/test', project_id: 99 }}
        polling
        fallbackBranch="feature/test"
        fallbackProjectId={99}
      />,
    );
    // status defaults to "Pending" when no status string is reported.
    expect(screen.getByText('Pending')).toBeInTheDocument();
    // Falls back to the in-flight monitor message when there are no events.
    expect(screen.getByText(/connecting to monitor/i)).toBeInTheDocument();
  });

  it('renders the live indicator label as "Completed" on success', () => {
    render(
      <PipelineProgressCard
        progress={makeProgress({ status: 'success', completed: true })}
        polling={false}
      />,
    );
    // The live-status caption label.
    const completedNodes = screen.getAllByText('Completed');
    expect(completedNodes.length).toBeGreaterThan(0);
  });

  it('attaches the latest-event ring only to the bottom row', () => {
    const events: PipelineProgressEvent[] = [
      makeEvent('12:00:00', 'monitoring', 'Older'),
      makeEvent('12:00:30', 'build_running', 'Newest'),
    ];
    const { container } = render(
      <PipelineProgressCard
        progress={makeProgress({ events, status: 'build_running' })}
        polling
      />,
    );
    const list = container.querySelector('ol');
    expect(list).not.toBeNull();
    if (list) {
      const items = within(list).getAllByRole('listitem');
      expect(items).toHaveLength(2);
      // The latest item gets the fade-up animation class.
      expect(items[items.length - 1].className).toMatch(/fade-up/);
    }
  });
});
