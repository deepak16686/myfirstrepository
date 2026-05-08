/**
 * Unit tests for CredentialsPanel.
 *
 * The module-under-test owns two external edges we need to control:
 *   1. `fetchCredentials` — mocked so we can exercise 200 / 401 paths.
 *   2. the UI zustand store — read / written directly for token state.
 *
 * Each test gets a fresh QueryClient so TanStack Query state does not leak
 * between cases.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactElement, ReactNode } from 'react';

import { ApiError } from '@/lib/api';
import type { CredentialsResponse, Tool } from '@/types/tool';

// --------------------------------------------------------------------------
// Module mocks — must be declared before importing the component under test.
// --------------------------------------------------------------------------
vi.mock('@/lib/api', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api')>('@/lib/api');
  return {
    ...actual,
    fetchCredentials: vi.fn(),
  };
});

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

import { fetchCredentials } from '@/lib/api';
import { toast } from 'sonner';
import { useUiStore } from '@/store/ui';
import { CredentialsPanel } from '../CredentialsPanel';

const mockFetchCredentials = vi.mocked(fetchCredentials);

// --------------------------------------------------------------------------
// Fixtures
// --------------------------------------------------------------------------
function makeTool(overrides: Partial<Tool> = {}): Tool {
  return {
    id: 'grafana',
    name: 'Grafana',
    category: 'observability',
    description: 'Dashboards for metrics, logs, traces.',
    icon: 'line-chart',
    embed: false,
    tags: [],
    credentials: 'vault:secret/observability/grafana',
    ...overrides,
  };
}

function renderWithQuery(ui: ReactElement): void {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  render(ui, { wrapper });
}

// Reset the store + mocks before each test. The zustand store persists to
// localStorage via our custom helper; the test-setup `afterEach` clears it.
beforeEach(() => {
  act(() => {
    useUiStore.getState().setOperatorToken(null);
  });
  mockFetchCredentials.mockReset();
  vi.mocked(toast.error).mockReset();
  vi.mocked(toast.success).mockReset();
  vi.mocked(toast.info).mockReset();
});

describe('CredentialsPanel', () => {
  it('renders nothing when the tool has no credentials pointer', () => {
    // Even though the component short-circuits, React hook rules mean
    // `useMutation` is still called once. Tests therefore always need the
    // QueryClientProvider, even on the "null render" path.
    const qc = new QueryClient();
    const { container } = render(
      <QueryClientProvider client={qc}>
        <CredentialsPanel tool={makeTool({ credentials: undefined })} />
      </QueryClientProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the credentials pointer is the literal "none"', () => {
    const qc = new QueryClient();
    const { container } = render(
      <QueryClientProvider client={qc}>
        <CredentialsPanel tool={makeTool({ credentials: 'none' })} />
      </QueryClientProvider>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the locked state initially with a Reveal button', () => {
    renderWithQuery(<CredentialsPanel tool={makeTool()} />);
    expect(screen.getByText('Credentials stored in Vault')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /reveal credentials/i }),
    ).toBeInTheDocument();
    // Reveal flow has not started yet — no token input or field rows.
    expect(screen.queryByPlaceholderText('Operator token')).not.toBeInTheDocument();
  });

  it('shows the token-entry input when Reveal is clicked without a stored token', async () => {
    const user = userEvent.setup();
    renderWithQuery(<CredentialsPanel tool={makeTool()} />);

    await user.click(screen.getByRole('button', { name: /reveal credentials/i }));

    expect(screen.getByPlaceholderText('Operator token')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /unlock/i })).toBeInTheDocument();
    // The API should NOT have been called yet — we asked for a token first.
    expect(mockFetchCredentials).not.toHaveBeenCalled();
  });

  it('calls fetchCredentials with the stored token and renders returned fields', async () => {
    const user = userEvent.setup();
    act(() => {
      useUiStore.getState().setOperatorToken('pre-stored-token');
    });

    const payload: CredentialsResponse = {
      tool_id: 'grafana',
      source: 'vault',
      fields: {
        username: 'admin',
        password: 'super-secret',
        url: 'http://localhost:3000',
      },
      retrieved_at: new Date().toISOString(),
    };
    mockFetchCredentials.mockResolvedValueOnce(payload);

    renderWithQuery(<CredentialsPanel tool={makeTool()} />);
    await user.click(screen.getByRole('button', { name: /reveal credentials/i }));

    await waitFor(() => {
      expect(mockFetchCredentials).toHaveBeenCalledTimes(1);
    });
    expect(mockFetchCredentials).toHaveBeenCalledWith('grafana', 'pre-stored-token');

    // Fields are rendered by key; values are masked by default.
    await waitFor(() => {
      expect(screen.getByText('username')).toBeInTheDocument();
    });
    expect(screen.getByText('password')).toBeInTheDocument();
    expect(screen.getByText('url')).toBeInTheDocument();
    // All plaintext values should be hidden until hovered / toggled.
    expect(screen.queryByText('super-secret')).not.toBeInTheDocument();
    // Source + audit line present.
    expect(screen.getByText(/retrieved from/i)).toBeInTheDocument();
  });

  it('clears the stored token on a 401 and toasts the error', async () => {
    const user = userEvent.setup();
    act(() => {
      useUiStore.getState().setOperatorToken('bad-token');
    });

    mockFetchCredentials.mockRejectedValueOnce(
      new ApiError('Operator token required', 401, '/creds'),
    );

    renderWithQuery(<CredentialsPanel tool={makeTool()} />);
    await user.click(screen.getByRole('button', { name: /reveal credentials/i }));

    await waitFor(() => {
      expect(useUiStore.getState().operatorToken).toBeNull();
    });
    expect(toast.error).toHaveBeenCalledWith('Operator token required');
    // Panel remains locked.
    expect(screen.getByText('Credentials stored in Vault')).toBeInTheDocument();
  });

  it('drops to collapsed state and toasts on 503', async () => {
    const user = userEvent.setup();
    act(() => {
      useUiStore.getState().setOperatorToken('any-token');
    });

    mockFetchCredentials.mockRejectedValueOnce(
      new ApiError('Credentials endpoint disabled on backend', 503, '/creds'),
    );

    renderWithQuery(<CredentialsPanel tool={makeTool()} />);
    await user.click(screen.getByRole('button', { name: /reveal credentials/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        'Credentials endpoint not configured on backend',
      );
    });
    // Token is NOT cleared on 503 (the token isn't at fault).
    expect(useUiStore.getState().operatorToken).toBe('any-token');
  });

  it('Re-lock collapses the reveal back to the locked state', async () => {
    const user = userEvent.setup();
    act(() => {
      useUiStore.getState().setOperatorToken('ok');
    });
    mockFetchCredentials.mockResolvedValueOnce({
      tool_id: 'grafana',
      source: 'vault',
      fields: { username: 'admin' },
      retrieved_at: new Date().toISOString(),
    });

    renderWithQuery(<CredentialsPanel tool={makeTool()} />);
    await user.click(screen.getByRole('button', { name: /reveal credentials/i }));
    await waitFor(() => {
      expect(screen.getByText('username')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /re-lock credentials/i }));
    expect(screen.queryByText('username')).not.toBeInTheDocument();
    expect(screen.getByText('Credentials stored in Vault')).toBeInTheDocument();
    // Token is cached across the re-lock so subsequent reveals skip the
    // token prompt.
    expect(useUiStore.getState().operatorToken).toBe('ok');
  });
});
