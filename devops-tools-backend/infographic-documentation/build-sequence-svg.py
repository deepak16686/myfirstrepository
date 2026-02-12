"""
Build the GitHub Actions Pipeline Chat Interface - Request Flow Sequence Diagram.
Generates a large SVG with 14 participants, 103 steps, happy + failure paths.
"""

SVG_W = 2400
HEADER_H = 120
PARTICIPANT_H = 70
PARTICIPANT_Y = HEADER_H + 20
LIFELINE_START = PARTICIPANT_Y + PARTICIPANT_H + 10
STEP_H = 52  # vertical spacing per step
PHASE_GAP = 40  # extra gap between phases
MARGIN_LEFT = 30
MARGIN_RIGHT = 30

# 14 participants with colors
PARTICIPANTS = [
    ("User/Browser",      "Frontend app.js",         "#6366f1"),  # indigo
    ("Backend Router",    "github_pipeline.py /chat", "#8b5cf6"),  # violet
    ("Generator",         "generator.py facade",      "#a855f7"),  # purple
    ("Analyzer",          "analyzer.py",              "#7c3aed"),  # violet-dark
    ("Gitea API",         "External Service",         "#0ea5e9"),  # sky
    ("ChromaDB",          "Template Storage",          "#06b6d4"),  # cyan
    ("LLM",              "Ollama / Claude",            "#f59e0b"),  # amber
    ("Validator",         "validator.py",              "#10b981"),  # emerald
    ("Image Seeder",      "image_seeder.py",           "#14b8a6"),  # teal
    ("Nexus Registry",    "External Service",          "#0d9488"),  # teal-dark
    ("Committer",         "committer.py",              "#3b82f6"),  # blue
    ("Monitor",           "Background Task",           "#f97316"),  # orange
    ("LLM Fixer",         "github_llm_fixer.py",       "#ef4444"),  # red
    ("Learning",          "learning.py",               "#22c55e"),  # green
]

N_PARTS = len(PARTICIPANTS)
usable_w = SVG_W - MARGIN_LEFT - MARGIN_RIGHT
part_spacing = usable_w / N_PARTS
part_xs = [MARGIN_LEFT + part_spacing * i + part_spacing / 2 for i in range(N_PARTS)]

# Colors
GREEN = "#00d4aa"
GREEN_LIGHT = "#00e4bb"
ORANGE = "#ff6b35"
RED = "#ef4444"
GRAY = "#64748b"
TEXT_WHITE = "#e2e8f0"
TEXT_DIM = "#94a3b8"
BG = "#0f0f23"
CARD_BG = "rgba(26,26,46,0.92)"

# Step definitions: (step_num, from_idx, to_idx, label, color, is_dashed, is_return)
# from_idx/to_idx index into PARTICIPANTS (0-based)
# "self" arrows: from_idx == to_idx, drawn as a self-loop

# Phase structure: (phase_name, phase_color, steps_list)
PHASES = []

# Helper to get participant index
P = {name: i for i, (name, _, _) in enumerate(PARTICIPANTS)}
U = P["User/Browser"]
R = P["Backend Router"]
G = P["Generator"]
A = P["Analyzer"]
GI = P["Gitea API"]
C = P["ChromaDB"]
L = P["LLM"]
V = P["Validator"]
IS = P["Image Seeder"]
N = P["Nexus Registry"]
CO = P["Committer"]
M = P["Monitor"]
LF = P["LLM Fixer"]
LE = P["Learning"]

# PHASE 1: GENERATE
PHASES.append(("PHASE 1: REPOSITORY ANALYSIS", GREEN, [
    (1,  U,  R,  "POST /chat {message: repo_url, conversation_id}", GREEN, False, False),
    (2,  R,  R,  "_extract_url() -> _to_internal_url()", GREEN, False, False),
    (3,  R,  G,  "generate_with_validation(repo_url, token, model, max_fix=10)", GREEN, False, False),
    (4,  G,  G,  "generate_workflow_files()", GREEN, False, False),
    (5,  G,  A,  "analyze_repository(repo_url, token)", GREEN, False, False),
    (6,  A,  A,  "parse_github_url() -> owner/repo/host", GREEN, False, False),
    (7,  A,  GI, "GET /repos/{owner}/{repo}", GREEN, False, False),
    (8,  GI, A,  "{default_branch: 'main', ...}", GREEN, True, True),
    (9,  A,  GI, "GET /repos/{owner}/{repo}/contents?ref=main", GREEN, False, False),
    (10, GI, A,  "['pom.xml', 'src/', 'README.md', ...]", GREEN, True, True),
    (11, A,  A,  "detect: lang=java, framework=spring, pm=maven", GREEN, False, False),
    (12, A,  G,  "return analysis", GREEN, True, True),
]))

# PHASE 2: TEMPLATE LOOKUP
PHASES.append(("PHASE 2: TEMPLATE LOOKUP (ChromaDB RAG)", GREEN, [
    (13, G,  G,  "get_best_template_files('java', 'spring')", GREEN, False, False),
    (14, G,  C,  "POST collections/github_actions_successful_pipelines/get", GREEN, False, False),
    (15, C,  G,  "matching templates (or empty)", GREEN, True, True),
    (16, G,  G,  "DECISION: Template found? -> skip to validation", "#d97706", False, False),
]))

# PHASE 3: LLM GENERATION
PHASES.append(("PHASE 3: LLM GENERATION (if no ChromaDB template)", GREEN, [
    (17, G,  G,  "get_reference_workflow('java', 'spring')", GREEN, False, False),
    (18, G,  C,  "POST collections/github_actions_templates/get", GREEN, False, False),
    (19, C,  G,  "reference workflow or null", GREEN, True, True),
    (20, G,  G,  "_generate_with_llm(analysis, reference, context)", GREEN, False, False),
    (21, G,  L,  "POST /api/generate {prompt: lang+framework+rules+nexus}", GREEN, False, False),
    (22, L,  G,  "---DOCKERFILE--- ... ---GITHUB_ACTIONS--- ... ---END---", GREEN, True, True),
    (23, G,  G,  "_parse_llm_output() -> extract workflow + dockerfile", GREEN, False, False),
    (24, G,  V,  "_validate_and_fix_workflow() + _validate_and_fix_dockerfile()", GREEN, False, False),
    (25, V,  G,  "parse YAML, ensure env vars, self-hosted runners, on:true fix", GREEN, True, True),
    (26, G,  G,  "_ensure_learn_job() -> add learn-record job if missing", GREEN, False, False),
]))

# PHASE 4: ITERATIVE VALIDATION
PHASES.append(("PHASE 4: ITERATIVE LLM VALIDATION", GREEN, [
    (27, G,  LF, "iterative_fix(workflow, dockerfile, analysis, max=10)", GREEN, False, False),
    (28, LF, LF, "_validate_workflow() -> text checks: on:, jobs:, self-hosted", GREEN, False, False),
    (29, LF, LF, "If errors -> fix_pipeline(workflow, dockerfile, errors)", GREEN, False, False),
    (30, LF, L,  "POST /api/generate {fix prompt + errors + rules + images}", GREEN, False, False),
    (31, L,  LF, "fixed workflow + dockerfile", GREEN, True, True),
    (32, LF, LF, "parse + strip code fences -> updated files", GREEN, False, False),
    (33, LF, LF, "LOOP back to step 28 until valid or max attempts", "#d97706", True, False),
    (34, LF, G,  "{success, workflow, dockerfile, attempts, fix_history}", GREEN, True, True),
]))

# PHASE 5: IMAGE SEEDING
PHASES.append(("PHASE 5: NEXUS IMAGE SEEDING", GREEN, [
    (35, G,  IS, "ensure_images_in_nexus(workflow)", GREEN, False, False),
    (36, IS, IS, "extract_workflow_images() -> regex parse image refs", GREEN, False, False),
    (37, IS, N,  "GET /v2/apm-repo/demo/{image}/manifests/{tag}", GREEN, False, False),
    (38, N,  IS, "200 (exists) or 404 (missing)", GREEN, True, True),
    (39, IS, IS, "If missing: skopeo copy docker.io -> ai-nexus:5001", GREEN, True, False),
    (40, IS, G,  "{seeded: [...], already_exists: [...], failed: [...]}", GREEN, True, True),
]))

# PHASE 6: RESPONSE TO USER
PHASES.append(("PHASE 6: RESPONSE TO USER", GREEN, [
    (41, G,  R,  "return {success, workflow, dockerfile, analysis, model_used}", GREEN, True, True),
    (42, R,  R,  "store _chat_pending[conv_id] = {repo_url, workflow, ...}", GREEN, False, False),
    (43, R,  R,  "build response: source banner + lang/fw + validation + preview", GREEN, False, False),
    (44, R,  U,  "JSON {conversation_id, message: 'Generated... commit?'}", GREEN, True, True),
    (45, U,  U,  "Frontend displays workflow preview to user", GREEN, False, False),
]))

# PHASE 7: COMMIT
PHASES.append(("PHASE 7: COMMIT TO REPOSITORY", GREEN, [
    (46, U,  R,  "POST /chat {message: 'commit', conversation_id: uuid}", GREEN, False, False),
    (47, R,  R,  "_is_approval('commit') -> retrieve _chat_pending[conv_id]", GREEN, False, False),
    (48, R,  CO, "commit_to_github(repo_url, token, workflow, dockerfile)", GREEN, False, False),
    (49, CO, CO, "parse_github_url() -> owner/repo/host", GREEN, False, False),
    (50, CO, CO, "branch = 'ci-pipeline-20260212-HHMMSS'", GREEN, False, False),
    (51, CO, GI, "GET /repos/{owner}/{repo}/branches/main", GREEN, False, False),
    (52, GI, CO, "{commit: {id: 'abc123...'}}", GREEN, True, True),
    (53, CO, GI, "POST /repos/{owner}/{repo}/branches {new_branch, old_branch}", GREEN, False, False),
    (54, GI, CO, "201 branch created", GREEN, True, True),
    (55, CO, GI, "GET /contents/.github/workflows/ci.yml?ref=ci-pipeline-...", GREEN, False, False),
    (56, GI, CO, "404 (new file)", GREEN, True, True),
    (57, CO, GI, "POST /contents/.github/workflows/ci.yml {base64, branch}", GREEN, False, False),
    (58, GI, CO, "201 file created", GREEN, True, True),
    (59, CO, GI, "POST /contents/Dockerfile {base64, branch, message}", GREEN, False, False),
    (60, GI, CO, "201 file created", GREEN, True, True),
    (61, CO, R,  "{success, branch, commit_sha, web_url}", GREEN, True, True),
]))

# PHASE 8: START MONITORING
PHASES.append(("PHASE 8: START BACKGROUND MONITORING", GREEN, [
    (62, R,  R,  "progress_store.create(project_id, branch, max_attempts=10)", GREEN, False, False),
    (63, R,  M,  "background_tasks.add_task(monitor_workflow_for_learning)", GREEN, True, False),
    (64, R,  R,  "del _chat_pending[conversation_id]", GREEN, False, False),
    (65, R,  U,  "JSON {conv_id, message: 'Committed!', monitoring: {...}}", GREEN, True, True),
    (66, U,  R,  "setInterval -> GET /progress/{project_id}/{branch} (10s)", GREEN, True, False),
]))

# PHASE 9: MONITORING
PHASES.append(("PHASE 9: BACKGROUND MONITORING (async)", GREEN, [
    (67, M,  GI, "GET /repos/.../actions/runs?branch={branch}&limit=10", GREEN, True, False),
    (68, GI, M,  "{workflow_runs: [...]} with run status", GREEN, True, True),
    (69, M,  GI, "GET /repos/.../actions/runs/{run_id}/jobs", GREEN, True, False),
    (70, GI, M,  "job list with status/conclusion per job", GREEN, True, True),
    (71, M,  M,  "update progress_store: job status icons", GREEN, True, False),
    (72, U,  R,  "poll GET /progress -> render progress bar", GREEN, True, False),
]))

# PHASE 10A: SUCCESS
PHASES.append(("PHASE 10A: SUCCESS PATH", GREEN, [
    (73, M,  M,  "Gitea run conclusion: 'success'", GREEN, False, False),
    (74, M,  LE, "rl_record_build_result(repo_url, token, branch, run_id)", GREEN, False, False),
    (75, LE, GI, "GET /repos/.../actions/runs?branch={branch}", GREEN, False, False),
    (76, LE, GI, "GET /repos/.../raw/.github/workflows/ci.yml?ref={branch}", GREEN, False, False),
    (77, LE, GI, "GET /repos/.../raw/Dockerfile?ref={branch}", GREEN, False, False),
    (78, LE, LE, "store_successful_pipeline(workflow, dockerfile, lang, fw)", GREEN, False, False),
    (79, LE, C,  "POST /add to github_actions_successful_pipelines", GREEN, False, False),
    (80, M,  M,  "progress_store.complete -> 'Workflow succeeded!'", GREEN, False, False),
    (81, U,  U,  "poll -> completed=true -> stop polling -> show success", GREEN, False, False),
]))

# PHASE 10B: FAILURE + SELF-HEAL
PHASES.append(("PHASE 10B: FAILURE + SELF-HEAL PATH", ORANGE, [
    (82, M,  M,  "Gitea run conclusion: 'failure'", ORANGE, False, False),
    (83, M,  M,  "update progress: 'Fetching error logs for self-heal...'", ORANGE, False, False),
    (84, M,  GI, "GET /repos/.../actions/runs/{run_id}/jobs", ORANGE, False, False),
    (85, GI, M,  "job with conclusion='failure', job_id, job_name", ORANGE, True, True),
    (86, M,  GI, "GET /repos/.../actions/jobs/{job_id}/logs", ORANGE, False, False),
    (87, GI, M,  "raw log text (truncated to 8000 chars)", ORANGE, True, True),
    (88, M,  LF, "generate_fix(dockerfile, workflow, error_log, job_name)", ORANGE, False, False),
    (89, LF, LF, "identify_error_type: image_not_found / missing_nodejs / etc.", ORANGE, False, False),
    (90, LF, LF, "extract_key_errors: filter error/failed/exception/fatal", ORANGE, False, False),
    (91, LF, L,  "POST /api/generate {fix prompt + error log + error type}", ORANGE, False, False),
    (92, L,  LF, "fixed workflow + dockerfile", ORANGE, True, True),
    (93, LF, M,  "FixResult {success, workflow, dockerfile, explanation}", ORANGE, True, True),
    (94, M,  CO, "commit_to_github(fixed_workflow, fixed_dockerfile, same_branch)", ORANGE, False, False),
    (95, CO, GI, "GET /contents/ci.yml -> 200 -> PUT with SHA to update", ORANGE, False, False),
    (96, CO, GI, "GET /contents/Dockerfile -> 200 -> PUT with SHA to update", ORANGE, False, False),
    (97, GI, CO, "files updated -> triggers new workflow run", ORANGE, True, True),
    (98, M,  M,  "update progress: '[Fix 1/10] Re-committed. Monitoring...'", ORANGE, False, False),
    (99, M,  M,  "LOOP back to step 67 (monitor new workflow run)", "#d97706", True, False),
    (100, M, M,  "If succeeds -> go to step 73 (success path)", GREEN, True, False),
    (101, M, M,  "If fails again & attempts < max -> step 82 (self-heal)", ORANGE, True, False),
    (102, M, M,  "If max attempts reached -> 'Failed after 10 attempts'", RED, False, False),
    (103, U, U,  "poll -> completed=true -> stop -> show final result", ORANGE, False, False),
]))

# Calculate total height
total_steps = sum(len(phase[2]) for phase in PHASES)
total_phase_gaps = len(PHASES) * (PHASE_GAP + 40)  # 40 for phase header
SVG_H = LIFELINE_START + total_steps * STEP_H + total_phase_gaps + 200  # 200 for legend

def escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")

lines = []
w = lines.append

# SVG header
w(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SVG_W} {SVG_H}" width="{SVG_W}" height="{SVG_H}" font-family="\'Segoe UI\', system-ui, -apple-system, sans-serif">')

# Defs
w('<defs>')
# Arrow markers
for color, cid in [(GREEN, "green"), (ORANGE, "orange"), (RED, "red"), (GRAY, "gray"), ("#d97706", "amber")]:
    w(f'<marker id="arrow-{cid}" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">')
    w(f'  <polygon points="0 0, 10 3.5, 0 7" fill="{color}"/>')
    w(f'</marker>')
    w(f'<marker id="arrow-{cid}-rev" markerWidth="10" markerHeight="7" refX="1" refY="3.5" orient="auto">')
    w(f'  <polygon points="10 0, 0 3.5, 10 7" fill="{color}"/>')
    w(f'</marker>')

# Glow filters
w('<filter id="glow-green" x="-20%" y="-20%" width="140%" height="140%">')
w(f'  <feDropShadow dx="0" dy="0" stdDeviation="3" flood-color="{GREEN}" flood-opacity="0.5"/>')
w('</filter>')
w('<filter id="glow-orange" x="-20%" y="-20%" width="140%" height="140%">')
w(f'  <feDropShadow dx="0" dy="0" stdDeviation="3" flood-color="{ORANGE}" flood-opacity="0.5"/>')
w('</filter>')
w('<filter id="shadow" x="-4%" y="-4%" width="108%" height="108%">')
w('  <feDropShadow dx="1" dy="2" stdDeviation="2" flood-color="#000000" flood-opacity="0.4"/>')
w('</filter>')
# Grid pattern
w('<pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">')
w('  <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1a1a3e" stroke-width="0.5" opacity="0.3"/>')
w('</pattern>')
w('</defs>')

# Background
w(f'<rect width="{SVG_W}" height="{SVG_H}" fill="{BG}"/>')
w(f'<rect width="{SVG_W}" height="{SVG_H}" fill="url(#grid)"/>')

# Title bar
w(f'<rect x="0" y="0" width="{SVG_W}" height="{HEADER_H}" fill="rgba(15,15,35,0.95)" stroke="{GREEN}" stroke-width="0" />')
w(f'<line x1="0" y1="{HEADER_H}" x2="{SVG_W}" y2="{HEADER_H}" stroke="{GREEN}" stroke-width="1" opacity="0.4"/>')
w(f'<text x="{SVG_W//2}" y="42" fill="#ffffff" font-size="26" font-weight="700" text-anchor="middle">GitHub Actions Pipeline Chat Interface - Complete Request Flow</text>')
w(f'<text x="{SVG_W//2}" y="68" fill="{TEXT_DIM}" font-size="14" font-weight="400" text-anchor="middle">AI DevOps Platform  |  Sequence Diagram  |  14 Participants  |  103 Steps  |  10 Phases</text>')
w(f'<text x="{SVG_W//2}" y="90" fill="{GRAY}" font-size="12" font-weight="400" text-anchor="middle">FastAPI + Ollama/Claude + Gitea + ChromaDB + Nexus + Reinforcement Learning + Self-Healing</text>')
w(f'<text x="{SVG_W//2}" y="110" fill="{GRAY}" font-size="11" font-weight="400" text-anchor="middle" font-family="monospace">POST /api/v1/github-pipeline/chat</text>')

# Participant boxes
part_box_w = part_spacing - 8
for i, (name, subtitle, color) in enumerate(PARTICIPANTS):
    x = part_xs[i]
    bx = x - part_box_w / 2
    by = PARTICIPANT_Y
    w(f'<rect x="{bx}" y="{by}" width="{part_box_w}" height="{PARTICIPANT_H}" rx="6" fill="rgba(26,26,46,0.95)" stroke="{color}" stroke-width="1.5" filter="url(#shadow)"/>')
    w(f'<text x="{x}" y="{by+28}" fill="#ffffff" font-size="11" font-weight="700" text-anchor="middle">{escape(name)}</text>')
    w(f'<text x="{x}" y="{by+45}" fill="{TEXT_DIM}" font-size="9" font-weight="400" text-anchor="middle">{escape(subtitle)}</text>')
    # Number badge
    w(f'<circle cx="{bx+12}" cy="{by+12}" r="9" fill="{color}" opacity="0.8"/>')
    w(f'<text x="{bx+12}" y="{by+16}" fill="#fff" font-size="9" font-weight="700" text-anchor="middle">{i+1}</text>')

# Lifelines
lifeline_end = SVG_H - 140
for i, (_, _, color) in enumerate(PARTICIPANTS):
    x = part_xs[i]
    w(f'<line x1="{x}" y1="{LIFELINE_START}" x2="{x}" y2="{lifeline_end}" stroke="{color}" stroke-width="1" stroke-dasharray="4,4" opacity="0.25"/>')

# Draw phases and steps
cur_y = LIFELINE_START + 20

def draw_arrow(step_num, from_i, to_i, label, color, is_dashed, is_return, y):
    """Draw an arrow between two participants at height y."""
    x1 = part_xs[from_i]
    x2 = part_xs[to_i]

    # Color mapping for markers
    if color == GREEN or color == GREEN_LIGHT:
        marker_id = "green"
    elif color == ORANGE:
        marker_id = "orange"
    elif color == RED:
        marker_id = "red"
    elif color == "#d97706":
        marker_id = "amber"
    else:
        marker_id = "gray"

    dash = ' stroke-dasharray="6,3"' if is_dashed else ''
    opacity = '0.7' if is_return else '1'
    stroke_w = '1.2' if is_return else '1.5'

    # Step number badge
    badge_x = MARGIN_LEFT - 2
    w(f'<circle cx="{badge_x}" cy="{y}" r="11" fill="{color}" opacity="0.85"/>')
    w(f'<text x="{badge_x}" y="{y+4}" fill="#fff" font-size="8" font-weight="700" text-anchor="middle">{step_num}</text>')

    if from_i == to_i:
        # Self-arrow (loop) - drawn as a right-side bump
        x = part_xs[from_i]
        loop_w = 25
        w(f'<path d="M {x+6} {y-4} L {x+loop_w} {y-4} L {x+loop_w} {y+4} L {x+6} {y+4}" '
          f'fill="none" stroke="{color}" stroke-width="{stroke_w}"{dash} opacity="{opacity}" '
          f'marker-end="url(#arrow-{marker_id})"/>')
        # Label to the right of the loop
        label_x = x + loop_w + 10
        max_label_w = SVG_W - label_x - 10
    else:
        # Straight arrow
        # Offset endpoints slightly so arrows don't overlap lifelines
        if x2 > x1:
            ax1 = x1 + 4
            ax2 = x2 - 4
            marker = f'marker-end="url(#arrow-{marker_id})"'
        else:
            ax1 = x1 - 4
            ax2 = x2 + 4
            marker = f'marker-end="url(#arrow-{marker_id})"'

        w(f'<line x1="{ax1}" y1="{y}" x2="{ax2}" y2="{y}" '
          f'stroke="{color}" stroke-width="{stroke_w}"{dash} opacity="{opacity}" {marker}/>')

        # Label centered above the arrow
        label_x = (ax1 + ax2) / 2
        max_label_w = abs(ax2 - ax1) - 10

    # Truncate label if needed
    display_label = label
    est_char_w = 5.5  # approx px per char at font-size 9
    max_chars = int(max_label_w / est_char_w) if max_label_w > 40 else 60
    if len(display_label) > max_chars and max_chars > 10:
        display_label = display_label[:max_chars-3] + "..."

    label_color = color if not is_return else TEXT_DIM
    font_w = "400" if is_return else "500"
    label_y = y - 7

    if from_i == to_i:
        anchor = "start"
    else:
        anchor = "middle"

    w(f'<text x="{label_x}" y="{label_y}" fill="{label_color}" font-size="9" font-weight="{font_w}" '
      f'text-anchor="{anchor}" opacity="0.9">{escape(display_label)}</text>')

for phase_idx, (phase_name, phase_color, steps) in enumerate(PHASES):
    # Phase header
    cur_y += 10
    w(f'<rect x="{MARGIN_LEFT}" y="{cur_y}" width="{SVG_W - MARGIN_LEFT - MARGIN_RIGHT}" height="30" '
      f'rx="4" fill="rgba(26,26,46,0.8)" stroke="{phase_color}" stroke-width="1" opacity="0.9"/>')
    w(f'<text x="{SVG_W//2}" y="{cur_y+20}" fill="{phase_color}" font-size="12" font-weight="700" '
      f'text-anchor="middle" letter-spacing="1.5">{escape(phase_name)}</text>')
    cur_y += 30 + 15

    for step in steps:
        step_num, from_i, to_i, label, color, is_dashed, is_return = step
        draw_arrow(step_num, from_i, to_i, label, color, is_dashed, is_return, cur_y)
        cur_y += STEP_H

    cur_y += PHASE_GAP // 2

# Legend
legend_y = cur_y + 20
legend_x = MARGIN_LEFT + 20
w(f'<rect x="{MARGIN_LEFT}" y="{legend_y}" width="{SVG_W - MARGIN_LEFT - MARGIN_RIGHT}" height="100" '
  f'rx="8" fill="rgba(26,26,46,0.9)" stroke="{GRAY}" stroke-width="1"/>')
w(f'<text x="{legend_x}" y="{legend_y+22}" fill="#ffffff" font-size="13" font-weight="700">LEGEND</text>')

# Legend items - row 1
lx = legend_x + 80
ly = legend_y + 22
items_r1 = [
    (GREEN, False, "Happy Path (sync)"),
    (GREEN, True,  "Return / Async"),
    (ORANGE, False, "Self-Heal Path"),
    (RED, False, "Failure / Max Attempts"),
    ("#d97706", False, "Decision / Loop"),
]
for color, dashed, lbl in items_r1:
    dash = ' stroke-dasharray="6,3"' if dashed else ''
    w(f'<line x1="{lx}" y1="{ly-3}" x2="{lx+35}" y2="{ly-3}" stroke="{color}" stroke-width="2"{dash}/>')
    w(f'<text x="{lx+42}" y="{ly}" fill="{TEXT_DIM}" font-size="10" font-weight="400">{escape(lbl)}</text>')
    lx += 210

# Legend items - row 2
lx = legend_x
ly2 = legend_y + 50
w(f'<circle cx="{lx+10}" cy="{ly2}" r="10" fill="{GREEN}" opacity="0.85"/>')
w(f'<text x="{lx+10}" y="{ly2+4}" fill="#fff" font-size="8" font-weight="700" text-anchor="middle">N</text>')
w(f'<text x="{lx+26}" y="{ly2+4}" fill="{TEXT_DIM}" font-size="10">= Step Number</text>')

lx += 150
w(f'<rect x="{lx}" y="{ly2-12}" width="24" height="24" rx="4" fill="rgba(26,26,46,0.95)" stroke="#6366f1" stroke-width="1.5"/>')
w(f'<text x="{lx+30}" y="{ly2+4}" fill="{TEXT_DIM}" font-size="10">= Participant</text>')

lx += 150
w(f'<line x1="{lx}" y1="{ly2}" x2="{lx+30}" y2="{ly2}" stroke="#6366f1" stroke-width="1" stroke-dasharray="4,4" opacity="0.4"/>')
w(f'<text x="{lx+36}" y="{ly2+4}" fill="{TEXT_DIM}" font-size="10">= Lifeline</text>')

lx += 140
w(f'<text x="{lx}" y="{ly2+4}" fill="{TEXT_DIM}" font-size="10">Phases: 1-6 Generate &amp; Commit (green) | 7-9 Monitor (green/async) | 10A Success (green) | 10B Self-Heal (orange)</text>')

# Row 3 - stats
ly3 = legend_y + 75
w(f'<text x="{legend_x}" y="{ly3}" fill="{GRAY}" font-size="10" font-family="monospace">'
  f'14 Participants | 103 Steps | 11 Phases | 10 Max Self-Heal Attempts | Poll Interval: 30s (monitor) / 10s (frontend) | Log Truncation: 8000 chars</text>')

# Recalculate actual height before corner accents
actual_h = int(cur_y + 160)

# Corner accents (using actual_h)
for cx, cy, dx, dy in [(0,0,40,0), (0,0,0,40), (SVG_W,0,-40,0), (SVG_W,0,0,40),
                         (0,actual_h,40,0), (0,actual_h,0,-40), (SVG_W,actual_h,-40,0), (SVG_W,actual_h,0,-40)]:
    w(f'<line x1="{cx}" y1="{cy}" x2="{cx+dx}" y2="{cy+dy}" stroke="{GREEN}" stroke-width="2" opacity="0.3"/>')

w('</svg>')

svg_content = '\n'.join(lines)

# Update dimensions in SVG header
svg_content = svg_content.replace(f'viewBox="0 0 {SVG_W} {SVG_H}"', f'viewBox="0 0 {SVG_W} {actual_h}"')
svg_content = svg_content.replace(f'height="{SVG_H}"', f'height="{actual_h}"')
# Fix lifeline end and background rects
svg_content = svg_content.replace(f'y2="{lifeline_end}"', f'y2="{actual_h - 140}"')
svg_content = svg_content.replace(f'height="{SVG_H}" fill="#0f0f23"', f'height="{actual_h}" fill="#0f0f23"')
svg_content = svg_content.replace(f'height="{SVG_H}" fill="url(#grid)"', f'height="{actual_h}" fill="url(#grid)"')

output_path = r"d:\Repos\ai-folder\devops-tools-backend\infographic-documentation\request-flow-sequence-diagram.svg"
with open(output_path, 'w', encoding='utf-8') as f:
    f.write(svg_content)

print(f"SVG written to {output_path}")
print(f"Dimensions: {SVG_W} x {actual_h}")
print(f"Total steps: {sum(len(p[2]) for p in PHASES)}")
print(f"Total phases: {len(PHASES)}")
