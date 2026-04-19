# DevOps Portal — Frontend

Vite + React 19 + TypeScript + Tailwind CSS 4 + shadcn/ui single-page app that
unifies the 34+ locally-hosted DevOps, AI, and observability tools into one
command-center UI. Built for a keyboard-first operator who wants to scan
health, pivot between tools, and trigger actions without touching the mouse.

Backend contract: FastAPI at `http://localhost:8003`, endpoints under
`/api/v1/portal/*`, `/api/v1/chat/*`, `/api/v1/gitlab/*`. This SPA is mounted
by `app/main.py` via `StaticFiles` — its build output lands in `dist/` and is
served at `/`. No changes to the API contract were required for this polish
pass; the frontend consumes the bare-array `/portal/tools` and flattens
`/portal/health` client-side.

## Requirements

- Node.js **>= 20.11** (tested on 20 LTS and 22).
- `pnpm` (preferred) or `npm`.

## Quick start

```bash
# from this directory
pnpm install           # or: npm install
pnpm dev               # Vite dev server on http://localhost:5173, /api proxied to :8003
pnpm build             # typecheck + bundle into dist/
pnpm preview           # serve the prod bundle locally
pnpm lint              # eslint flat config, --max-warnings 0
pnpm typecheck         # tsc --build (strict mode, no any)
```

## How it is served in prod

1. `pnpm build` outputs `dist/index.html` + `dist/assets/*`.
2. `devops-tools-backend/app/main.py` mounts `dist/` via
   `StaticFiles(directory=..., html=True)` at `/`.
3. The same origin serves both SPA and API, so every `fetch('/api/...')` is
   same-origin — Tailscale Funnel sees one HTTPS endpoint, no CORS.

## Features at a glance

### Command palette (`⌘K` / `Ctrl+K`)

- Fuzzy search across every registered tool (name / id / description / tags)
  powered by `fuse.js` with weighted fields (name 0.5, id 0.25, description
  0.15, tags 0.1) at threshold 0.38.
- Three selection modes on a single highlighted result:
  - `Enter` → Launch in a new tab (calls `POST /api/v1/portal/launch/:id`,
    falls back to `url_external` on error).
  - `⌘Enter` / `Ctrl+Enter` → Embed inside the portal (`/embed/:id`).
  - `Alt+Enter` → Open the detail drawer.
- Navigation group collapses when a query is present. Actions group always
  visible (refresh, theme swap, copy portal URL, open GitLab/Grafana/Splunk,
  Tailscale info, sidebar & rail toggles).
- Renders via React portal over a blurred backdrop with a signal hairline and
  `animate-in fade-in-0 zoom-in-95 slide-in-from-top-4` reveal.

### Status rail

A condensed dot strip sitting between the topbar and the main content area.
Each dot is a tooltip-rich interactive target with:

- Color-coded status (`down → degraded → unknown → healthy`, trouble-first
  sorted).
- Tooltip with name/category/id, status label, latency (with "stale" after
  5 min), and time-since-last-probe.
- Aggregate count chip (`H / D / N`) that pulses on every snapshot change.
- Toggle button lives in the topbar (`Signal` / `SignalZero` icon).

### Tools page (`/tools`)

Three synchronized views (persist choice to `localStorage`):

- **Grid** — `ToolCard` tiles with conic-sheen hover, expandable tags,
  `layoutId`-shared hero element for the detail-drawer transition.
- **Table** — TanStack Table with virtualization (`@tanstack/react-virtual`
  engages above 25 rows), sortable columns, single grid template shared
  between header and rows so alignment is byte-perfect.
- **Compact** — dense two-line list with inline xs sparklines on `md+`
  screens for "how many tools can I see at once".

Sticky filter bar:

- View tab switcher with `motion.span layoutId="tools-view-underline"`
  spring-animated active pill.
- Saved-view chips — `All tools` / `AI` / `CI-CD` / `Down now`.
- URL-synced state — `?q=`, `?category=`, `?health=` are authoritative;
  browser back/forward preserves filter state.

### Dashboard (`/`)

- **Gradient KPI cards** with animated count-up (rAF-driven, ease-out-cubic,
  honours `prefers-reduced-motion`), conic gradient halo behind the value,
  and a tiny SVG sparkline fed by a 24-sample rolling buffer per KPI.
- **Critical strip** — compact band of every tool in `down` state.
- **Category heatmap** — 2/3/4/7 responsive grid, each cell color-mixed
  against `--card` by healthy%, clickable and deep-links to `/tools?category=…`.
- **Latency histogram** — 12-bucket log-scaled SVG with `p50/p95/max` dashed
  markers and a `--accent-signal → --accent-signal-alt` gradient fill.
- **Incidents strip** — last 6 health-state transitions derived from the
  client-side buffer, filtering the `unknown → healthy` boot noise.
- **Activity feed + top picks** — live-synthesised stream + one featured
  tool per category.

### Global motion / atmospherics

- Layered background: `grid-dots` (opacity 0.22 dark / 0.35 light) +
  slow-drifting `mesh-bg` radial gradients.
- Top progress bar (`FetchProgress`) that animates on every in-flight
  TanStack query or mutation.
- Sonner toasts slide from the right.
- Route transitions wrap `<Outlet/>` with `motion.div` + `AnimatePresence
  mode="wait"`.
- Double-ring focus style on every interactive surface.

### Accessibility

- `Skip to main content` link (keyboard-only) is the first focusable element.
- `aria-live="polite"` region announces every health transition.
- Cmdk list is `role="listbox"` with keyboard arrow + wrap navigation.
- Keyboard shortcut overlay (`?`) lists every shortcut by section.
- `prefers-reduced-motion` short-circuits the count-up animation and
  dampens the mesh drift.

### Themes

- **Light**, **Dark**, **System** (follows `prefers-color-scheme`), and
  **Cyberpunk** (neon magenta/cyan, maximal signal).
- Pre-paint script in `index.html` avoids FOUC — the chosen theme is applied
  before React mounts.

## Keyboard reference

| Shortcut       | Action                                              |
| -------------- | --------------------------------------------------- |
| `⌘K` / `Ctrl+K` | Open command palette                                |
| `/`            | Focus the topbar search                             |
| `?`            | Open the keyboard shortcut overlay                  |
| `Esc`          | Close the topmost overlay or drawer                 |
| `g d`          | Go to Overview                                      |
| `g t`          | Go to Tools                                         |
| `g p`          | Go to Pipelines                                     |
| `g c`          | Go to AI Chat                                       |
| `t`            | Toggle dark / light theme                           |
| `\`            | Collapse / expand sidebar                           |
| `⌘⇧R`          | Invalidate every TanStack query (full refetch)      |
| `Enter`        | (In palette) Launch highlighted tool                |
| `⌘Enter`       | (In palette) Embed highlighted tool                 |
| `Alt+Enter`    | (In palette) Open detail drawer for highlighted tool |

## Project layout

```
src/
  main.tsx                 React entry + QueryClient + global overlays + dev devtools
  App.tsx                  <RouterProvider router={router}/>
  router.tsx               createBrowserRouter; Dashboard/Tools eager, Embed/Pipelines/Chat lazy
  index.css                Tailwind 4 entry + shadcn tokens + @utility blocks + keyframes

  lib/
    utils.ts               cn, formatLatency (w/ stale), timeAgo, modKey, prefersReducedMotion
    api.ts                 Typed fetch, Zod-validated responses, fallback seeds, health buffer
    icons.ts               string -> LucideIcon
    status.tsx             statusMeta(status) -> { label, shortLabel, text, signal }

  hooks/
    useTools.ts            /portal/tools
    useHealth.ts           /portal/health — polled every 15s
    useTheme.ts            light | dark | system | cyberpunk (persisted, FOUC-safe)

  store/
    ui.ts                  sidebar, drawer, palette, rail, shortcuts, toolsView, savedView

  types/
    tool.ts                Zod schemas

  components/
    ui/                    shadcn primitives (new-york style)
    layout/                Sidebar, Topbar, AppShell
    common/
      CommandBar           / search
      CommandPalette       ⌘K palette
      CountUpNumber        rAF count-up
      FetchProgress        top progress bar
      GlobalShortcuts      key handler for the whole app
      PageHeader           page title/eyebrow/description/actions
      ShortcutsDialog      ? overlay
      StatusAnnouncer      aria-live transitions
      StatusRail           33-dot condensed rail
      TailscaleChip        live tailnet indicator
      ThemeToggle          4-option menu
    tools/
      HealthDot, HealthSparkline, ToolCard, ToolsFilterBar, ToolsTableView,
      ToolsCompactView, ToolDetailDrawer
    dashboard/
      KpiCard, CriticalStrip, ActivityFeed, CategoryHeatmap,
      LatencyHistogram, IncidentsStrip

  pages/
    Dashboard.tsx          Eager
    Tools.tsx              Eager
    EmbedView.tsx          Lazy
    Pipelines.tsx          Lazy
    Chat.tsx               Lazy
    NotFound.tsx           Lazy
```

## Fallback / offline seed

`lib/api.ts` ships a hard-coded 3-tool fallback that is returned only when
the real `/api/v1/portal/tools` request throws (network or 404). A
`console.warn` is emitted so it is visible during parallel backend
development.

## Production build + serve (from repo root)

```bash
cd devops-tools-backend/frontend
pnpm install
pnpm build

cd ..
python -m uvicorn app.main:app --host 0.0.0.0 --port 8003
# Portal: http://localhost:8003/
```

## Verify locally on docker-desktop

```bash
# Dev server with live reload
pnpm dev
# Visit http://localhost:5173 — /api calls are proxied to :8003

# Prod bundle sanity
pnpm build && pnpm preview
# Visit http://localhost:4173

# Full integrated flow (via FastAPI static mount)
cd devops-tools-backend && python -m uvicorn app.main:app --port 8003
# Visit http://localhost:8003/
```

## Rollback

All changes live under `devops-tools-backend/frontend/` on the current
branch. To roll back the polish pass:

```bash
git restore --staged --worktree -- devops-tools-backend/frontend
```

No backend, no Docker, no Terraform artefacts were touched.
