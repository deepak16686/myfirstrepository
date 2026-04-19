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
    path: z.string().optional(),
    expect_status: z.union([z.number(), z.array(z.number())]).optional(),
    command: z.array(z.string()).optional(),
    expect_exit_code: z.number().optional(),
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
  health: ProbeSpecSchema.optional(),
  credentials: z.string().optional(),
  embed: z.boolean().default(false),
  tags: z.array(z.string()).default([]),
  compose_project: z.string().optional(),
  container_name: z.string().optional(),
  docs_url: z.string().optional(),
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

export const ChatResponseSchema = z.object({
  message: z.string(),
  conversation_id: z.string(),
});
export type ChatResponse = z.infer<typeof ChatResponseSchema>;

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
