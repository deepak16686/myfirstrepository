/**
 * AI Platform - DevOps & Infrastructure Frontend Application
 */

// Configuration
const API_BASE_URL = window.location.origin;
let conversationId = null;
let isLoading = false;
let currentCategory = 'devops';
let currentTool = null;

// Pipeline progress polling state
let pollingInterval = null;
let progressMessageId = null;

// Terraform navigation state
let terraformNavLevel = 0;    // 0=providers, 1=resources, 2=subtypes
let terraformProvider = null;
let terraformResource = null;
let terraformSubType = null;
let terraformContext = null;   // Sent with every chat message

// Terraform provider/resource tree
const terraformTree = {
    providers: {
        vsphere: {
            name: 'On-Prem (vSphere)',
            icon: '🏢',
            desc: 'VMware vSphere infrastructure',
            color: '#6d8c3c'
        },
        azure: {
            name: 'Azure',
            icon: '☁️',
            desc: 'Microsoft Azure cloud',
            color: '#0078d4'
        },
        aws: {
            name: 'AWS',
            icon: '🔶',
            desc: 'Amazon Web Services',
            color: '#ff9900'
        },
        gcp: {
            name: 'GCP',
            icon: '🔵',
            desc: 'Google Cloud Platform',
            color: '#4285f4'
        }
    },
    resources: {
        vm: {
            name: 'Virtual Machines',
            icon: '🖥️',
            desc: 'Provision and manage virtual machines',
            sub_types: {
                linux: { name: 'Linux', icon: '🐧', desc: 'Linux-based VMs' },
                windows: { name: 'Windows', icon: '🪟', desc: 'Windows-based VMs' }
            }
        },
        kubernetes: {
            name: 'Kubernetes Clusters',
            icon: '☸️',
            desc: 'Deploy managed Kubernetes clusters'
        },
        containers: {
            name: 'Container Services',
            icon: '🐳',
            desc: 'Run containers on managed services'
        },
        networking: {
            name: 'Networking',
            icon: '🌐',
            desc: 'VPCs, subnets, firewalls, load balancers'
        }
    }
};

// Category configurations
const categoryConfig = {
    devops: {
        title: 'DevOps Tools',
        subtitle: 'AI-powered automation for your DevOps workflows'
    },
    iac: {
        title: 'Infrastructure as Code',
        subtitle: 'Generate and manage infrastructure configurations'
    },
    support: {
        title: 'Support Tools',
        subtitle: 'AI-assisted incident management and troubleshooting'
    },
    sre: {
        title: 'SRE Tools',
        subtitle: 'Site Reliability Engineering utilities and calculators'
    },
    auxiliary: {
        title: 'Auxiliary Tools',
        subtitle: 'Utilities for security, compliance, cost management and more'
    }
};

// Connectivity state: { toolName: Set of selected group names }
let selectedTools = {};

// Tool configurations
const toolConfig = {
    'pipeline-generator': {
        name: 'GitLab Pipeline Generator',
        icon: '🚀',
        endpoint: '/api/v1/chat/',
        welcomeMessage: `Hello! I'm your AI DevOps assistant. I can help you generate CI/CD pipelines for your GitLab repositories.

Just provide me with a GitLab repository URL and I'll analyze it and create appropriate Dockerfile and .gitlab-ci.yml files for you.

**Example:** "Generate a pipeline for http://gitlab-server/ai-pipeline-projects/java-springboot-api"`
    },
    'jenkins-generator': {
        name: 'Jenkins Pipeline Generator',
        icon: '🔧',
        endpoint: '/api/v1/jenkins-pipeline/chat',
        welcomeMessage: `Hello! I'm your AI DevOps assistant for Jenkins Declarative Pipelines.

I can generate **Jenkinsfile** and **Dockerfile** for any project with a full 9-stage pipeline:
Compile → Build Image → Test Image → Static Analysis → SonarQube → Trivy Scan → Push Release → Notify → Learn

Just provide a repository URL and I'll analyze it and create the pipeline files.

**Example:** "Generate a pipeline for http://localhost:3002/jenkins-projects/java-springboot-api"

**Commands:**
- Provide a **URL** to generate a pipeline
- Say **"commit"** to commit the generated files to the repository
- Say **"status"** to check Jenkins build status`
    },
    'github-actions': {
        name: 'GitHub Actions Generator',
        icon: '🐙',
        endpoint: '/api/v1/github-pipeline/chat',
        welcomeMessage: `Hello! I'm your AI DevOps assistant for GitHub Actions (via Gitea).

I can generate **GitHub Actions Workflow** and **Dockerfile** for any project with a full 9-job pipeline:
compile → build-image → test-image → static-analysis → sonarqube → trivy-scan → push-release → notify → learn-record

Just provide a repository URL and I'll analyze it and create the workflow files.

**Example:** "Generate a workflow for http://localhost:3002/github-projects/java-springboot-api"

**Commands:**
- Provide a **URL** to generate a workflow
- Say **"commit"** to commit the generated files to the repository
- Say **"status"** to check GitHub Actions workflow status`
    },
    'terraform-generator': {
        name: 'Terraform Generator',
        icon: '🌍',
        viewType: 'terraform-nav'
    },
    'connectivity-validator': {
        name: 'Tool Connectivity Validator',
        icon: '🔗',
        viewType: 'connectivity'
    },
    'commit-history': {
        name: 'Commit History',
        icon: '\u{1F4CB}',
        viewType: 'commit-history'
    },
    'chromadb-browser': {
        name: 'ChromaDB Browser',
        icon: '\u{1F5C3}',
        viewType: 'chromadb-browser'
    }
};

// DOM Elements
let messagesContainer;
let messageInput;
let sendButton;
let connectionStatus;
let conversationIdElement;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Get DOM elements
    messagesContainer = document.getElementById('messages');
    messageInput = document.getElementById('messageInput');
    sendButton = document.getElementById('sendButton');
    connectionStatus = document.getElementById('connectionStatus');
    conversationIdElement = document.getElementById('conversationId');

    // Configure marked for markdown parsing
    marked.setOptions({
        highlight: function(code, lang) {
            if (lang && hljs.getLanguage(lang)) {
                return hljs.highlight(code, { language: lang }).value;
            }
            return hljs.highlightAuto(code).value;
        },
        breaks: true,
        gfm: true
    });

    // Setup event listeners
    setupEventListeners();

    // Check API health
    checkApiHealth();

    // Initialize view
    showCategory('devops');
});

/**
 * Setup all event listeners
 */
function setupEventListeners() {
    // Navigation tabs
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const category = tab.dataset.category;
            showCategory(category);
        });
    });

    // Tool cards
    document.querySelectorAll('.tool-card').forEach(card => {
        card.addEventListener('click', () => {
            if (!card.classList.contains('disabled')) {
                const tool = card.dataset.tool;
                openTool(tool);
            }
        });
    });

    // Message input - Enter key
    if (messageInput) {
        messageInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    }
}

/**
 * Show a specific category
 */
/**
 * Hide all views, then show only the specified one.
 */
function switchView(viewId) {
    const views = ['dashboardView', 'toolView', 'connectivityView', 'terraformNavView', 'commitHistoryView', 'chromadbBrowserView'];
    views.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            if (id === viewId) {
                el.classList.remove('hidden');
            } else {
                el.classList.add('hidden');
            }
        }
    });
}

function showCategory(category) {
    currentCategory = category;

    // Update nav tabs
    document.querySelectorAll('.nav-tab').forEach(tab => {
        if (tab.dataset.category === category) {
            tab.classList.add('active');
        } else {
            tab.classList.remove('active');
        }
    });

    // Show/hide cards based on category
    const cards = document.querySelectorAll('.tool-card');
    cards.forEach(card => {
        const cardCategory = card.dataset.category;
        if (cardCategory === category) {
            card.classList.remove('hidden');
            card.style.display = 'flex';
        } else {
            card.classList.add('hidden');
            card.style.display = 'none';
        }
    });

    // Show ONLY the dashboard view
    switchView('dashboardView');

    currentTool = null;
    terraformContext = null;
}

/**
 * Open a specific tool
 */
function openTool(toolId) {
    currentTool = toolId;
    const config = toolConfig[toolId];

    if (!config) {
        console.error('Unknown tool:', toolId);
        return;
    }

    // Handle connectivity view type
    if (config.viewType === 'connectivity') {
        openConnectivityView();
        return;
    }

    // Handle commit history view type
    if (config.viewType === 'commit-history') {
        openCommitHistoryView();
        return;
    }

    // Handle chromadb browser view type
    if (config.viewType === 'chromadb-browser') {
        openChromaDBBrowser();
        return;
    }

    // Handle terraform navigation view type
    if (config.viewType === 'terraform-nav') {
        openTerraformNav();
        return;
    }

    // Update tool header
    document.getElementById('toolIcon').textContent = config.icon;
    document.getElementById('toolName').textContent = config.name;

    // Reset chat with welcome message
    resetChat(config.welcomeMessage);

    // Show ONLY the tool view
    switchView('toolView');

    // Focus on input
    if (messageInput) {
        messageInput.focus();
    }
}

/**
 * Go back to dashboard
 */
function goBack() {
    stopProgressPolling();
    // If in terraform chat, go back to terraform nav instead of dashboard
    if (currentTool && currentTool.startsWith('terraform-chat-')) {
        openTerraformNav();
        // Restore nav level to where they left off
        if (terraformResource) {
            terraformNavLevel = 1;
            renderTerraformCards();
        }
        return;
    }
    showCategory(currentCategory);
}

/**
 * Reset chat with a welcome message
 */
function resetChat(welcomeMessage) {
    stopProgressPolling();
    conversationId = null;
    if (conversationIdElement) {
        conversationIdElement.textContent = '';
    }

    if (messagesContainer) {
        messagesContainer.innerHTML = `
            <div class="message assistant">
                <div class="message-content">
                    ${marked.parse(welcomeMessage)}
                </div>
            </div>
        `;
    }
}

/**
 * Check API health and update status
 */
async function checkApiHealth() {
    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        if (response.ok) {
            setConnectionStatus('connected', 'Connected');
        } else {
            setConnectionStatus('disconnected', 'Disconnected');
        }
    } catch (error) {
        setConnectionStatus('disconnected', 'Disconnected');
        console.error('API health check failed:', error);
    }
}

/**
 * Update connection status indicator
 */
function setConnectionStatus(status, text) {
    if (connectionStatus) {
        connectionStatus.className = `status ${status}`;
        connectionStatus.textContent = text;
    }

    const sessionStatus = document.getElementById('sessionStatus');
    if (sessionStatus) {
        sessionStatus.className = `status ${status}`;
        sessionStatus.textContent = text;
    }
}

/**
 * Send a message to the chat API
 */
async function sendMessage() {
    if (!messageInput) return;

    const message = messageInput.value.trim();
    if (!message || isLoading) return;

    // Set loading state
    setLoading(true);

    // Add user message to UI
    addMessage('user', message);
    messageInput.value = '';

    // Add loading indicator
    const loadingId = addLoadingMessage();

    try {
        // Route to the correct endpoint based on current tool
        const config = currentTool ? toolConfig[currentTool] : null;
        const chatEndpoint = (config && config.endpoint) ? config.endpoint : '/api/v1/chat/';

        const response = await fetch(`${API_BASE_URL}${chatEndpoint}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: message,
                conversation_id: conversationId,
                ...(terraformContext ? { context: terraformContext } : {})
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        // Update conversation ID
        conversationId = data.conversation_id;
        if (conversationIdElement) {
            conversationIdElement.textContent = `Session: ${conversationId.substring(0, 8)}...`;
        }

        // Remove loading indicator and add response
        removeLoadingMessage(loadingId);
        addMessage('assistant', data.message);

        // If a pipeline was just committed, start polling for progress
        if (data.monitoring && data.monitoring.project_id != null && data.monitoring.branch) {
            startProgressPolling(data.monitoring.project_id, data.monitoring.branch);
        }

    } catch (error) {
        console.error('Error sending message:', error);
        removeLoadingMessage(loadingId);
        addMessage('assistant', `**Error:** ${error.message}\n\nPlease check if the backend is running and try again.`);
    } finally {
        setLoading(false);
    }
}

/**
 * Add a message to the chat UI
 */
function addMessage(role, content) {
    if (!messagesContainer) return;

    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    // Parse markdown and render
    contentDiv.innerHTML = marked.parse(content);

    // Apply syntax highlighting to code blocks
    contentDiv.querySelectorAll('pre code').forEach((block) => {
        hljs.highlightElement(block);
    });

    messageDiv.appendChild(contentDiv);
    messagesContainer.appendChild(messageDiv);

    // Scroll to bottom
    scrollToBottom();
}

/**
 * Add a loading message indicator
 */
function addLoadingMessage() {
    if (!messagesContainer) return null;

    const id = 'loading-' + Date.now();
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant loading';
    messageDiv.id = id;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';
    contentDiv.innerHTML = '<p>Thinking</p>';

    messageDiv.appendChild(contentDiv);
    messagesContainer.appendChild(messageDiv);
    scrollToBottom();

    return id;
}

/**
 * Remove a loading message
 */
function removeLoadingMessage(id) {
    if (!id) return;
    const element = document.getElementById(id);
    if (element) {
        element.remove();
    }
}

/**
 * Set loading state
 */
function setLoading(loading) {
    isLoading = loading;

    if (sendButton) {
        sendButton.disabled = loading;

        const buttonText = sendButton.querySelector('.button-text');
        const buttonLoading = sendButton.querySelector('.button-loading');

        if (loading) {
            if (buttonText) buttonText.style.display = 'none';
            if (buttonLoading) buttonLoading.style.display = 'inline-flex';
            setConnectionStatus('loading', 'Processing...');
        } else {
            if (buttonText) buttonText.style.display = 'inline';
            if (buttonLoading) buttonLoading.style.display = 'none';
            setConnectionStatus('connected', 'Connected');
        }
    }
}

/**
 * Scroll chat to bottom
 */
function scrollToBottom() {
    if (messagesContainer) {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
}

/**
 * Start a new conversation
 */
async function newConversation() {
    if (!currentTool) return;

    const config = toolConfig[currentTool];
    if (!config) return;

    try {
        const response = await fetch(`${API_BASE_URL}/api/v1/chat/new`, {
            method: 'POST'
        });

        if (response.ok) {
            const data = await response.json();
            conversationId = data.conversation_id;
            if (conversationIdElement) {
                conversationIdElement.textContent = `Session: ${conversationId.substring(0, 8)}...`;
            }

            // Reset chat with welcome message
            resetChat(config.welcomeMessage);
        }
    } catch (error) {
        console.error('Error creating new conversation:', error);
    }
}

// ============================================================================
// Pipeline Progress Polling
// ============================================================================

function startProgressPolling(projectId, branch) {
    stopProgressPolling();
    progressMessageId = addProgressMessage('Pipeline committed. Waiting for pipeline to start...');
    pollingInterval = setInterval(() => {
        fetchProgress(projectId, branch);
    }, 10000);
    // First fetch after a short delay (pipeline needs time to register)
    setTimeout(() => fetchProgress(projectId, branch), 5000);
}

function stopProgressPolling() {
    if (pollingInterval) {
        clearInterval(pollingInterval);
        pollingInterval = null;
    }
}

async function fetchProgress(projectId, branch) {
    try {
        // Route to correct progress endpoint based on active tool
        let progressBase = '/api/v1/pipeline/progress';
        if (currentTool === 'jenkins-generator') {
            progressBase = '/api/v1/jenkins-pipeline/progress';
        } else if (currentTool === 'github-actions') {
            progressBase = '/api/v1/github-pipeline/progress';
        } else if (currentTool && currentTool.startsWith('terraform-')) {
            progressBase = '/api/v1/terraform/progress';
        }
        const response = await fetch(
            `${API_BASE_URL}${progressBase}/${projectId}/${encodeURIComponent(branch)}`
        );
        if (!response.ok) return;
        const data = await response.json();
        if (!data.found) return;

        updateProgressMessage(progressMessageId, data);

        if (data.completed) {
            stopProgressPolling();
            progressMessageId = null;
        }
    } catch (error) {
        console.error('Error fetching pipeline progress:', error);
    }
}

function addProgressMessage(initialText) {
    if (!messagesContainer) return null;
    const id = 'progress-' + Date.now();
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    messageDiv.id = id;
    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content progress-tracker';
    contentDiv.innerHTML = buildProgressHTML({
        status: 'monitoring',
        current_message: initialText,
        attempt: 0, max_attempts: 3,
        events: [], completed: false
    });
    messageDiv.appendChild(contentDiv);
    messagesContainer.appendChild(messageDiv);
    scrollToBottom();
    return id;
}

function updateProgressMessage(id, data) {
    if (!id) return;
    const element = document.getElementById(id);
    if (!element) return;
    const contentDiv = element.querySelector('.message-content');
    if (contentDiv) {
        contentDiv.innerHTML = buildProgressHTML(data);
        scrollToBottom();
    }
}

// ============================================================================
// Terraform Multi-Level Navigation
// ============================================================================

function openTerraformNav() {
    terraformNavLevel = 0;
    terraformProvider = null;
    terraformResource = null;
    terraformSubType = null;
    terraformContext = null;

    // Show ONLY the terraform nav view
    switchView('terraformNavView');

    currentTool = 'terraform-generator';
    renderTerraformCards();
}

function renderTerraformCards() {
    const container = document.getElementById('terraformCardsContainer');
    const title = document.getElementById('terraformNavTitle');
    container.innerHTML = '';

    updateTerraformBreadcrumb();

    if (terraformNavLevel === 0) {
        // Show provider cards
        title.textContent = 'Select Cloud Provider';
        for (const [key, prov] of Object.entries(terraformTree.providers)) {
            const card = document.createElement('div');
            card.className = `tf-nav-card provider-${key}`;
            card.innerHTML = `
                <div class="tf-nav-card-icon">${prov.icon}</div>
                <div class="tf-nav-card-name">${prov.name}</div>
                <div class="tf-nav-card-desc">${prov.desc}</div>
            `;
            card.addEventListener('click', () => selectTerraformProvider(key));
            container.appendChild(card);
        }
    } else if (terraformNavLevel === 1) {
        // Show resource type cards
        const prov = terraformTree.providers[terraformProvider];
        title.textContent = `${prov.name} - Select Resource Type`;
        for (const [key, res] of Object.entries(terraformTree.resources)) {
            const card = document.createElement('div');
            card.className = 'tf-nav-card resource-card';
            card.innerHTML = `
                <div class="tf-nav-card-icon">${res.icon}</div>
                <div class="tf-nav-card-name">${res.name}</div>
                <div class="tf-nav-card-desc">${res.desc}</div>
            `;
            card.addEventListener('click', () => selectTerraformResource(key));
            container.appendChild(card);
        }
    } else if (terraformNavLevel === 2) {
        // Show sub-type cards (only for VMs)
        const prov = terraformTree.providers[terraformProvider];
        const res = terraformTree.resources[terraformResource];
        title.textContent = `${prov.name} - ${res.name} - Select Type`;
        for (const [key, sub] of Object.entries(res.sub_types)) {
            const card = document.createElement('div');
            card.className = 'tf-nav-card subtype-card';
            card.innerHTML = `
                <div class="tf-nav-card-icon">${sub.icon}</div>
                <div class="tf-nav-card-name">${sub.name}</div>
                <div class="tf-nav-card-desc">${sub.desc}</div>
            `;
            card.addEventListener('click', () => selectTerraformSubType(key));
            container.appendChild(card);
        }
    }
}

function selectTerraformProvider(provider) {
    terraformProvider = provider;
    terraformNavLevel = 1;
    renderTerraformCards();
}

function selectTerraformResource(resource) {
    terraformResource = resource;
    const res = terraformTree.resources[resource];

    // If resource has sub-types, show them; otherwise open chat
    if (res.sub_types) {
        terraformNavLevel = 2;
        renderTerraformCards();
    } else {
        openTerraformChat(null);
    }
}

function selectTerraformSubType(subType) {
    terraformSubType = subType;
    openTerraformChat(subType);
}

function openTerraformChat(subType) {
    const prov = terraformTree.providers[terraformProvider];
    const res = terraformTree.resources[terraformResource];
    const subInfo = subType ? res.sub_types[subType] : null;

    // Build context for backend
    terraformContext = {
        provider: terraformProvider,
        resource_type: terraformResource,
        sub_type: subType
    };

    // Build a dynamic tool ID for this combo
    const toolId = `terraform-chat-${terraformProvider}-${terraformResource}`;
    currentTool = toolId;

    // Build welcome message
    let contextLabel = `${prov.name} > ${res.name}`;
    if (subInfo) contextLabel += ` > ${subInfo.name}`;

    const welcomeMsg = `Hello! I'm your AI Terraform assistant for **${contextLabel}**.

I can generate production-ready Terraform configurations including \`provider.tf\`, \`main.tf\`, \`variables.tf\`, \`outputs.tf\`, and \`terraform.tfvars.example\`.

**Just describe what you need** and I'll generate the Terraform files, validate them, and optionally run \`terraform plan\`.

**Commands:**
- Describe your infrastructure requirements to **generate** Terraform configs
- Say **"plan"** to run \`terraform plan\` on the generated files
- Say **"apply"** to apply the configuration (requires cloud credentials)
- Say **"commit"** to commit the files to a Git repository
- Say **"destroy"** to tear down provisioned resources`;

    // Register dynamic tool config for this chat session
    toolConfig[toolId] = {
        name: `Terraform - ${contextLabel}`,
        icon: '🌍',
        endpoint: '/api/v1/terraform/chat',
        welcomeMessage: welcomeMsg
    };

    // Update tool header
    document.getElementById('toolIcon').textContent = '🌍';
    document.getElementById('toolName').textContent = `Terraform - ${contextLabel}`;

    // Reset chat with welcome message
    resetChat(welcomeMsg);

    // Show ONLY the tool view
    switchView('toolView');

    if (messageInput) messageInput.focus();
}

function terraformGoBack() {
    if (terraformNavLevel > 0) {
        terraformNavLevel--;
        if (terraformNavLevel === 0) {
            terraformProvider = null;
            terraformResource = null;
            terraformSubType = null;
        } else if (terraformNavLevel === 1) {
            terraformResource = null;
            terraformSubType = null;
        }
        renderTerraformCards();
    } else {
        // Back to dashboard
        showCategory(currentCategory);
    }
}

function updateTerraformBreadcrumb() {
    const bc = document.getElementById('terraformBreadcrumb');
    let parts = [];

    parts.push('<span class="bc-item" onclick="openTerraformNav()">Terraform</span>');

    if (terraformProvider) {
        const prov = terraformTree.providers[terraformProvider];
        if (terraformNavLevel > 1) {
            parts.push(`<span class="bc-separator">›</span>`);
            parts.push(`<span class="bc-item" onclick="terraformNavLevel=1;terraformResource=null;renderTerraformCards()">${prov.name}</span>`);
        } else {
            parts.push(`<span class="bc-separator">›</span>`);
            parts.push(`<span class="bc-current">${prov.name}</span>`);
        }
    }

    if (terraformResource && terraformNavLevel >= 2) {
        const res = terraformTree.resources[terraformResource];
        parts.push(`<span class="bc-separator">›</span>`);
        parts.push(`<span class="bc-current">${res.name}</span>`);
    }

    bc.innerHTML = parts.join('');
}

// ============================================================================
// Connectivity Validator
// ============================================================================

function openConnectivityView() {
    // Show ONLY the connectivity view
    switchView('connectivityView');
    selectedTools = {};
    testAllConnectivity();
}

async function testAllConnectivity() {
    const grid = document.getElementById('connectivityGrid');
    grid.innerHTML = '<div class="connectivity-loading"><span class="spinner"></span> Testing connectivity to all tools...</div>';

    // Hide access request panel during testing
    document.getElementById('accessRequestPanel').classList.add('hidden');
    selectedTools = {};

    try {
        const response = await fetch(`${API_BASE_URL}/api/v1/connectivity/`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        // Update summary
        document.getElementById('totalCount').textContent = data.total;
        document.getElementById('healthyCount').textContent = data.healthy;
        document.getElementById('unhealthyCount').textContent = data.unhealthy;
        document.getElementById('unknownCount').textContent = data.unknown;

        renderConnectivityGrid(data.tools);

        // Show access request panel if there are unhealthy tools
        if (data.unhealthy > 0 || data.unknown > 0) {
            document.getElementById('accessRequestPanel').classList.remove('hidden');
        }
    } catch (error) {
        grid.innerHTML = `<div class="connectivity-error">Failed to check connectivity: ${error.message}</div>`;
    }
}

function renderConnectivityGrid(tools) {
    const grid = document.getElementById('connectivityGrid');
    grid.innerHTML = '';

    const iconMap = {
        'gitlab': '<svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor"><path d="M22.65 14.39L12 22.13 1.35 14.39a.84.84 0 0 1-.3-.94l1.22-3.78 2.44-7.51A.42.42 0 0 1 4.82 2a.43.43 0 0 1 .58 0 .42.42 0 0 1 .11.18l2.44 7.49h8.1l2.44-7.51A.42.42 0 0 1 18.6 2a.43.43 0 0 1 .58 0 .42.42 0 0 1 .11.18l2.44 7.51L23 13.45a.84.84 0 0 1-.35.94z"/></svg>',
        'shield-check': '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/></svg>',
        'shield-alert': '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
        'package': '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2"><line x1="16.5" y1="9.4" x2="7.5" y2="4.21"/><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>',
        'database': '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>',
        'brain': '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2"><path d="M9.5 2A5.5 5.5 0 0 0 5 5.5v.01A5.5 5.5 0 0 0 5 16.5v.01A4 4 0 0 0 9 20.5h.5"/><path d="M14.5 2A5.5 5.5 0 0 1 19 5.5v.01A5.5 5.5 0 0 1 19 16.5v.01A4 4 0 0 1 15 20.5h-.5"/><path d="M12 2v20"/></svg>',
        'github': '<svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/></svg>',
        'ticket': '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"/><path d="M13 5v2"/><path d="M13 17v2"/><path d="M13 11v2"/></svg>',
        'activity': '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
        'settings': '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
        'tool': '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>'
    };

    for (const tool of tools) {
        const card = document.createElement('div');
        card.className = `connectivity-card status-${tool.status}`;
        const isUnhealthy = tool.status !== 'healthy';
        const groups = tool.access_groups || [];

        const svgIcon = iconMap[tool.icon] || iconMap['tool'];

        // Build access groups HTML
        let groupsHtml = '';
        if (groups.length > 0) {
            groupsHtml = `
                <div class="conn-access-groups">
                    <span class="conn-label">Groups:</span>
                    <div class="conn-groups-list">
                        ${groups.map(g => `<span class="conn-group-tag" title="${g.description}">${g.name}</span>`).join('')}
                    </div>
                </div>`;
        }

        // Build group checkboxes for unhealthy tools
        let groupCheckboxes = '';
        if (isUnhealthy && groups.length > 0) {
            groupCheckboxes = `
                <div class="conn-group-select">
                    <span class="conn-group-select-label">Select groups to request:</span>
                    ${groups.map(g => `
                        <label class="conn-group-checkbox" title="${g.description}">
                            <input type="checkbox" onchange="toggleGroupSelection('${tool.name}', '${g.name}')">
                            <span>${g.name}</span>
                        </label>
                    `).join('')}
                </div>`;
        }

        card.innerHTML = `
            <div class="conn-card-header">
                <div class="conn-card-icon">${svgIcon}</div>
                <span class="conn-status-badge status-${tool.status}">${tool.status.toUpperCase()}</span>
            </div>
            <h4 class="conn-card-title">${tool.display_name}</h4>
            <div class="conn-card-details">
                <div class="conn-detail"><span class="conn-label">URL:</span> <span class="conn-value">${tool.base_url}</span></div>
                ${tool.version ? `<div class="conn-detail"><span class="conn-label">Version:</span> <span class="conn-value">${tool.version}</span></div>` : ''}
                ${tool.latency_ms !== null ? `<div class="conn-detail"><span class="conn-label">Latency:</span> <span class="conn-value">${tool.latency_ms}ms</span></div>` : ''}
                <div class="conn-detail"><span class="conn-label">Auth:</span> <span class="conn-value">${tool.auth_type || 'None'}</span></div>
                ${tool.error ? `<div class="conn-detail conn-error"><span class="conn-label">Error:</span> <span class="conn-value">${tool.error}</span></div>` : ''}
                ${groupsHtml}
            </div>
            ${groupCheckboxes}
            <div class="conn-card-actions">
                <button class="conn-retest-btn" onclick="retestTool('${tool.name}', this)">Retest</button>
                ${isUnhealthy ? `<label class="conn-select-label"><input type="checkbox" onchange="toggleToolSelection('${tool.name}')"> Request Access</label>` : ''}
            </div>
        `;
        grid.appendChild(card);
    }
}

async function retestTool(toolName, btn) {
    btn.disabled = true;
    btn.textContent = 'Testing...';
    try {
        const response = await fetch(`${API_BASE_URL}/api/v1/connectivity/${toolName}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const tool = await response.json();

        // Refresh entire grid to update counts
        await testAllConnectivity();
    } catch (error) {
        btn.textContent = 'Failed';
        setTimeout(() => { btn.textContent = 'Retest'; btn.disabled = false; }, 2000);
    }
}

function toggleToolSelection(toolName) {
    if (selectedTools[toolName]) {
        delete selectedTools[toolName];
    } else {
        selectedTools[toolName] = new Set();
    }
    updateAccessRequestPanel();
}

function toggleGroupSelection(toolName, groupName) {
    // Ensure the tool is in selectedTools
    if (!selectedTools[toolName]) {
        selectedTools[toolName] = new Set();
    }
    if (selectedTools[toolName].has(groupName)) {
        selectedTools[toolName].delete(groupName);
    } else {
        selectedTools[toolName].add(groupName);
    }
    updateAccessRequestPanel();
}

function updateAccessRequestPanel() {
    const list = document.getElementById('selectedToolsList');
    const toolNames = Object.keys(selectedTools);
    if (toolNames.length === 0) {
        list.innerHTML = '<p class="no-tools-selected">No tools selected</p>';
    } else {
        list.innerHTML = toolNames.map(t => {
            const groups = selectedTools[t];
            const groupStr = groups && groups.size > 0
                ? ` (${Array.from(groups).join(', ')})`
                : '';
            return `<span class="selected-tool-tag">${t}${groupStr}</span>`;
        }).join(' ');
    }
}

async function submitAccessRequest() {
    const toolNames = Object.keys(selectedTools);
    if (toolNames.length === 0) {
        alert('Please select at least one tool to request access for.');
        return;
    }

    const name = document.getElementById('requesterName').value.trim();
    const email = document.getElementById('requesterEmail').value.trim();
    const reason = document.getElementById('accessReason').value.trim();

    if (!name || !email || !reason) {
        alert('Please fill in all fields.');
        return;
    }

    // Build tools array with selected groups
    const toolsPayload = toolNames.map(t => ({
        tool: t,
        groups: Array.from(selectedTools[t] || [])
    }));

    try {
        const response = await fetch(`${API_BASE_URL}/api/v1/connectivity/access-request`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tools: toolsPayload,
                reason: reason,
                requester_name: name,
                requester_email: email
            })
        });

        const result = await response.json();
        if (result.success) {
            alert(`Access request created successfully!\n\nJira Issue: ${result.jira_issue_key}\n${result.jira_issue_url || ''}`);
            selectedTools = {};
            updateAccessRequestPanel();
            // Uncheck all checkboxes
            document.querySelectorAll('.conn-select-label input, .conn-group-checkbox input').forEach(cb => cb.checked = false);
        } else {
            alert(`Failed to create access request: ${result.message}`);
        }
    } catch (error) {
        alert(`Error submitting request: ${error.message}`);
    }
}

function linkify(text) {
    // Convert markdown links [text](url) to HTML <a> tags
    return text
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color:#3b82f6;">$1</a>')
        .replace(/\n/g, '<br>');
}

function buildProgressHTML(data) {
    const icons = {
        'monitoring': '&#9203;',
        'pipeline_running': '&#9654;&#65039;',
        'build_running': '&#9654;&#65039;',
        'pipeline_failed': '&#10060;',
        'build_failed': '&#10060;',
        'fixing': '&#128295;',
        'fix_committed': '&#128296;',
        'success': '&#9989;',
        'failed': '&#10060;'
    };
    const colors = {
        'monitoring': '#f59e0b',
        'pipeline_running': '#3b82f6',
        'build_running': '#3b82f6',
        'pipeline_failed': '#ef4444',
        'build_failed': '#ef4444',
        'fixing': '#f97316',
        'fix_committed': '#8b5cf6',
        'success': '#22c55e',
        'failed': '#ef4444'
    };

    const icon = icons[data.status] || '&#8987;';
    const color = colors[data.status] || '#666';

    let html = `<div style="border-left: 3px solid ${color}; padding: 8px 12px;">`;
    html += `<p style="margin:0 0 6px 0;"><strong style="color:${color};">${icon} Pipeline Monitor</strong>`;
    if (data.pipeline_id) html += ` <span style="color:#888;font-size:0.85em;">#${data.pipeline_id}</span>`;
    html += `</p>`;
    html += `<p style="margin:0 0 4px 0;">${linkify(data.current_message)}</p>`;

    if (data.attempt > 0 && !data.completed) {
        const pct = Math.round((data.attempt / data.max_attempts) * 100);
        html += `<div style="background:#e5e7eb;border-radius:4px;height:6px;margin:8px 0;">`;
        html += `<div style="background:${color};border-radius:4px;height:6px;width:${pct}%;transition:width 0.3s;"></div></div>`;
        html += `<p style="font-size:0.85em;color:#666;margin:0;">Self-healing: attempt ${data.attempt}/${data.max_attempts}</p>`;
    }

    if (data.events && data.events.length > 0) {
        html += '<details style="margin-top:8px;"><summary style="cursor:pointer;font-size:0.85em;color:#888;">Event log (' + data.events.length + ')</summary>';
        html += '<div style="font-size:0.8em;color:#666;margin-top:4px;max-height:200px;overflow-y:auto;">';
        for (const e of data.events) {
            const eIcon = icons[e.stage] || '';
            html += `<div style="padding:2px 0;"><code style="color:#999;">${e.timestamp}</code> ${eIcon} ${linkify(e.message)}</div>`;
        }
        html += '</div></details>';
    }

    if (!data.completed) {
        html += '<p style="font-size:0.8em;color:#999;margin:6px 0 0 0;">Auto-updating every 10s...</p>';
    }

    html += '</div>';
    return html;
}

// ============================================================================
// Commit History Viewer
// ============================================================================

function openCommitHistoryView() {
    switchView('commitHistoryView');

    // Default date range: last 7 days
    const now = new Date();
    const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

    const formatLocal = (d) => {
        const pad = (n) => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    };

    document.getElementById('commitSince').value = formatLocal(weekAgo);
    document.getElementById('commitUntil').value = formatLocal(now);
    document.getElementById('commitBranch').innerHTML = '<option value="">All branches</option>';
    _lastBranchFetchUrl = '';
    document.getElementById('commitResults').innerHTML = '<p style="color:#888;text-align:center;padding:40px 0;">Enter a repository URL and date range, then click <strong>Fetch Commits</strong>.</p>';
    document.getElementById('commitSummary').style.display = 'none';
}

// Store repo URL for detail fetches
let _commitRepoUrl = '';
let _commitToken = '';
let _lastBranchFetchUrl = '';

async function fetchBranches() {
    const repoUrl = document.getElementById('commitRepoUrl').value.trim();
    if (!repoUrl || repoUrl === _lastBranchFetchUrl) return;
    _lastBranchFetchUrl = repoUrl;

    const select = document.getElementById('commitBranch');
    select.innerHTML = '<option value="">Loading...</option>';
    select.disabled = true;

    try {
        const body = { repo_url: repoUrl };
        const token = document.getElementById('commitToken').value.trim();
        if (token) body.token = token;

        const resp = await fetch(`${API_BASE_URL}/api/v1/commit-history/branches`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (!resp.ok) {
            select.innerHTML = '<option value="">All branches</option>';
            select.disabled = false;
            return;
        }

        const data = await resp.json();
        select.innerHTML = '<option value="">All branches</option>';

        if (data.branches && data.branches.length > 0) {
            // Sort: default branch first, then alphabetical
            data.branches.sort((a, b) => {
                if (a.default && !b.default) return -1;
                if (!a.default && b.default) return 1;
                return a.name.localeCompare(b.name);
            });
            for (const br of data.branches) {
                const opt = document.createElement('option');
                opt.value = br.name;
                opt.textContent = br.name + (br.default ? ' (default)' : '');
                select.appendChild(opt);
            }
        }
    } catch (err) {
        select.innerHTML = '<option value="">All branches</option>';
    } finally {
        select.disabled = false;
    }
}

async function fetchCommitHistory() {
    const repoUrl = document.getElementById('commitRepoUrl').value.trim();
    const since = document.getElementById('commitSince').value;
    const until = document.getElementById('commitUntil').value;
    const token = document.getElementById('commitToken').value.trim();

    if (!repoUrl) { alert('Please enter a repository URL.'); return; }
    if (!since || !until) { alert('Please select both start and end dates.'); return; }

    _commitRepoUrl = repoUrl;
    _commitToken = token;

    const btn = document.getElementById('commitFetchBtn');
    const results = document.getElementById('commitResults');
    btn.disabled = true;
    btn.textContent = 'Fetching...';
    results.innerHTML = '<div style="text-align:center;padding:40px;"><span class="spinner"></span> Fetching commits...</div>';

    try {
        const branch = document.getElementById('commitBranch').value;
        const body = {
            repo_url: repoUrl,
            since: since + ':00',
            until: until + ':00',
            page: 1,
            per_page: 100
        };
        if (token) body.token = token;
        if (branch) body.branch = branch;

        const resp = await fetch(`${API_BASE_URL}/api/v1/commit-history/commits`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        const data = await resp.json();

        // Update summary
        const summary = document.getElementById('commitSummary');
        summary.style.display = 'flex';
        document.getElementById('commitTotalCount').textContent = data.total || data.commits.length;
        document.getElementById('commitServerType').textContent = (data.server_type || '-').toUpperCase();

        let totalAdds = 0, totalDels = 0;
        for (const c of data.commits) {
            totalAdds += c.additions || 0;
            totalDels += c.deletions || 0;
        }
        document.getElementById('commitAdditions').textContent = '+' + totalAdds;
        document.getElementById('commitDeletions').textContent = '-' + totalDels;

        renderCommitTable(data.commits, data.repo);

    } catch (err) {
        results.innerHTML = `<div style="color:#ef4444;padding:20px;text-align:center;"><strong>Error:</strong> ${err.message}</div>`;
        document.getElementById('commitSummary').style.display = 'none';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Fetch Commits';
    }
}

function renderCommitTable(commits, repoLabel) {
    const results = document.getElementById('commitResults');

    if (!commits || commits.length === 0) {
        results.innerHTML = '<p style="color:#888;text-align:center;padding:40px;">No commits found in the selected date range.</p>';
        return;
    }

    let html = `<table style="width:100%;border-collapse:collapse;font-size:0.88em;margin-top:12px;">
        <thead>
            <tr style="background:#f1f5f9;text-align:left;">
                <th style="padding:10px 12px;border-bottom:2px solid #e2e8f0;width:100px;">Commit</th>
                <th style="padding:10px 12px;border-bottom:2px solid #e2e8f0;">Message</th>
                <th style="padding:10px 12px;border-bottom:2px solid #e2e8f0;width:130px;">Author</th>
                <th style="padding:10px 12px;border-bottom:2px solid #e2e8f0;width:160px;">Date</th>
                <th style="padding:10px 12px;border-bottom:2px solid #e2e8f0;width:80px;text-align:center;">Changes</th>
                <th style="padding:10px 12px;border-bottom:2px solid #e2e8f0;width:60px;text-align:center;">Files</th>
            </tr>
        </thead>
        <tbody>`;

    for (const c of commits) {
        const dateStr = formatCommitDate(c.date);
        const shortSha = c.short_sha || c.sha.substring(0, 7);

        html += `<tr style="border-bottom:1px solid #f1f5f9;cursor:pointer;" onclick="toggleCommitDetail(this, '${c.sha}')" title="Click to view changed files">
            <td style="padding:8px 12px;font-family:monospace;">
                <a href="${c.url}" target="_blank" onclick="event.stopPropagation();" style="color:#3b82f6;text-decoration:none;font-weight:600;">${shortSha}</a>
            </td>
            <td style="padding:8px 12px;max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(c.message)}">${escapeHtml(c.message)}</td>
            <td style="padding:8px 12px;color:#666;">${escapeHtml(c.author)}</td>
            <td style="padding:8px 12px;color:#888;font-size:0.9em;">${dateStr}</td>
            <td style="padding:8px 12px;text-align:center;">
                <span style="color:#22c55e;font-size:0.85em;">+${c.additions || 0}</span>
                <span style="color:#ef4444;font-size:0.85em;margin-left:4px;">-${c.deletions || 0}</span>
            </td>
            <td style="padding:8px 12px;text-align:center;color:#666;">${c.files_changed || '-'}</td>
        </tr>
        <tr class="commit-detail-row" style="display:none;">
            <td colspan="6" style="padding:0;background:#f8fafc;">
                <div class="commit-detail-content" style="padding:12px 20px;">
                    <span class="spinner" style="display:inline-block;"></span> Loading files...
                </div>
            </td>
        </tr>`;
    }

    html += '</tbody></table>';
    results.innerHTML = html;
}

async function toggleCommitDetail(row, sha) {
    const detailRow = row.nextElementSibling;
    if (!detailRow || !detailRow.classList.contains('commit-detail-row')) return;

    // Toggle visibility
    if (detailRow.style.display !== 'none') {
        detailRow.style.display = 'none';
        return;
    }

    detailRow.style.display = 'table-row';
    const content = detailRow.querySelector('.commit-detail-content');

    // Check if already loaded
    if (content.dataset.loaded === 'true') return;

    try {
        const body = { repo_url: _commitRepoUrl };
        if (_commitToken) body.token = _commitToken;

        const resp = await fetch(`${API_BASE_URL}/api/v1/commit-history/commits/${sha}/detail`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }

        const data = await resp.json();
        content.dataset.loaded = 'true';

        if (!data.files || data.files.length === 0) {
            content.innerHTML = '<p style="color:#888;margin:0;">No file changes found.</p>';
            return;
        }

        let filesHtml = `<div style="font-size:0.85em;">
            <div style="margin-bottom:8px;color:#666;">
                <strong>${data.files.length} file(s) changed</strong>
                &mdash; <span style="color:#22c55e;">+${data.stats?.additions || 0}</span>
                <span style="color:#ef4444;margin-left:4px;">-${data.stats?.deletions || 0}</span>
            </div>`;

        for (const f of data.files) {
            const statusColors = {
                added: '#22c55e', modified: '#f59e0b', removed: '#ef4444', renamed: '#8b5cf6'
            };
            const statusColor = statusColors[f.status] || '#666';
            const statusIcon = { added: '+', modified: '~', removed: '-', renamed: '>' }[f.status] || '?';

            filesHtml += `<div style="display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid #f1f5f9;">
                <span style="color:${statusColor};font-weight:700;font-family:monospace;width:16px;text-align:center;">${statusIcon}</span>
                <span style="font-family:monospace;flex:1;">${escapeHtml(f.filename)}</span>
                <span style="color:#22c55e;font-size:0.9em;">+${f.additions}</span>
                <span style="color:#ef4444;font-size:0.9em;">-${f.deletions}</span>
            </div>`;
        }

        filesHtml += '</div>';
        content.innerHTML = filesHtml;

    } catch (err) {
        content.innerHTML = `<p style="color:#ef4444;margin:0;">Failed to load details: ${err.message}</p>`;
    }
}

function formatCommitDate(dateStr) {
    if (!dateStr) return '-';
    try {
        const d = new Date(dateStr);
        const pad = (n) => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    } catch { return dateStr; }
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ============================================================================
// ChromaDB Browser
// ============================================================================

function openChromaDBBrowser() {
    switchView('chromadbBrowserView');
    refreshChromaDBSummary();
}

async function refreshChromaDBSummary() {
    const grid = document.getElementById('chromadbCollectionsGrid');
    grid.innerHTML = '<div class="connectivity-loading"><span class="spinner"></span> Loading ChromaDB collections...</div>';

    try {
        const response = await fetch(`${API_BASE_URL}/api/v1/chromadb-browser/summary`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        document.getElementById('chromadbCollectionCount').textContent = data.total_collections;
        document.getElementById('chromadbDocumentCount').textContent = data.total_documents;

        renderChromaDBCollections(data.collections);
    } catch (error) {
        grid.innerHTML = `<div class="connectivity-error">Failed to load ChromaDB collections: ${error.message}</div>`;
    }
}

function renderChromaDBCollections(collections) {
    const grid = document.getElementById('chromadbCollectionsGrid');
    grid.innerHTML = '';

    if (!collections || collections.length === 0) {
        grid.innerHTML = '<div class="connectivity-loading">No collections found.</div>';
        return;
    }

    for (const coll of collections) {
        const card = document.createElement('div');
        card.className = 'connectivity-card status-healthy';

        let sampleHtml = '';
        if (coll.sample_ids && coll.sample_ids.length > 0) {
            sampleHtml = '<div style="margin-top:12px;"><strong style="font-size:0.85em;color:#666;">Sample Documents (first 10):</strong>';
            sampleHtml += '<div style="max-height:220px;overflow-y:auto;margin-top:6px;">';
            for (let i = 0; i < coll.sample_ids.length; i++) {
                const id = coll.sample_ids[i];
                const meta = coll.sample_metadata && coll.sample_metadata[i] ? coll.sample_metadata[i] : {};
                const lang = meta.language || meta.type || '';
                const fw = meta.framework || '';
                const metaBadges = (lang ? `<span style="background:#e0e7ff;color:#3730a3;padding:1px 6px;border-radius:3px;font-size:0.78em;margin-left:6px;">${escapeHtml(lang)}</span>` : '')
                    + (fw ? `<span style="background:#fef3c7;color:#92400e;padding:1px 6px;border-radius:3px;font-size:0.78em;margin-left:4px;">${escapeHtml(fw)}</span>` : '');
                sampleHtml += `<div style="padding:4px 8px;border-bottom:1px solid #f1f5f9;font-family:monospace;font-size:0.82em;display:flex;align-items:center;gap:4px;">
                    <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(id)}">${escapeHtml(id)}</span>${metaBadges}
                </div>`;
            }
            sampleHtml += '</div></div>';
        }

        const loadBtn = coll.count > 0
            ? `<button class="conn-retest-btn" onclick="event.stopPropagation();loadChromaDBCollection('${escapeHtml(coll.name)}')">View All Documents</button>`
            : '';

        card.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <h4 style="margin:0;font-size:1.05em;">${escapeHtml(coll.name)}</h4>
                <span style="background:${coll.count > 0 ? '#22c55e' : '#94a3b8'};color:#fff;padding:4px 12px;border-radius:20px;font-size:0.85em;font-weight:600;">${coll.count} docs</span>
            </div>
            <div style="margin-top:6px;font-size:0.78em;color:#999;font-family:monospace;">${escapeHtml(coll.id)}</div>
            ${sampleHtml}
            <div style="margin-top:10px;">${loadBtn}</div>
        `;
        grid.appendChild(card);
    }
}

async function loadChromaDBCollection(collectionName) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/v1/chromadb-browser/collection`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ collection_name: collectionName, limit: 200, offset: 0 })
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        let html = `<div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:200;display:flex;align-items:center;justify-content:center;" onclick="if(event.target===this)this.remove()">`;
        html += `<div style="background:#fff;border-radius:12px;padding:24px;max-width:900px;width:90%;max-height:80vh;overflow-y:auto;">`;
        html += `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">`;
        html += `<h3 style="margin:0;">${escapeHtml(collectionName)} <span style="color:#888;font-weight:400;">(${data.total} documents)</span></h3>`;
        html += `<button onclick="this.closest('div[style*=fixed]').remove()" style="background:none;border:none;font-size:1.5em;cursor:pointer;">&times;</button>`;
        html += `</div>`;

        if (data.ids && data.ids.length > 0) {
            html += '<table style="width:100%;border-collapse:collapse;font-size:0.85em;">';
            html += '<thead><tr style="background:#f1f5f9;"><th style="padding:8px;text-align:left;">Document ID</th><th style="padding:8px;text-align:left;">Metadata</th><th style="padding:8px;width:60px;">Actions</th></tr></thead><tbody>';
            for (let i = 0; i < data.ids.length; i++) {
                const id = data.ids[i];
                const meta = data.metadatas && data.metadatas[i] ? JSON.stringify(data.metadatas[i]) : '{}';
                html += `<tr style="border-bottom:1px solid #f1f5f9;">`;
                html += `<td style="padding:6px 8px;font-family:monospace;font-size:0.9em;max-width:350px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(id)}">${escapeHtml(id)}</td>`;
                html += `<td style="padding:6px 8px;font-size:0.85em;color:#666;max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(meta)}">${escapeHtml(meta.substring(0, 150))}</td>`;
                html += `<td style="padding:6px 8px;text-align:center;"><button onclick="deleteChromaDBDoc('${escapeHtml(collectionName)}','${escapeHtml(id)}',this)" style="background:#ef4444;color:#fff;border:none;padding:2px 8px;border-radius:4px;cursor:pointer;font-size:0.8em;">Del</button></td>`;
                html += `</tr>`;
            }
            html += '</tbody></table>';
        } else {
            html += '<p style="color:#888;">No documents found.</p>';
        }

        html += '</div></div>';
        document.body.insertAdjacentHTML('beforeend', html);

    } catch (error) {
        alert('Failed to load documents: ' + error.message);
    }
}

async function deleteChromaDBDoc(collectionName, docId, btn) {
    if (!confirm(`Delete document "${docId}" from "${collectionName}"?`)) return;
    btn.disabled = true;
    btn.textContent = '...';
    try {
        const response = await fetch(`${API_BASE_URL}/api/v1/chromadb-browser/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ collection_name: collectionName, document_id: docId })
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const result = await response.json();
        if (result.success) {
            const row = btn.closest('tr');
            if (row) row.remove();
        } else {
            alert('Delete failed: ' + (result.message || 'Unknown error'));
            btn.disabled = false;
            btn.textContent = 'Del';
        }
    } catch (error) {
        alert('Delete error: ' + error.message);
        btn.disabled = false;
        btn.textContent = 'Del';
    }
}

// ========== LLM Settings ==========

async function loadLLMProviders() {
    try {
        const resp = await fetch(`${API_BASE_URL}/api/v1/llm/providers`);
        if (!resp.ok) throw new Error('Failed to load providers');
        const data = await resp.json();
        renderLLMProviders(data);
        // Update nav badge
        const badge = document.getElementById('activeLLMBadge');
        if (badge) badge.textContent = data.active_display_name || 'Unknown';
    } catch (e) {
        console.error('Failed to load LLM providers:', e);
        document.getElementById('llmProvidersList').innerHTML =
            '<p style="color:#c62828;">Failed to load providers. Is the backend running?</p>';
    }
}

function renderLLMProviders(data) {
    const container = document.getElementById('llmProvidersList');
    const activeId = data.active_provider;
    let html = '';

    for (const p of data.providers) {
        const isActive = p.id === activeId;
        const isDisabled = !p.enabled;
        const cardClass = isActive ? 'active' : (isDisabled ? 'disabled' : '');
        const statusClass = isActive ? 'active-status' : (p.enabled ? 'available-status' : 'unavailable-status');
        const statusText = isActive ? 'Active' : (p.enabled ? 'Available' : 'Not configured');
        const onclick = isDisabled ? '' : `onclick="selectLLMProvider('${p.id}')"`;

        html += `<div class="llm-provider-card ${cardClass}" ${onclick}>`;
        html += `<div class="provider-header">`;
        html += `<span class="provider-name">${p.name}</span>`;
        html += `<span class="provider-status ${statusClass}">${statusText}</span>`;
        html += `</div>`;
        html += `<div class="provider-description">${p.description}</div>`;
        html += `<div class="provider-models">`;
        for (const m of p.models) {
            const isCurrent = isActive && m === (p.active_model || p.default_model);
            html += `<span class="model-chip ${isCurrent ? 'current' : ''}">${m}</span>`;
        }
        html += `</div></div>`;
    }

    container.innerHTML = html;
}

async function selectLLMProvider(providerId) {
    try {
        const resp = await fetch(`${API_BASE_URL}/api/v1/llm/set-active`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider_id: providerId })
        });
        if (!resp.ok) {
            const err = await resp.json();
            alert('Failed to switch provider: ' + (err.detail || 'Unknown error'));
            return;
        }
        // Reload provider list to reflect change
        await loadLLMProviders();
    } catch (e) {
        console.error('Failed to switch provider:', e);
        alert('Failed to switch provider: ' + e.message);
    }
}

function openLLMSettings() {
    document.getElementById('llmSettingsModal').classList.remove('hidden');
    loadLLMProviders();
}

function closeLLMSettings() {
    document.getElementById('llmSettingsModal').classList.add('hidden');
}

// Close modal on overlay click
document.addEventListener('click', (e) => {
    if (e.target.id === 'llmSettingsModal') {
        closeLLMSettings();
    }
});

// Load active provider badge on startup
document.addEventListener('DOMContentLoaded', () => {
    loadLLMProviders();
});
