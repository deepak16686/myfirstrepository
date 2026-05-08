/**
 * Canonical tool-registry schema mirrored from `config/tools.yaml`.
 * Source of truth: devops-tools-backend/config/tools.yaml
 */
import { z } from 'zod';

/* ------------------------------------------------------------------------ */
/* Enums                                                                      */
/* ------------------------------------------------------------------------ */
export const HealthStatusSchema = z.enum(['healthy', 'degraded', 'down', 'unknown']);
export type HealthStatus = z.infer<typeof HealthStatusSchema>;

export const CategoryIdSchema = z.enum([
  'ai',
  'cicd',
  'scm',
  'quality',
  'security',
  'registry',
  'observability',
  'metrics',
  'logging',
  'data',
  'pm',
  'gateway',
  'platform',
  'projects',
]);
export type CategoryId = z.infer<typeof CategoryIdSchema>;

/* ------------------------------------------------------------------------ */
/* Health probe definition                                                    */
/* ------------------------------------------------------------------------ */
const ProbeSpecSchema = z
  .object({
    method: z.string(),
    path: z.string().nullable().optional(),
    expect_status: z.union([z.number(), z.string(), z.array(z.number())]).nullable().optional(),
    command: z.array(z.string()).nullable().optional(),
    expect_exit_code: z.number().nullable().optional(),
  })
  .passthrough();

/* ------------------------------------------------------------------------ */
/* Live health entry (runtime probe result)                                   */
/* ------------------------------------------------------------------------ */
/* Declared before ToolSchema so the Tool.health field can reference it.
 * Backend sends the runtime health state under `tool.health`, and the
 * (config-only) probe spec under `tool.health_spec`. */
const LiveHealthSchema = z
  .object({
    status: HealthStatusSchema,
    latency_ms: z.number().nullable().optional(),
    last_checked: z.string().nullable().optional(),
    error: z.string().nullable().optional(),
    http_status: z.number().nullable().optional(),
    tool_id: z.string().optional(),
  })
  .passthrough();

/* ------------------------------------------------------------------------ */
/* Tool                                                                       */
/* ------------------------------------------------------------------------ */
export const ToolSchema = z.object({
  id: z.string(),
  name: z.string(),
  category: CategoryIdSchema,
  description: z.string(),
  icon: z.string(),
  url_internal: z.string().nullable().optional(),
  url_external: z.string().nullable().optional(),
  url_funnel: z.string().nullable().optional(),
  url_tailnet: z.string().nullable().optional(),
  health: LiveHealthSchema.nullable().optional(),
  health_spec: ProbeSpecSchema.nullable().optional(),
  credentials: z.string().nullable().optional(),
  embed: z.boolean().default(false),
  tags: z.array(z.string()).default([]),
  compose_project: z.string().nullable().optional(),
  container_name: z.string().nullable().optional(),
  docs_url: z.string().nullable().optional(),
  // Live health fields — enriched by backend
  health_status: HealthStatusSchema.optional(),
  latency_ms: z.number().nullable().optional(),
  last_checked: z.string().nullable().optional(),
});
export type Tool = z.infer<typeof ToolSchema>;

/* ------------------------------------------------------------------------ */
/* Category                                                                   */
/* ------------------------------------------------------------------------ */
export const CategorySchema = z.object({
  id: CategoryIdSchema,
  name: z.string(),
  order: z.number(),
  color: z.string().nullable().optional(),
  tool_count: z.number().optional(),
  healthy_count: z.number().optional(),
  healthy_pct: z.number().optional(),
});
export type Category = z.infer<typeof CategorySchema>;

/* ------------------------------------------------------------------------ */
/* Health map                                                                 */
/* ------------------------------------------------------------------------ */
/* Backend HealthStatus carries extra fields (tool_id, http_status); we
 * keep the response-shape Zod permissive via `.passthrough()` and only
 * narrow the fields the UI actually reads.
 */
export const HealthEntrySchema = z
  .object({
    status: HealthStatusSchema,
    latency_ms: z.number().nullable().optional(),
    last_checked: z.string().nullable().optional(),
    error: z.string().nullable().optional(),
    http_status: z.number().nullable().optional(),
    tool_id: z.string().optional(),
  })
  .passthrough();
export type HealthEntry = z.infer<typeof HealthEntrySchema>;

export const HealthMapSchema = z.record(z.string(), HealthEntrySchema);
export type HealthMap = z.infer<typeof HealthMapSchema>;

/* ------------------------------------------------------------------------ */
/* Launch response                                                            */
/* ------------------------------------------------------------------------ */
export const LaunchResponseSchema = z.object({
  redirect_url: z.string(),
  requires_auth: z.boolean().default(false),
  tool_id: z.string().optional(),
});
export type LaunchResponse = z.infer<typeof LaunchResponseSchema>;

/* ------------------------------------------------------------------------ */
/* Tailscale status                                                           */
/* ------------------------------------------------------------------------ */
export const TailscaleStatusSchema = z.object({
  state: z.enum(['live', 'local', 'down']),
  hostname: z.string().nullable().optional(),
  funnel_enabled: z.boolean().optional(),
  magic_dns: z.string().nullable().optional(),
  error: z.string().nullable().optional(),
});
export type TailscaleStatus = z.infer<typeof TailscaleStatusSchema>;

/* ------------------------------------------------------------------------ */
/* Chat (existing backend)                                                    */
/* ------------------------------------------------------------------------ */
export const ChatMessageSchema = z.object({
  role: z.enum(['user', 'assistant', 'system']),
  content: z.string(),
  id: z.string().optional(),
  ts: z.string().optional(),
});
export type ChatMessage = z.infer<typeof ChatMessageSchema>;

/**
 * After a successful `commit_pipeline` tool call the backend kicks off a
 * background self-healing monitor and surfaces the polling key on the
 * chat response. The frontend uses this hint to start polling
 * `/api/v1/pipeline/progress/{project_id}/{branch}`.
 *
 * The field is optional because:
 *   • non-commit messages don't trigger monitoring
 *   • older deploys may not include the field — Chat.tsx falls back to a
 *     regex on `message` when `monitoring` is absent.
 */
export const ChatMonitoringHintSchema = z.object({
  project_id: z.number(),
  branch: z.string(),
  self_healing_enabled: z.boolean().optional(),
  max_heal_attempts: z.number().optional(),
  monitor_mode: z.string().optional(),
});
export type ChatMonitoringHint = z.infer<typeof ChatMonitoringHintSchema>;

/**
 * Generation metadata attached to a chat response after a successful
 * `generate_pipeline` tool call. The backend populates this from
 * `app/services/pipeline/generator.py::generate_pipeline_files`:
 *   - `rag_hit=true`             → Priority-1 RAG short-circuit (chromadb-direct)
 *   - `fix_attempts>1`           → LLM single-shot needed N-1 fixer passes
 *   - `persisted_to_rag=true`    → fixer-validated pipeline saved for next time
 *   - `validation_passed=false`  → fixer exhausted 10 attempts; user should review
 */
export const ChatGenerationInfoSchema = z
  .object({
    template_source: z.string().nullable().optional(),
    source_token: z.string().nullable().optional(),
    rag_hit: z.boolean().nullable().optional(),
    had_rag_reference: z.boolean().nullable().optional(),
    fix_attempts: z.number().nullable().optional(),
    validation_passed: z.boolean().nullable().optional(),
    persisted_to_rag: z.boolean().nullable().optional(),
    model_used: z.string().nullable().optional(),
    language: z.string().nullable().optional(),
    framework: z.string().nullable().optional(),
  })
  .passthrough();
export type ChatGenerationInfo = z.infer<typeof ChatGenerationInfoSchema>;

export const ChatResponseSchema = z.object({
  message: z.string(),
  conversation_id: z.string(),
  pending_pipeline: z.unknown().nullable().optional(),
  monitoring: ChatMonitoringHintSchema.nullable().optional(),
  generation: ChatGenerationInfoSchema.nullable().optional(),
});
export type ChatResponse = z.infer<typeof ChatResponseSchema>;

/* ------------------------------------------------------------------------ */
/* Pipeline progress (live self-healing monitor)                              */
/* ------------------------------------------------------------------------ */
/**
 * Mirrors `app/services/pipeline_progress.py::PipelineProgress.to_dict()`.
 * Status enum is intentionally permissive: backend may add new stages
 * over time and we don't want a Zod failure to break the polling loop.
 */
export const PipelineProgressEventSchema = z.object({
  timestamp: z.string(),
  stage: z.string(),
  message: z.string(),
  attempt: z.number(),
  max_attempts: z.number(),
});
export type PipelineProgressEvent = z.infer<typeof PipelineProgressEventSchema>;

export const PipelineProgressSchema = z.object({
  found: z.boolean(),
  project_id: z.number().optional(),
  branch: z.string().optional(),
  status: z.string().optional(),
  current_message: z.string().optional(),
  attempt: z.number().optional(),
  max_attempts: z.number().optional(),
  pipeline_id: z.number().nullable().optional(),
  completed: z.boolean().optional(),
  model_used: z.string().nullable().optional(),
  fixer_model_used: z.string().nullable().optional(),
  events: z.array(PipelineProgressEventSchema).optional(),
  // Click-through URLs the user opens to watch the run live in GitLab.
  // `pipelines_browser_url` is the branch-filtered list page; populated
  // as soon as the monitor starts. `pipeline_web_url` is the deep link
  // to the specific pipeline run; populated once the monitor learns the
  // pipeline_id (typically within ~5s of the commit).
  pipelines_browser_url: z.string().nullable().optional(),
  pipeline_web_url: z.string().nullable().optional(),
  // Backend may also include a "message" field on the not-found branch.
  message: z.string().optional(),
});
export type PipelineProgress = z.infer<typeof PipelineProgressSchema>;

/* ------------------------------------------------------------------------ */
/* Credentials reveal                                                         */
/* ------------------------------------------------------------------------ */
/* Matches backend contract:
 *   GET /api/v1/portal/tools/{id}/credentials  (header: X-Portal-Operator)
 *   200 → { tool_id, source, fields: { ... }, retrieved_at }
 * `fields` is a free-form string map — values are opaque strings, not
 * limited to username/password.
 */
export const CredentialsResponseSchema = z.object({
  tool_id: z.string(),
  source: z.string(),
  fields: z.record(z.string(), z.string()),
  retrieved_at: z.string(),
});
export type CredentialsResponse = z.infer<typeof CredentialsResponseSchema>;

/* ------------------------------------------------------------------------ */
/* GitLab Pipelines (existing backend)                                        */
/* ------------------------------------------------------------------------ */
export const PipelineRunSchema = z.object({
  id: z.number(),
  project_id: z.number().optional(),
  project_name: z.string().optional(),
  ref: z.string().optional(),
  status: z.string(),
  sha: z.string().optional(),
  web_url: z.string().optional(),
  created_at: z.string().optional(),
  updated_at: z.string().optional(),
  duration: z.number().nullable().optional(),
  user: z
    .object({
      name: z.string().optional(),
      username: z.string().optional(),
    })
    .optional(),
});
export type PipelineRun = z.infer<typeof PipelineRunSchema>;
