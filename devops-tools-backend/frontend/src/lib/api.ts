/**
 * Typed API client for the DevOps Portal backend.
 *
 *  - All calls go through `api<T>(path, schema, init?)` which:
 *      1. Fetches a same-origin URL (so prod + dev + Tailscale Funnel all work).
 *      2. Throws `ApiError` on non-2xx.
 *      3. Validates the body with Zod and narrows the type.
 *
 *  - Helpers fall back to a hard-coded 3-tool seed if the endpoint is missing —
 *    this lets the frontend be developed in parallel with the backend. A console
 *    warning is emitted whenever the fallback is used.
 *
 *  - Contract note: backend returns BARE lists/maps (no wrapper object) and
 *    nests live health on `tool.health`. We flatten `tool.health` into
 *    `health_status / latency_ms / last_checked` at the API boundary so
 *    the rest of the UI can stay flat.
 */
import { z } from 'zod';
import {
  type Category,
  CategorySchema,
  type CredentialsResponse,
  CredentialsResponseSchema,
  type HealthEntry,
  HealthEntrySchema,
  type HealthMap,
  HealthMapSchema,
  type LaunchResponse,
  LaunchResponseSchema,
  type PipelineRun,
  PipelineRunSchema,
  type TailscaleStatus,
  TailscaleStatusSchema,
  type Tool,
  ToolSchema,
  type ChatResponse,
  ChatResponseSchema,
  type PipelineProgress,
  PipelineProgressSchema,
} from '@/types/tool';

/* ------------------------------------------------------------------------ */
/* Error type                                                                  */
/* ------------------------------------------------------------------------ */
export class ApiError extends Error {
  status: number;
  url: string;
  detail: string | undefined;
  constructor(message: string, status: number, url: string, detail?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.url = url;
    this.detail = detail;
  }
}

/* ------------------------------------------------------------------------ */
/* Core                                                                        */
/* ------------------------------------------------------------------------ */
async function api<T>(
  path: string,
  schema: z.ZodType<T>,
  init?: RequestInit
): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let detail: string | undefined;
    try {
      detail = await res.text();
    } catch {
      /* swallow */
    }
    throw new ApiError(
      `${init?.method ?? 'GET'} ${path} → ${res.status} ${res.statusText}`,
      res.status,
      path,
      detail
    );
  }
  const json: unknown = await res.json();
  const parsed = schema.safeParse(json);
  if (!parsed.success) {
    // Log the first 3 issues to keep console readable.
    const head = parsed.error.issues.slice(0, 3);
    console.error('[api] schema validation failed', path, head, json);
    throw new ApiError(
      `Schema validation failed for ${path}`,
      200,
      path,
      parsed.error.message
    );
  }
  return parsed.data;
}

/* ------------------------------------------------------------------------ */
/* Fallback seed — used only when /api/v1/portal/tools is missing             */
/* ------------------------------------------------------------------------ */
const FALLBACK_TOOLS: Tool[] = [
  {
    id: 'ollama',
    name: 'Ollama',
    category: 'ai',
    description:
      'Local LLM inference server — qwen3:32b, pipeline-generator-v5, nomic-embed.',
    icon: 'brain',
    url_internal: 'http://ollama:11434',
    url_external: 'http://localhost:11434',
    embed: false,
    tags: ['llm', 'inference', 'gpu', 'local-ai'],
    compose_project: 'infra-stack',
    container_name: 'ollama',
    health_status: 'unknown',
    latency_ms: null,
    last_checked: null,
  },
  {
    id: 'grafana',
    name: 'Grafana',
    category: 'observability',
    description: 'Dashboards for metrics, logs, traces. Primary obs UI.',
    icon: 'line-chart',
    url_internal: 'http://grafana:3000',
    url_external: 'http://localhost:3000',
    embed: true,
    tags: ['dashboards', 'metrics', 'logs'],
    compose_project: 'infra-stack',
    container_name: 'grafana',
    health_status: 'unknown',
    latency_ms: null,
    last_checked: null,
  },
  {
    id: 'devops-tools-backend',
    name: 'DevOps Tools API',
    category: 'platform',
    description:
      'FastAPI backend — tool catalog, pipeline generator, RL engine.',
    icon: 'server-cog',
    url_internal: 'http://devops-tools-backend:8003',
    url_external: 'http://localhost:8003',
    embed: false,
    tags: ['api', 'backend', 'fastapi'],
    compose_project: 'dev-stack',
    container_name: 'devops-tools-backend',
    docs_url: 'http://localhost:8003/docs',
    health_status: 'unknown',
    latency_ms: null,
    last_checked: null,
  },
];

const FALLBACK_CATEGORIES: Category[] = [
  { id: 'ai', name: 'AI & LLM', order: 1, color: '#7c3aed' },
  { id: 'observability', name: 'Observability', order: 7, color: '#06b6d4' },
  { id: 'platform', name: 'Platform API', order: 13, color: '#14b8a6' },
];

/* ------------------------------------------------------------------------ */
/* Flattening: backend ToolOut has nested `health`; UI wants flat fields      */
/* ------------------------------------------------------------------------ */
/**
 * `raw` is typed as `unknown` because inferring through Zod's
 * `.default(false)` + `.nullable().optional()` stack produces a slightly
 * different structural type at each call site (two "Tool" identities). The
 * inner body does the shape-narrowing + explicit cast back to `Tool`.
 */
function flattenHealth(raw: unknown): Tool {
  const t = raw as Tool;
  const nested = (raw as { health?: HealthEntry | null }).health;
  if (nested && typeof nested === 'object' && 'status' in nested) {
    return {
      ...t,
      health_status: nested.status,
      latency_ms: nested.latency_ms ?? t.latency_ms ?? null,
      last_checked: nested.last_checked ?? t.last_checked ?? null,
    };
  }
  return t;
}

/* ------------------------------------------------------------------------ */
/* Public helpers                                                              */
/* ------------------------------------------------------------------------ */
const ToolListSchema = z.array(ToolSchema);

export async function fetchTools(): Promise<Tool[]> {
  try {
    const list = await api('/api/v1/portal/tools', ToolListSchema);
    return list.map(flattenHealth);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 500)) {
      console.warn(
        '[portal] /api/v1/portal/tools unavailable — using 3-tool fallback seed'
      );
      return FALLBACK_TOOLS;
    }
    if (!(e instanceof ApiError)) {
      console.warn('[portal] network error fetching tools — using fallback seed', e);
      return FALLBACK_TOOLS;
    }
    throw e;
  }
}

export async function fetchTool(id: string): Promise<Tool> {
  const t = await api(
    `/api/v1/portal/tools/${encodeURIComponent(id)}`,
    ToolSchema
  );
  return flattenHealth(t);
}

const CategoriesListSchema = z.array(CategorySchema);
export async function fetchCategories(): Promise<Category[]> {
  try {
    return await api('/api/v1/portal/categories', CategoriesListSchema);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 500)) {
      console.warn('[portal] /api/v1/portal/categories unavailable — using fallback');
      return FALLBACK_CATEGORIES;
    }
    throw e;
  }
}

export async function fetchHealth(): Promise<HealthMap> {
  try {
    return await api('/api/v1/portal/health', HealthMapSchema);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 500)) {
      console.warn('[portal] /api/v1/portal/health unavailable — returning empty map');
      return {};
    }
    if (!(e instanceof ApiError)) {
      console.warn('[portal] network error fetching health', e);
      return {};
    }
    throw e;
  }
}

/** Force a re-probe of a single tool. Backend returns the single HealthStatus
 *  object (not a map); we wrap it so call sites can treat the result uniformly. */
export async function reprobeHealth(id: string): Promise<HealthMap> {
  try {
    const entry = await api(
      `/api/v1/portal/health/${encodeURIComponent(id)}`,
      HealthEntrySchema
    );
    return { [id]: entry };
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return {};
    throw e;
  }
}

export async function launchTool(id: string): Promise<LaunchResponse> {
  // Zod's `.default(false)` on `requires_auth` produces an optional-input
  // type at `z.input<...>` but a required-boolean output at `z.output<...>`.
  // `api<T>()` infers from `z.ZodType<T>`, which picks the input side here;
  // the exported `LaunchResponse` alias uses `z.infer` (output). Bridge the
  // two by narrowing through `unknown`.
  const parsed = await api(
    `/api/v1/portal/launch/${encodeURIComponent(id)}`,
    LaunchResponseSchema,
    { method: 'POST' },
  );
  return parsed as unknown as LaunchResponse;
}

/* ------------------------------------------------------------------------ */
/* Credentials reveal                                                         */
/* ------------------------------------------------------------------------ */
/**
 * Fetch stored credentials for a tool. Privileged endpoint — requires the
 * operator token to be supplied as the `X-Portal-Operator` header.
 *
 * Contract:
 *   200 → CredentialsResponse
 *   204 → no credentials available (returns null)
 *   401 → missing header    → ApiError "Operator token required"
 *   403 → wrong token       → ApiError "Operator token rejected"
 *   404 → tool not found    → ApiError "Tool not found"
 *   503 → disabled          → ApiError "Credentials endpoint disabled on backend"
 *
 * SECURITY:
 *   - Token is sent only via the X-Portal-Operator header, never as a query
 *     param or logged. Response validation is strict; any shape mismatch
 *     throws before the caller sees field values.
 */
export async function fetchCredentials(
  id: string,
  operatorToken: string
): Promise<CredentialsResponse | null> {
  const path = `/api/v1/portal/tools/${encodeURIComponent(id)}/credentials`;
  const res = await fetch(path, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
      'X-Portal-Operator': operatorToken,
    },
  });

  if (res.status === 204) return null;

  if (!res.ok) {
    let detail: string | undefined;
    try {
      detail = await res.text();
    } catch {
      /* swallow */
    }
    let msg: string;
    switch (res.status) {
      case 401:
        msg = 'Operator token required';
        break;
      case 403:
        msg = 'Operator token rejected';
        break;
      case 404:
        msg = 'Tool not found';
        break;
      case 503:
        msg = 'Credentials endpoint disabled on backend';
        break;
      default:
        msg = `GET ${path} → ${res.status} ${res.statusText}`;
    }
    throw new ApiError(msg, res.status, path, detail);
  }

  const json: unknown = await res.json();
  const parsed = CredentialsResponseSchema.safeParse(json);
  if (!parsed.success) {
    const head = parsed.error.issues.slice(0, 3);
    // Intentionally do NOT log `json` — it contains credential values.
    console.error('[api] credentials schema validation failed', path, head);
    throw new ApiError(
      `Schema validation failed for ${path}`,
      200,
      path,
      parsed.error.message
    );
  }
  return parsed.data;
}

export async function fetchTailscaleStatus(): Promise<TailscaleStatus> {
  try {
    return await api('/api/v1/portal/tailscale/status', TailscaleStatusSchema);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      return { state: 'local' };
    }
    if (!(e instanceof ApiError)) {
      return { state: 'local', error: 'network error' };
    }
    throw e;
  }
}

/* ------------------------------------------------------------------------ */
/* Pipelines (existing GitLab router)                                         */
/* ------------------------------------------------------------------------ */
/* The existing endpoint shape is legacy and may be either a bare array or
 * a wrapped `{pipelines: [...]}`. Accept both. */
const PipelinesSchema = z.union([
  z.array(PipelineRunSchema),
  z.object({ pipelines: z.array(PipelineRunSchema) }).transform((o) => o.pipelines),
]);
export async function fetchPipelines(): Promise<PipelineRun[]> {
  try {
    // The union + `.transform()` on one branch confuses TS into inferring
    // `PipelineRun[] | { pipelines: PipelineRun[] }` for the output, even
    // though the transform narrows to `PipelineRun[]` at runtime. Re-cast
    // the confirmed-list result via the shared transform contract.
    const raw = await api('/api/v1/gitlab/pipelines', PipelinesSchema);
    return raw as unknown as PipelineRun[];
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 500)) {
      return [];
    }
    if (!(e instanceof ApiError)) return [];
    throw e;
  }
}

/* ------------------------------------------------------------------------ */
/* Chat                                                                        */
/* ------------------------------------------------------------------------ */
export async function sendChat(
  message: string,
  conversationId: string | null,
  requestId?: string,
): Promise<ChatResponse> {
  return api('/api/v1/chat/', ChatResponseSchema, {
    method: 'POST',
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      request_id: requestId ?? null,
    }),
  });
}

export async function newConversation(): Promise<{ conversation_id: string }> {
  const schema = z.object({ conversation_id: z.string() });
  return api('/api/v1/chat/new', schema, { method: 'POST' });
}

/**
 * Live in-flight phase emitted by `_tool_run_pipeline` while the main
 * `/api/v1/chat/` POST is still working. The frontend polls every ~1.5s
 * keyed by the `request_id` it sent on the chat POST.
 *
 * Phase enum (loose — backend may add more):
 *   idle | analyzing | checking_rag | rag_hit | llm_validated | llm_fixed
 *   | committing | monitoring | validation_failed | error
 */
const ChatInflightSchema = z
  .object({
    phase: z.string(),
    message: z.string().optional(),
    ts: z.number().optional(),
    rag_hit: z.boolean().optional(),
    fix_attempts: z.number().optional(),
    language: z.string().optional(),
    framework: z.string().optional(),
    branch: z.string().optional(),
    gitlab_pipelines_url: z.string().optional(),
    repo_url: z.string().optional(),
    errors: z.array(z.string()).optional(),
  })
  .passthrough();
export type ChatInflight = z.infer<typeof ChatInflightSchema>;

export async function fetchChatInflight(key: string): Promise<ChatInflight> {
  return api(
    `/api/v1/chat/inflight/${encodeURIComponent(key)}`,
    ChatInflightSchema,
  );
}

/* ------------------------------------------------------------------------ */
/* Pipeline self-heal monitor — polled by the chat after `commit_pipeline`    */
/* ------------------------------------------------------------------------ */
/**
 * Poll the in-memory progress store for a (project_id, branch) pair.
 *
 * Endpoint: `GET /api/v1/pipeline/progress/{project_id}/{branch}`
 *
 *   • The branch segment is URL-encoded — branches like
 *     `feature/ai-pipeline-abc` contain slashes, and FastAPI's `branch:path`
 *     converter accepts the un-escaped slash, but we encode anyway so the
 *     client survives a tightening of the route in either direction.
 *   • If the backend hasn't started monitoring yet (or already evicted
 *     completed entries) the response is `{ found: false }` — the schema
 *     parses fine and the caller renders a "waiting…" state.
 *   • A 404 is also gracefully translated to `{ found: false }` so the
 *     poll loop doesn't bail on the first response that races backend
 *     monitor startup.
 */
export async function fetchPipelineProgress(
  projectId: number,
  branch: string,
): Promise<PipelineProgress> {
  const path = `/api/v1/pipeline/progress/${encodeURIComponent(
    String(projectId),
  )}/${encodeURIComponent(branch)}`;
  try {
    return await api(path, PipelineProgressSchema);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      return { found: false };
    }
    throw e;
  }
}
