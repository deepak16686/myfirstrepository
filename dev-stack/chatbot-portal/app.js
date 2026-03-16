/**
 * AI DevOps Chat Portal - app.js
 * Unified chatbot portal integrating all DevOps tools via the backend API.
 */

// ============================================================
// BASE URL DETECTION
// Works both when accessed directly (localhost:3005) and via
// nginx-proxy (https://deepak-desktop.tailac51e7.ts.net/chatbot/)
// ============================================================
const TAILSCALE_BASE = 'https://deepak-desktop.tailac51e7.ts.net';
const IS_TAILSCALE = window.location.hostname.includes('tailac51e7.ts.net')
    || window.location.hostname.includes('tailscale');

// When accessed via Tailscale (/chatbot/), API calls go to /api/v1/...
// nginx-proxy handles /api/ -> devops-tools-backend:8003
// When accessed directly (localhost:3005), the portal's own nginx proxies /api/ -> backend
// Either way, /api/v1/... works as-is because window.location.origin resolves correctly.

function tsUrl(path) {
    // Return a Tailscale-absolute URL for inter-tool links
    return `${TAILSCALE_BASE}${path}`;
}

// ============================================================
// TOOL REGISTRY
// ============================================================
const TOOL_REGISTRY = [
    {
        categoryId: 'pipelines',
        categoryName: 'Pipeline Generators',
        categoryIcon: '⚙️',
        tools: [
            {
                id: 'gitlab-pipeline',
                name: 'GitLab Pipeline',
                icon: '🦊',
                desc: 'Generate .gitlab-ci.yml + Dockerfile for any project',
                endpoint: '/api/v1/chat/',
                type: 'chat',
                tags: ['GitLab', 'CI/CD'],
                quickPrompts: [
                    'Generate a pipeline for http://gitlab-server/ai-pipeline-projects/java-springboot-api',
                    'Generate a pipeline for a Python FastAPI project',
                    'Generate a pipeline for a Node.js Express application',
                ],
                welcome: `## GitLab Pipeline Generator 🦊

I analyze your repository and generate production-ready CI/CD files:

- **\`.gitlab-ci.yml\`** — 9-stage pipeline (compile → build → test → sast → quality → security → push → notify → learn)
- **\`Dockerfile\`** — Multi-stage build optimized for your stack

**Supported stacks:** Java/Spring Boot, Python/FastAPI, Node.js/Express, Go, Ruby

---

**Get started:** Paste a GitLab repository URL

> Example: \`Generate a pipeline for http://gitlab-server/ai-pipeline-projects/java-springboot-api\``,
            },
            {
                id: 'jenkins-pipeline',
                name: 'Jenkins Pipeline',
                icon: '🔧',
                desc: 'Generate Jenkinsfile + Dockerfile for Gitea repos',
                endpoint: '/api/v1/jenkins-pipeline/chat',
                type: 'chat',
                tags: ['Jenkins', 'Groovy'],
                quickPrompts: [
                    'Generate a Jenkinsfile for http://localhost:3002/jenkins-projects/java-springboot-api',
                    'Create a Jenkins pipeline for Python FastAPI',
                    'Generate a pipeline for a Go application',
                ],
                welcome: `## Jenkins Pipeline Generator 🔧

I generate **Jenkinsfile** (Declarative) + **Dockerfile** with a full 9-stage pipeline:

\`\`\`
Compile → Build Image → Test → Static Analysis → SonarQube → Trivy → Push → Notify → Learn
\`\`\`

**Repos:** Stored in Gitea under \`jenkins-projects\` org

---

**Get started:** Paste a Gitea repository URL

> Example: \`Generate a pipeline for http://localhost:3002/jenkins-projects/java-springboot-api\`

**Commands after generation:**
- \`commit\` — commit files to the repository
- \`status\` — check Jenkins build status`,
            },
            {
                id: 'github-actions',
                name: 'GitHub Actions',
                icon: '🐙',
                desc: 'Generate .github/workflows YAML for Gitea repos',
                endpoint: '/api/v1/github-pipeline/chat',
                type: 'chat',
                tags: ['GitHub Actions', 'YAML'],
                quickPrompts: [
                    'Generate a workflow for http://localhost:3002/github-projects/java-springboot-api',
                    'Create a GitHub Actions workflow for Python project',
                    'Generate a workflow for Node.js application',
                ],
                welcome: `## GitHub Actions Generator 🐙

I generate **\`.github/workflows/pipeline.yml\`** + **\`Dockerfile\`** with a full 9-job workflow:

\`\`\`
compile → build-image → test-image → static-analysis → sonarqube → trivy-scan → push-release → notify → learn-record
\`\`\`

**Repos:** Stored in Gitea under \`github-projects\` org

---

**Get started:** Paste a Gitea repository URL

> Example: \`Generate a workflow for http://localhost:3002/github-projects/java-springboot-api\`

**Commands after generation:**
- \`commit\` — commit files to the repository
- \`status\` — check workflow run status`,
            },
        ],
    },
    {
        categoryId: 'iac',
        categoryName: 'Infrastructure as Code',
        categoryIcon: '🌍',
        tools: [
            {
                id: 'terraform',
                name: 'Terraform Generator',
                icon: '🏗️',
                desc: 'Generate Terraform configs for vSphere, Azure, AWS, GCP',
                endpoint: '/api/v1/terraform/chat',
                type: 'chat',
                tags: ['Terraform', 'HCL'],
                quickPrompts: [
                    'Generate Azure AKS cluster Terraform config with 3 nodes',
                    'Create vSphere VM configuration for Ubuntu 22.04',
                    'Generate AWS EKS cluster with auto-scaling',
                    'Create GCP GKE cluster Terraform configuration',
                ],
                welcome: `## Terraform Generator 🏗️

I generate **Infrastructure as Code** configurations for multiple cloud providers:

| Provider | Resources |
|----------|-----------|
| ☁️ **Azure** | AKS, VMs, VNets, PostgreSQL, Redis |
| 🏢 **vSphere** | VMs, clusters, networking |
| 🔶 **AWS** | EKS, EC2, VPC, RDS |
| 🔵 **GCP** | GKE, Compute, CloudSQL |

---

**Get started:** Tell me what infrastructure you need

> Examples:
> - \`Generate Azure AKS cluster with 3 nodes and auto-scaling\`
> - \`Create a vSphere VM with 4 vCPU, 8GB RAM, Ubuntu 22.04\``,
            },
        ],
    },
    {
        categoryId: 'security',
        categoryName: 'Security & Compliance',
        categoryIcon: '🔒',
        tools: [
            {
                id: 'dependency-scanner',
                name: 'Dependency Scanner',
                icon: '🛡️',
                desc: 'Scan dependencies for CVEs and vulnerabilities',
                type: 'redirect',
                redirect: tsUrl('/devops-api/'),
                tags: ['CVE', 'Security'],
            },
            {
                id: 'compliance-checker',
                name: 'Compliance Checker',
                icon: '✅',
                desc: 'Check security and compliance policies',
                type: 'redirect',
                redirect: tsUrl('/devops-api/'),
                tags: ['Compliance', 'Policy'],
            },
            {
                id: 'secret-manager',
                name: 'Secret Manager',
                icon: '🔑',
                desc: 'Manage HashiCorp Vault secrets',
                type: 'redirect',
                redirect: tsUrl('/devops-api/'),
                tags: ['Vault', 'Secrets'],
            },
        ],
    },
    {
        categoryId: 'observability',
        categoryName: 'Observability & SRE',
        categoryIcon: '📊',
        tools: [
            {
                id: 'connectivity',
                name: 'Connectivity Validator',
                icon: '🔗',
                desc: 'Test connectivity to all DevOps tools',
                type: 'redirect',
                redirect: tsUrl('/devops-api/'),
                tags: ['Health', 'Monitoring'],
            },
            {
                id: 'release-notes',
                name: 'Release Notes',
                icon: '📋',
                desc: 'Generate automated release documentation',
                type: 'redirect',
                redirect: tsUrl('/devops-api/'),
                tags: ['Documentation'],
            },
            {
                id: 'migration-assistant',
                name: 'Migration Assistant',
                icon: '🔄',
                desc: 'Legacy system modernization assistant',
                type: 'redirect',
                redirect: tsUrl('/devops-api/'),
                tags: ['Migration'],
            },
        ],
    },
    {
        categoryId: 'management',
        categoryName: 'Management',
        categoryIcon: '⚙️',
        tools: [
            {
                id: 'commit-history',
                name: 'Commit History',
                icon: '📜',
                desc: 'Browse repository commit history',
                type: 'redirect',
                redirect: tsUrl('/devops-api/'),
                tags: ['Git'],
            },
            {
                id: 'chromadb-browser',
                name: 'ChromaDB Browser',
                icon: '🗃️',
                desc: 'Browse vector database pipeline templates',
                type: 'redirect',
                redirect: tsUrl('/devops-api/'),
                tags: ['ChromaDB'],
            },
            {
                id: 'access-manager',
                name: 'Access Manager',
                icon: '👥',
                desc: 'RBAC user groups and access management',
                type: 'redirect',
                redirect: tsUrl('/devops-api/'),
                tags: ['RBAC'],
            },
            {
                id: 'tool-directory',
                name: 'Tool Directory',
                icon: '📚',
                desc: 'View all configured tools and their status',
                type: 'redirect',
                redirect: tsUrl('/devops-api/'),
                tags: ['Directory'],
            },
        ],
    },
];

// Flat tool map for quick lookup
const TOOL_MAP = {};
TOOL_REGISTRY.forEach(cat => cat.tools.forEach(t => { TOOL_MAP[t.id] = t; }));

// ============================================================
// STATE
// ============================================================
let currentTool = null;
let isLoading = false;

// Per-tool conversation state (persisted to localStorage)
function getConvState(toolId) {
    try {
        const raw = localStorage.getItem(`conv_${toolId}`);
        return raw ? JSON.parse(raw) : { conversationId: null, messages: [] };
    } catch { return { conversationId: null, messages: [] }; }
}
function setConvState(toolId, state) {
    try { localStorage.setItem(`conv_${toolId}`, JSON.stringify(state)); } catch {}
}

// ============================================================
// INIT
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    setupMarked();
    renderSidebar();
    renderQuickToolGrid();
    renderQuickLinks();
    setupInput();
    setupSidebarToggle();
    checkApiHealth();
    loadLLMInfo();
});

function setupMarked() {
    marked.setOptions({
        highlight(code, lang) {
            if (lang && hljs.getLanguage(lang)) {
                return hljs.highlight(code, { language: lang }).value;
            }
            return hljs.highlightAuto(code).value;
        },
        breaks: true,
        gfm: true,
    });

    // Custom renderer for code blocks with copy buttons
    const renderer = new marked.Renderer();
    renderer.code = function(code, language) {
        const lang = language || 'plaintext';
        let highlighted;
        try {
            highlighted = hljs.getLanguage(lang)
                ? hljs.highlight(code, { language: lang }).value
                : hljs.highlightAuto(code).value;
        } catch { highlighted = code; }
        const escapedCode = code.replace(/"/g, '&quot;').replace(/`/g, '&#96;');
        return `<div class="code-block-wrapper">
  <div class="code-block-header">
    <span class="code-lang-label">${lang}</span>
    <button class="code-copy-btn" onclick="copyCode(this)" data-code="${escapedCode}">Copy</button>
  </div>
  <pre><code class="hljs language-${lang}">${highlighted}</code></pre>
</div>`;
    };
    marked.use({ renderer });
}

// ============================================================
// SIDEBAR RENDERING
// ============================================================
function renderSidebar() {
    const nav = document.getElementById('toolNav');
    nav.innerHTML = '';

    TOOL_REGISTRY.forEach(category => {
        const catEl = document.createElement('div');
        catEl.className = 'tool-nav-category';
        catEl.id = `cat-${category.categoryId}`;

        const header = document.createElement('div');
        header.className = 'tool-nav-category-header';
        header.innerHTML = `
            <span class="cat-icon">${category.categoryIcon}</span>
            <span>${category.categoryName}</span>
            <span class="cat-chevron">▼</span>
        `;
        header.addEventListener('click', () => catEl.classList.toggle('collapsed'));

        const items = document.createElement('div');
        items.className = 'tool-nav-items';

        category.tools.forEach(tool => {
            const item = document.createElement('div');
            item.className = 'tool-nav-item';
            item.id = `nav-${tool.id}`;
            item.dataset.toolId = tool.id;
            const typeLabel = tool.type === 'chat' ? 'CHAT' : 'LINK';
            const typeClass = tool.type === 'chat' ? 'chat' : 'link';
            item.innerHTML = `
                <span class="tool-nav-icon">${tool.icon}</span>
                <span class="tool-nav-label">${tool.name}</span>
                <span class="tool-nav-type ${typeClass}">${typeLabel}</span>
            `;
            item.addEventListener('click', () => openTool(tool.id));
            items.appendChild(item);
        });

        catEl.appendChild(header);
        catEl.appendChild(items);
        nav.appendChild(catEl);
    });
}

function renderQuickLinks() {
    const links = [
        { icon: '🏠', label: 'Service Dashboard', href: tsUrl('/') },
        { icon: '⚙️', label: 'Full Dev Portal', href: tsUrl('/devops-api/') },
        { icon: '📖', label: 'API Docs', href: tsUrl('/devops-api/docs') },
        { icon: '📈', label: 'Grafana', href: tsUrl('/grafana/') },
        { icon: '🔧', label: 'Jenkins', href: tsUrl('/jenkins/') },
        { icon: '🐙', label: 'Gitea', href: tsUrl('/gitea/') },
        { icon: '🦊', label: 'GitLab', href: tsUrl('/gitlab/') },
        { icon: '🔍', label: 'SonarQube', href: tsUrl('/sonarqube/') },
        { icon: '🔑', label: 'Vault', href: tsUrl('/vault/') },
        { icon: '🔥', label: 'Prometheus', href: tsUrl('/prometheus/') },
    ];
    const container = document.getElementById('quickLinks');
    if (!container) return;
    container.innerHTML = links.map(l => `
        <a href="${l.href}" target="_blank" class="quick-link">
            <span>${l.icon}</span> ${l.label}
        </a>
    `).join('');
}

function renderQuickToolGrid() {
    const grid = document.getElementById('quickToolGrid');
    // Show only chat tools on welcome screen
    const chatTools = [];
    TOOL_REGISTRY.forEach(cat => cat.tools.forEach(t => {
        if (t.type === 'chat') chatTools.push(t);
    }));

    grid.innerHTML = chatTools.map(tool => `
        <div class="quick-tool-card" onclick="openTool('${tool.id}')">
            <div class="quick-card-icon">${tool.icon}</div>
            <div class="quick-card-info">
                <div class="quick-card-name">${tool.name}</div>
                <div class="quick-card-desc">${tool.desc}</div>
            </div>
        </div>
    `).join('');
}

// ============================================================
// SIDEBAR TOGGLE
// ============================================================
function setupSidebarToggle() {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('sidebarToggle');
    const savedCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
    if (savedCollapsed) sidebar.classList.add('collapsed');

    toggleBtn.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
        localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
    });
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('mobile-open');
}

// ============================================================
// THEME
// ============================================================
function toggleTheme() {
    const html = document.documentElement;
    const isDark = html.dataset.theme === 'dark';
    html.dataset.theme = isDark ? 'light' : 'dark';
    document.getElementById('themeIcon').textContent = isDark ? '☀️' : '🌙';
    localStorage.setItem('theme', html.dataset.theme);
}

// Restore saved theme
const savedTheme = localStorage.getItem('theme');
if (savedTheme) {
    document.documentElement.dataset.theme = savedTheme;
    document.addEventListener('DOMContentLoaded', () => {
        document.getElementById('themeIcon').textContent = savedTheme === 'light' ? '☀️' : '🌙';
    });
}

// ============================================================
// API HEALTH
// ============================================================
async function checkApiHealth() {
    const dot = document.getElementById('healthDot');
    const text = document.getElementById('healthText');
    dot.className = 'health-indicator checking';
    text.textContent = 'Checking...';

    try {
        const res = await fetch('/health', { signal: AbortSignal.timeout(5000) });
        if (res.ok) {
            dot.className = 'health-indicator online';
            text.textContent = 'Backend online';
        } else {
            dot.className = 'health-indicator offline';
            text.textContent = `Backend error (${res.status})`;
        }
    } catch {
        dot.className = 'health-indicator offline';
        text.textContent = 'Backend offline';
    }
}

async function loadLLMInfo() {
    try {
        const res = await fetch('/api/v1/llm-settings/current');
        if (res.ok) {
            const data = await res.json();
            const label = data.provider
                ? `${data.provider}${data.model ? ' · ' + data.model : ''}`
                : 'LLM';
            document.getElementById('llmLabel').textContent = label;
        }
    } catch {
        document.getElementById('llmLabel').textContent = 'LLM';
    }
}

// ============================================================
// TOOL OPEN / CLOSE
// ============================================================
function openTool(toolId) {
    const tool = TOOL_MAP[toolId];
    if (!tool) return;

    currentTool = toolId;

    // Update sidebar active state
    document.querySelectorAll('.tool-nav-item').forEach(el => el.classList.remove('active'));
    const navItem = document.getElementById(`nav-${toolId}`);
    if (navItem) navItem.classList.add('active');

    // Update header
    document.getElementById('headerToolIcon').textContent = tool.icon;
    document.getElementById('headerToolName').textContent = tool.name;
    document.getElementById('headerToolStatus').textContent = tool.type === 'chat'
        ? 'Chat mode · AI-powered'
        : 'Opens in full portal';

    if (tool.type === 'redirect') {
        showRedirectView(tool);
        disableInput();
    } else {
        showChatView(tool);
        enableInput(tool);
    }
}

function showRedirectView(tool) {
    hideAllViews();
    const view = document.getElementById('redirectView');
    view.classList.remove('hidden');
    document.getElementById('redirectIcon').textContent = tool.icon;
    document.getElementById('redirectTitle').textContent = tool.name;
    document.getElementById('redirectDesc').textContent = tool.desc + '. This tool has a dedicated interface in the full portal.';
    document.getElementById('redirectLink').href = tool.redirect || 'http://localhost:8003';
}

function showChatView(tool) {
    hideAllViews();
    const view = document.getElementById('chatView');
    view.classList.remove('hidden');

    const container = document.getElementById('messagesContainer');
    container.innerHTML = '';

    // Load or initialize conversation
    const convState = getConvState(tool.id);
    if (convState.messages && convState.messages.length > 0) {
        // Restore previous conversation
        convState.messages.forEach(msg => {
            appendMessage(msg.role, msg.content, false);
        });
        updateConvIdDisplay(convState.conversationId);
        scrollToBottom();
    } else {
        // Show welcome message
        if (tool.welcome) {
            appendMessage('assistant', tool.welcome, false);
        }
    }
}

function hideAllViews() {
    document.getElementById('welcomeScreen').classList.add('hidden');
    document.getElementById('chatView').classList.add('hidden');
    document.getElementById('redirectView').classList.add('hidden');
}

// ============================================================
// INPUT SETUP
// ============================================================
function setupInput() {
    const input = document.getElementById('messageInput');
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    input.addEventListener('input', autoResizeTextarea);
}

function autoResizeTextarea() {
    const ta = document.getElementById('messageInput');
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
}

function enableInput(tool) {
    const input = document.getElementById('messageInput');
    const btn = document.getElementById('sendBtn');
    input.disabled = false;
    btn.disabled = false;
    input.placeholder = tool.quickPrompts?.[0]
        ? `Try: "${tool.quickPrompts[0].substring(0, 60)}..."`
        : 'Type your message...';
    input.focus();

    // Update input toolbar
    document.getElementById('inputToolIcon').textContent = tool.icon;
    document.getElementById('inputToolName').textContent = tool.name;

    const convState = getConvState(tool.id);
    updateConvIdDisplay(convState.conversationId);
}

function disableInput() {
    document.getElementById('messageInput').disabled = true;
    document.getElementById('sendBtn').disabled = true;
    document.getElementById('messageInput').placeholder = 'Select a chat tool to start messaging';
    document.getElementById('inputToolIcon').textContent = '🔗';
    document.getElementById('inputToolName').textContent = 'No chat tool selected';
    document.getElementById('convIdDisplay').textContent = '';
}

function updateConvIdDisplay(convId) {
    const el = document.getElementById('convIdDisplay');
    el.textContent = convId ? `conv: ${convId.substring(0, 16)}...` : '';
}

// ============================================================
// SEND MESSAGE
// ============================================================
async function sendMessage() {
    if (!currentTool || isLoading) return;

    const tool = TOOL_MAP[currentTool];
    if (!tool || tool.type !== 'chat') return;

    const input = document.getElementById('messageInput');
    const message = input.value.trim();
    if (!message) return;

    input.value = '';
    input.style.height = 'auto';
    setLoading(true);

    // Add user message to UI and state
    appendMessage('user', message);
    saveMessageToState(currentTool, 'user', message);

    // Add loading indicator
    const loadingId = addLoadingMessage();

    try {
        const convState = getConvState(currentTool);
        const body = { message, conversation_id: convState.conversationId };

        const res = await fetch(tool.endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(300000), // 5 min timeout for LLM calls
        });

        removeLoadingMessage(loadingId);

        if (!res.ok) {
            const errText = await res.text().catch(() => '');
            throw new Error(`Server error ${res.status}: ${errText.substring(0, 200)}`);
        }

        const data = await res.json();
        const reply = data.response || data.message || data.content || JSON.stringify(data);
        const newConvId = data.conversation_id || convState.conversationId;

        // Update conversation state
        const updatedState = {
            conversationId: newConvId,
            messages: [
                ...(convState.messages || []),
                { role: 'user', content: message },
                { role: 'assistant', content: reply },
            ],
        };
        setConvState(currentTool, updatedState);
        updateConvIdDisplay(newConvId);

        appendMessage('assistant', reply);

        // Start progress polling if response contains pipeline generation signal
        if (reply.includes('progress_id') || reply.includes('Generating') || reply.includes('generating')) {
            const progressMatch = reply.match(/progress_id[:\s"]+([a-f0-9-]{8,})/i);
            if (progressMatch) {
                startProgressPolling(progressMatch[1], tool);
            }
        }

    } catch (err) {
        removeLoadingMessage(loadingId);
        const errMsg = err.name === 'TimeoutError'
            ? 'Request timed out (5 minutes). The AI may still be processing — check back shortly.'
            : `Error: ${err.message}`;
        appendMessage('assistant', `❌ ${errMsg}`);
        showToast(errMsg, 'error');
    }

    setLoading(false);
    scrollToBottom();
}

// ============================================================
// PROGRESS POLLING (pipeline generation progress)
// ============================================================
let progressPollTimer = null;

function startProgressPolling(progressId, tool) {
    if (progressPollTimer) clearInterval(progressPollTimer);
    progressPollTimer = setInterval(async () => {
        try {
            const res = await fetch(`${tool.endpoint.replace('/chat', '')}/progress?progress_id=${progressId}`);
            if (res.ok) {
                const data = await res.json();
                if (data.status === 'complete' || data.status === 'error') {
                    clearInterval(progressPollTimer);
                    progressPollTimer = null;
                }
            }
        } catch { clearInterval(progressPollTimer); progressPollTimer = null; }
    }, 3000);
}

// ============================================================
// MESSAGE RENDERING
// ============================================================
function appendMessage(role, content, animate = true) {
    const container = document.getElementById('messagesContainer');
    const div = document.createElement('div');
    div.className = `message ${role}`;
    if (!animate) div.style.animation = 'none';

    const avatarEmoji = role === 'user' ? '👤' : (currentTool ? (TOOL_MAP[currentTool]?.icon || '🤖') : '🤖');
    const renderedContent = role === 'user'
        ? escapeHtml(content).replace(/\n/g, '<br>')
        : marked.parse(content);

    div.innerHTML = `
        <div class="msg-avatar">${avatarEmoji}</div>
        <div class="msg-bubble">${renderedContent}</div>
    `;
    container.appendChild(div);

    if (animate) scrollToBottom();
}

function addLoadingMessage() {
    const id = 'loading-' + Date.now();
    const container = document.getElementById('messagesContainer');
    const div = document.createElement('div');
    div.className = 'message assistant loading';
    div.id = id;
    div.innerHTML = `
        <div class="msg-avatar">🤖</div>
        <div class="msg-bubble">
            <div class="typing-dots">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        </div>
    `;
    container.appendChild(div);
    scrollToBottom();
    return id;
}

function removeLoadingMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    if (container) container.scrollTop = container.scrollHeight;
}

function saveMessageToState(toolId, role, content) {
    const state = getConvState(toolId);
    state.messages = state.messages || [];
    state.messages.push({ role, content });
    // Keep last 60 messages to avoid localStorage bloat
    if (state.messages.length > 60) state.messages = state.messages.slice(-60);
    setConvState(toolId, state);
}

// ============================================================
// NEW CHAT
// ============================================================
function newChat() {
    if (!currentTool) return;
    const tool = TOOL_MAP[currentTool];
    if (!tool || tool.type !== 'chat') return;

    // Clear stored conversation
    setConvState(currentTool, { conversationId: null, messages: [] });
    updateConvIdDisplay(null);

    // Re-render with welcome message
    const container = document.getElementById('messagesContainer');
    container.innerHTML = '';
    if (tool.welcome) appendMessage('assistant', tool.welcome, false);

    showToast('New conversation started', 'info');
    document.getElementById('messageInput').focus();
}

// ============================================================
// LOADING STATE
// ============================================================
function setLoading(loading) {
    isLoading = loading;
    const btn = document.getElementById('sendBtn');
    const input = document.getElementById('messageInput');
    btn.disabled = loading;
    input.disabled = loading;
    if (loading) {
        btn.classList.add('loading');
        btn.innerHTML = '<div class="typing-dots" style="padding:0;gap:3px;"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>';
    } else {
        btn.classList.remove('loading');
        btn.innerHTML = '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>';
        input.disabled = false;
        input.focus();
    }
}

// ============================================================
// COPY CODE
// ============================================================
function copyCode(btn) {
    const code = btn.dataset.code
        .replace(/&quot;/g, '"')
        .replace(/&#96;/g, '`');
    navigator.clipboard.writeText(code).then(() => {
        const orig = btn.textContent;
        btn.textContent = 'Copied!';
        btn.style.color = 'var(--green)';
        setTimeout(() => {
            btn.textContent = orig;
            btn.style.color = '';
        }, 2000);
    }).catch(() => showToast('Could not copy to clipboard', 'error'));
}

// ============================================================
// TOAST NOTIFICATIONS
// ============================================================
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icons = { success: '✅', error: '❌', info: 'ℹ️' };
    toast.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(20px)';
        toast.style.transition = '0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ============================================================
// UTILITIES
// ============================================================
function escapeHtml(text) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

// Auto health check every 60 seconds
setInterval(checkApiHealth, 60000);
