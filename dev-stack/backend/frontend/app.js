/**
 * File: app.js
 * Purpose: Main frontend JavaScript for the AI DevOps Platform single-page application. Handles
 *          all UI interactions, chat conversations, tool switching, pipeline progress polling,
 *          and real-time build status updates across all supported CI/CD platforms (GitLab, Jenkins, GitHub Actions).
 * When Used: Loaded by index.html on every page visit. Drives the entire frontend experience including
 *            tool card selection, chat message rendering (with Markdown/code highlighting), approval workflows
 *            for pipeline commits, and progress bar animations during pipeline generation and builds.
 * Why Created: Provides a unified chat-based interface for all backend tools (pipeline generators, Terraform,
 *              secret manager, compliance checker, etc.) so users can interact with the platform through a
 *              single conversational UI rather than needing separate dashboards for each tool.
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
    },
    'secret-manager': {
        name: 'Secret Manager',
        icon: '\u{1F510}',
        viewType: 'secret-manager'
    },
    'dependency-scanner': {
        name: 'Dependency Scanner',
        icon: '\u{1F6E1}',
        viewType: 'dependency-scanner'
    },
    'release-notes': {
        name: 'Release Notes Generator',
        icon: '\u{1F4C4}',
        viewType: 'release-notes'
    },
    'migration-assistant': {
        name: 'Migration Assistant',
        icon: '\u{1F504}',
        viewType: 'migration-assistant'
    },
    'compliance-checker': {
        name: 'Compliance Checker',
        icon: '\u2705',
        viewType: 'compliance-checker'
    },
    'access-manager': {
        name: 'Access Manager',
        icon: '\u{1F465}',
        viewType: 'rbac-manager'
    },
    'tool-directory': {
        name: 'Tool Directory',
        icon: '\u{1F4DA}',
        viewType: 'tool-directory'
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
    const views = ['dashboardView', 'toolView', 'connectivityView', 'terraformNavView', 'commitHistoryView', 'chromadbBrowserView', 'secretManagerView', 'dependencyScannerView', 'releaseNotesView', 'migrationAssistantView', 'complianceCheckerView', 'rbacManagerView', 'toolDirectoryView'];
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

    // Handle secret manager view type
    if (config.viewType === 'secret-manager') {
        openSecretManager();
        return;
    }

    // Handle dependency scanner view type
    if (config.viewType === 'dependency-scanner') {
        openDependencyScanner();
        return;
    }

    // Handle release notes view type
    if (config.viewType === 'release-notes') {
        openReleaseNotesView();
        return;
    }

    // Handle migration assistant view type
    if (config.viewType === 'migration-assistant') {
        openMigrationAssistantView();
        return;
    }

    // Handle compliance checker view type
    if (config.viewType === 'compliance-checker') {
        openComplianceCheckerView();
        return;
    }

    // Handle RBAC access manager view type
    if (config.viewType === 'rbac-manager') {
        openRbacManager();
        return;
    }

    // Handle tool directory view type
    if (config.viewType === 'tool-directory') {
        openToolDirectory();
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

// ========== Secret Manager ==========

let secretManagerData = null;
let secretManagerPlatformFilter = 'all';
let secretEditMode = null; // null = add, {platform, scope, key} = edit

function openSecretManager() {
    switchView('secretManagerView');
    refreshSecretManager();
}

async function refreshSecretManager() {
    const grid = document.getElementById('secretsGrid');
    grid.innerHTML = '<div class="connectivity-loading"><span class="spinner"></span> Loading secrets...</div>';

    try {
        const response = await fetch(`${API_BASE_URL}/api/v1/secret-manager/list`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const raw = await response.json();

        // Normalize: extract secrets arrays from platforms wrapper
        const p = raw.platforms || {};
        secretManagerData = {
            gitlab: (p.gitlab && p.gitlab.secrets) || [],
            gitea_jenkins: (p.gitea_jenkins && p.gitea_jenkins.secrets) || [],
            gitea_github: (p.gitea_github && p.gitea_github.secrets) || [],
            jenkins: (p.jenkins && p.jenkins.secrets) || []
        };

        // Update summary counts
        let total = 0, gitlabCount = 0, giteaCount = 0, jenkinsCount = 0;
        gitlabCount = secretManagerData.gitlab.length; total += gitlabCount;
        giteaCount += secretManagerData.gitea_jenkins.length; total += secretManagerData.gitea_jenkins.length;
        giteaCount += secretManagerData.gitea_github.length; total += secretManagerData.gitea_github.length;
        jenkinsCount = secretManagerData.jenkins.length; total += jenkinsCount;

        document.getElementById('secretTotalCount').textContent = total;
        document.getElementById('secretGitlabCount').textContent = gitlabCount;
        document.getElementById('secretGiteaCount').textContent = giteaCount;
        document.getElementById('secretJenkinsCount').textContent = jenkinsCount;

        renderSecrets();
    } catch (error) {
        grid.innerHTML = `<div class="connectivity-error">Failed to load secrets: ${error.message}</div>`;
    }
}

function switchSecretPlatform(platform) {
    secretManagerPlatformFilter = platform;
    document.querySelectorAll('.secret-platform-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.platform === platform);
    });
    renderSecrets();
}

function renderSecrets() {
    const grid = document.getElementById('secretsGrid');
    if (!secretManagerData) { grid.innerHTML = '<p style="color:#888;">No data loaded.</p>'; return; }

    const platforms = {
        gitlab: { label: 'GitLab', color: '#e24329', items: secretManagerData.gitlab || [] },
        gitea_jenkins: { label: 'Gitea (Jenkins)', color: '#609926', items: secretManagerData.gitea_jenkins || [] },
        gitea_github: { label: 'Gitea (GitHub)', color: '#609926', items: secretManagerData.gitea_github || [] },
        jenkins: { label: 'Jenkins', color: '#d33833', items: secretManagerData.jenkins || [] }
    };

    let html = '';
    for (const [key, p] of Object.entries(platforms)) {
        if (secretManagerPlatformFilter !== 'all' && key !== secretManagerPlatformFilter) continue;
        if (p.items.length === 0) continue;

        html += `<div style="margin-bottom:20px;">`;
        html += `<h3 style="font-size:0.95em;margin:0 0 8px;color:${p.color};">${p.label} <span style="color:#888;font-weight:normal;">(${p.items.length})</span></h3>`;
        html += `<table style="width:100%;border-collapse:collapse;font-size:0.85em;">`;
        html += `<thead><tr style="background:#f1f5f9;"><th style="padding:8px;text-align:left;">Key</th><th style="padding:8px;text-align:left;">Scope / Project</th><th style="padding:8px;text-align:left;">Value</th><th style="padding:8px;width:100px;">Actions</th></tr></thead><tbody>`;

        for (const s of p.items) {
            const scope = s.display_name || s.scope || s.org || '-';
            const maskedVal = s.value || '***';
            const deleteScope = s.project_id || s.org || s.scope || '';
            html += `<tr style="border-bottom:1px solid #f1f5f9;">`;
            html += `<td style="padding:6px 8px;font-family:monospace;font-weight:600;">${escapeHtml(s.key)}</td>`;
            html += `<td style="padding:6px 8px;color:#666;">${escapeHtml(scope)}</td>`;
            html += `<td style="padding:6px 8px;font-family:monospace;color:#999;">${escapeHtml(maskedVal)}</td>`;
            html += `<td style="padding:6px 8px;text-align:center;">`;
            html += `<button onclick="deleteSecretAction('${key}','${escapeHtml(s.key)}','${escapeHtml(String(deleteScope))}')" style="background:#ef4444;color:#fff;border:none;padding:2px 8px;border-radius:4px;cursor:pointer;font-size:0.8em;">Delete</button>`;
            html += `</td></tr>`;
        }
        html += '</tbody></table></div>';
    }

    if (!html) html = '<p style="color:#888;text-align:center;padding:40px 0;">No secrets found for this filter.</p>';
    grid.innerHTML = html;
}

function openAddSecretModal() {
    secretEditMode = null;
    document.getElementById('secretModalTitle').textContent = 'Add Secret';
    document.getElementById('secretPlatform').value = 'gitlab';
    document.getElementById('secretKey').value = '';
    document.getElementById('secretValue').value = '';
    document.getElementById('secretKey').disabled = false;
    document.getElementById('secretProtected').checked = false;
    document.getElementById('secretMasked').checked = false;
    document.getElementById('secretEnvScope').value = '*';
    document.getElementById('secretDescription').value = '';
    onSecretPlatformChange();
    document.getElementById('secretModal').classList.remove('hidden');
    loadGitlabProjectsForModal();
}

function closeSecretModal() {
    document.getElementById('secretModal').classList.add('hidden');
}

function onSecretPlatformChange() {
    const platform = document.getElementById('secretPlatform').value;
    document.getElementById('secretProjectGroup').style.display = platform === 'gitlab' ? 'block' : 'none';
    document.getElementById('secretGitlabOptions').style.display = platform === 'gitlab' ? 'block' : 'none';
    document.getElementById('secretJenkinsOptions').style.display = platform === 'jenkins' ? 'block' : 'none';
}

async function loadGitlabProjectsForModal() {
    const sel = document.getElementById('secretProject');
    sel.innerHTML = '<option value="">Loading...</option>';
    try {
        const resp = await fetch(`${API_BASE_URL}/api/v1/secret-manager/gitlab/projects`);
        if (!resp.ok) throw new Error('Failed');
        const data = await resp.json();
        sel.innerHTML = '';
        for (const p of (data.projects || [])) {
            sel.innerHTML += `<option value="${p.id}">${escapeHtml(p.name_with_namespace || p.name)}</option>`;
        }
    } catch (e) {
        sel.innerHTML = '<option value="">Failed to load</option>';
    }
}

function toggleSecretValueVisibility() {
    const inp = document.getElementById('secretValue');
    inp.type = inp.type === 'password' ? 'text' : 'password';
}

async function submitSecret() {
    const btn = document.getElementById('secretSubmitBtn');
    const platform = document.getElementById('secretPlatform').value;
    const key = document.getElementById('secretKey').value.trim();
    const value = document.getElementById('secretValue').value;

    if (!key) { alert('Key is required'); return; }
    if (!value) { alert('Value is required'); return; }

    const body = { platform, key, value };

    if (platform === 'gitlab') {
        body.scope = document.getElementById('secretProject').value;
        body.protected_var = document.getElementById('secretProtected').checked;
        body.masked = document.getElementById('secretMasked').checked;
        body.environment_scope = document.getElementById('secretEnvScope').value || '*';
    } else if (platform === 'jenkins') {
        body.description = document.getElementById('secretDescription').value;
    }

    btn.disabled = true;
    btn.textContent = 'Saving...';

    try {
        const resp = await fetch(`${API_BASE_URL}/api/v1/secret-manager/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const result = await resp.json();
        if (!resp.ok || !result.success) throw new Error(result.detail || result.error || 'Failed');
        closeSecretModal();
        refreshSecretManager();
    } catch (error) {
        alert('Save failed: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Save';
    }
}

async function deleteSecretAction(platform, key, scope) {
    if (!confirm(`Delete secret "${key}" from ${platform}?`)) return;
    try {
        const resp = await fetch(`${API_BASE_URL}/api/v1/secret-manager/delete`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ platform, key, scope })
        });
        const result = await resp.json();
        if (!resp.ok || !result.success) throw new Error(result.detail || result.error || 'Failed');
        refreshSecretManager();
    } catch (error) {
        alert('Delete failed: ' + error.message);
    }
}


// ========== Dependency Scanner ==========

function openDependencyScanner() {
    switchView('dependencyScannerView');
    loadNexusImages();
}

async function loadNexusImages() {
    const sel = document.getElementById('depScanImageSelect');
    sel.innerHTML = '<option value="">Loading images...</option>';

    try {
        const resp = await fetch(`${API_BASE_URL}/api/v1/dependency-scanner/images`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        sel.innerHTML = '<option value="">-- Select from registry --</option>';
        if (data.images && data.images.length > 0) {
            for (const img of data.images) {
                const tags = img.tags || [img.version || 'latest'];
                for (const tag of tags) {
                    const fullName = `${img.name}:${tag}`;
                    sel.innerHTML += `<option value="${escapeHtml(fullName)}">${escapeHtml(fullName)}</option>`;
                }
            }
        }
    } catch (e) {
        sel.innerHTML = '<option value="">Failed to load images</option>';
    }
}

function depScanSelectImage(val) {
    if (val) document.getElementById('depScanImageInput').value = val;
}

async function runDependencyScan() {
    const imageFromSelect = document.getElementById('depScanImageSelect').value;
    const imageFromInput = document.getElementById('depScanImageInput').value.trim();
    const image = imageFromInput || imageFromSelect;

    if (!image) { alert('Please select or enter a Docker image.'); return; }

    const severity = document.getElementById('depScanSeverity').value;
    const ignoreUnfixed = document.getElementById('depScanIgnoreUnfixed').checked;
    const btn = document.getElementById('depScanBtn');
    const resultsDiv = document.getElementById('depScanResults');

    btn.disabled = true;
    btn.textContent = 'Scanning...';
    resultsDiv.innerHTML = '<div class="connectivity-loading"><span class="spinner"></span> Scanning image... this may take a minute.</div>';

    try {
        const resp = await fetch(`${API_BASE_URL}/api/v1/dependency-scanner/scan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image, severity, ignore_unfixed: ignoreUnfixed })
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }
        const data = await resp.json();

        if (!data.success) throw new Error(data.error || 'Scan failed');

        // Update summary bar
        const summary = data.summary || {};
        document.getElementById('depScanSummary').style.display = 'flex';
        document.getElementById('depScanTotal').textContent = summary.total || 0;
        document.getElementById('depScanCritical').textContent = summary.critical || 0;
        document.getElementById('depScanHigh').textContent = summary.high || 0;
        document.getElementById('depScanMedium').textContent = summary.medium || 0;
        document.getElementById('depScanLow').textContent = summary.low || 0;

        renderVulnerabilityTable(data.vulnerabilities || []);
    } catch (error) {
        resultsDiv.innerHTML = `<div class="connectivity-error">Scan failed: ${error.message}</div>`;
        document.getElementById('depScanSummary').style.display = 'none';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Scan Image';
    }
}

function renderVulnerabilityTable(vulns) {
    const resultsDiv = document.getElementById('depScanResults');
    if (!vulns || vulns.length === 0) {
        resultsDiv.innerHTML = '<p style="color:#22c55e;text-align:center;padding:40px 0;font-size:1.1em;font-weight:600;">No vulnerabilities found!</p>';
        return;
    }

    const severityColors = { CRITICAL: '#ef4444', HIGH: '#f97316', MEDIUM: '#f59e0b', LOW: '#3b82f6', UNKNOWN: '#9ca3af' };

    let html = `<table style="width:100%;border-collapse:collapse;font-size:0.83em;margin-top:12px;">`;
    html += `<thead><tr style="background:#f1f5f9;"><th style="padding:8px;text-align:left;">Package</th><th style="padding:8px;">Severity</th><th style="padding:8px;text-align:left;">Installed</th><th style="padding:8px;text-align:left;">Fixed In</th><th style="padding:8px;text-align:left;">CVE</th><th style="padding:8px;text-align:left;max-width:300px;">Title</th></tr></thead><tbody>`;

    for (const v of vulns) {
        const sev = (v.Severity || v.severity || 'UNKNOWN').toUpperCase();
        const color = severityColors[sev] || '#9ca3af';
        const cveId = v.VulnerabilityID || v.vulnerability_id || '';
        const cveLink = cveId.startsWith('CVE-') ? `<a href="https://nvd.nist.gov/vuln/detail/${cveId}" target="_blank" style="color:#3b82f6;">${escapeHtml(cveId)}</a>` : escapeHtml(cveId);

        html += `<tr style="border-bottom:1px solid #f1f5f9;">`;
        html += `<td style="padding:6px 8px;font-family:monospace;">${escapeHtml(v.PkgName || v.pkg_name || '')}</td>`;
        html += `<td style="padding:6px 8px;text-align:center;"><span style="background:${color};color:#fff;padding:2px 8px;border-radius:4px;font-size:0.85em;font-weight:600;">${sev}</span></td>`;
        html += `<td style="padding:6px 8px;font-family:monospace;font-size:0.95em;">${escapeHtml(v.InstalledVersion || v.installed_version || '')}</td>`;
        html += `<td style="padding:6px 8px;font-family:monospace;font-size:0.95em;color:#22c55e;">${escapeHtml(v.FixedVersion || v.fixed_version || '-')}</td>`;
        html += `<td style="padding:6px 8px;">${cveLink}</td>`;
        html += `<td style="padding:6px 8px;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(v.Title || v.title || '')}">${escapeHtml(v.Title || v.title || '')}</td>`;
        html += `</tr>`;
    }
    html += '</tbody></table>';
    resultsDiv.innerHTML = html;
}


// ========== Release Notes Generator ==========

function openReleaseNotesView() {
    switchView('releaseNotesView');
    // Set default dates: last 30 days
    const now = new Date();
    const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    document.getElementById('rnUntil').value = now.toISOString().split('T')[0];
    document.getElementById('rnSince').value = monthAgo.toISOString().split('T')[0];
}

async function fetchRNBranches() {
    const repoUrl = document.getElementById('rnRepoUrl').value.trim();
    if (!repoUrl) return;

    const sel = document.getElementById('rnBranch');
    sel.innerHTML = '<option value="">Loading...</option>';

    try {
        const resp = await fetch(`${API_BASE_URL}/api/v1/release-notes/branches`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ repo_url: repoUrl })
        });
        if (!resp.ok) throw new Error('Failed');
        const data = await resp.json();

        sel.innerHTML = '<option value="">All branches</option>';
        for (const b of (data.branches || [])) {
            const name = typeof b === 'string' ? b : b.name;
            sel.innerHTML += `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`;
        }
    } catch (e) {
        sel.innerHTML = '<option value="">All branches</option>';
    }
}

async function generateReleaseNotes() {
    const repoUrl = document.getElementById('rnRepoUrl').value.trim();
    if (!repoUrl) { alert('Please enter a repository URL.'); return; }

    const branch = document.getElementById('rnBranch').value;
    const since = document.getElementById('rnSince').value;
    const until = document.getElementById('rnUntil').value;
    const formatStyle = document.getElementById('rnFormat').value;

    const btn = document.getElementById('rnGenerateBtn');
    const output = document.getElementById('releaseNotesOutput');
    btn.disabled = true;
    btn.textContent = 'Generating...';
    output.innerHTML = '<div class="connectivity-loading"><span class="spinner"></span> Generating release notes via LLM... this may take a moment.</div>';

    try {
        const resp = await fetch(`${API_BASE_URL}/api/v1/release-notes/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ repo_url: repoUrl, branch: branch || undefined, since: since || undefined, until: until || undefined, format_style: formatStyle })
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Generation failed');

        const md = data.release_notes || '*(empty)*';
        const commitCount = data.commit_count || 0;

        let html = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">`;
        html += `<span style="background:#e0e7ff;color:#3730a3;padding:4px 12px;border-radius:12px;font-size:0.85em;font-weight:600;">${commitCount} commits analyzed</span>`;
        html += `<button onclick="copyReleaseNotes()" style="padding:6px 16px;background:#22c55e;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:0.85em;">Copy to Clipboard</button>`;
        html += `</div>`;
        html += `<div id="rnMarkdownContent" style="font-family:system-ui;line-height:1.6;white-space:pre-wrap;background:#f8f9fa;padding:16px;border-radius:8px;border:1px solid #e5e7eb;">${escapeHtml(md)}</div>`;
        output.innerHTML = html;
    } catch (error) {
        output.innerHTML = `<div class="connectivity-error">Failed: ${error.message}</div>`;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Generate';
    }
}

function copyReleaseNotes() {
    const el = document.getElementById('rnMarkdownContent');
    if (el) {
        navigator.clipboard.writeText(el.textContent).then(() => {
            const btn = event.target;
            btn.textContent = 'Copied!';
            setTimeout(() => btn.textContent = 'Copy to Clipboard', 1500);
        });
    }
}


// ========== Migration Assistant ==========

function openMigrationAssistantView() {
    switchView('migrationAssistantView');
    document.getElementById('migSourceInput').value = '';
    document.getElementById('migConvertedOutput').textContent = '';
    document.getElementById('migDockerfileSection').style.display = 'none';
    document.getElementById('migCopyBtn').style.display = 'none';
}

function detectPipelineFormat() {
    const content = document.getElementById('migSourceInput').value.trim();
    if (content.length < 20) return;

    // Simple client-side detection to auto-set source dropdown
    const sel = document.getElementById('migSourceFormat');
    if (content.includes('stages:') && (content.includes('script:') || content.includes('.gitlab-ci'))) {
        sel.value = 'gitlab';
    } else if (content.includes('pipeline {') || content.includes('pipeline{') || content.includes('agent ')) {
        sel.value = 'jenkins';
    } else if (content.includes('on:') && (content.includes('jobs:') || content.includes('runs-on'))) {
        sel.value = 'github-actions';
    }
}

async function convertPipeline() {
    const content = document.getElementById('migSourceInput').value.trim();
    if (!content) { alert('Please paste a pipeline configuration.'); return; }

    const sourceFormat = document.getElementById('migSourceFormat').value;
    const targetFormat = document.getElementById('migTargetFormat').value;
    const language = document.getElementById('migLanguage').value;
    const useLLM = document.getElementById('migUseLLM').checked;

    if (sourceFormat === targetFormat) { alert('Source and target formats must be different.'); return; }

    const btn = document.getElementById('migConvertBtn');
    const output = document.getElementById('migConvertedOutput');
    btn.disabled = true;
    btn.textContent = 'Converting...';
    output.textContent = 'Converting...';
    document.getElementById('migDockerfileSection').style.display = 'none';
    document.getElementById('migCopyBtn').style.display = 'none';

    try {
        const resp = await fetch(`${API_BASE_URL}/api/v1/migration-assistant/convert`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pipeline_content: content, source_format: sourceFormat, target_format: targetFormat, language: language || undefined, use_llm: useLLM })
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.detail || `HTTP ${resp.status}`);
        }
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Conversion failed');

        output.textContent = data.converted || '(empty result)';
        document.getElementById('migCopyBtn').style.display = 'inline-block';

        if (data.dockerfile) {
            document.getElementById('migDockerfileSection').style.display = 'block';
            document.getElementById('migDockerfileOutput').textContent = data.dockerfile;
        }
    } catch (error) {
        output.textContent = 'Error: ' + error.message;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Convert';
    }
}

function copyConvertedPipeline() {
    const text = document.getElementById('migConvertedOutput').textContent;
    navigator.clipboard.writeText(text).then(() => {
        const btn = document.getElementById('migCopyBtn');
        btn.textContent = 'Copied!';
        setTimeout(() => btn.textContent = 'Copy', 1500);
    });
}


// ========== Compliance Checker ==========

let complianceProjects = [];

function openComplianceCheckerView() {
    switchView('complianceCheckerView');
    loadComplianceDashboard();
}

async function loadComplianceDashboard() {
    const resultsDiv = document.getElementById('complianceResults');
    resultsDiv.innerHTML = '<div class="connectivity-loading"><span class="spinner"></span> Loading compliance dashboard...</div>';
    document.getElementById('complianceSummary').style.display = 'none';

    const search = document.getElementById('complianceSearch').value.trim();

    try {
        const resp = await fetch(`${API_BASE_URL}/api/v1/compliance/dashboard`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ search: search || null })
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Failed to load dashboard');

        complianceProjects = data.projects || [];
        const summary = data.summary || {};

        document.getElementById('complianceSummary').style.display = 'flex';
        document.getElementById('complianceTotalCount').textContent = summary.total || complianceProjects.length;
        document.getElementById('compliancePassCount').textContent = summary.pass || 0;
        document.getElementById('complianceWarnCount').textContent = summary.warn || 0;
        document.getElementById('complianceFailCount').textContent = summary.fail || 0;

        renderComplianceProjects();
    } catch (error) {
        resultsDiv.innerHTML = `<div class="connectivity-error">Failed to load dashboard: ${error.message}</div>`;
    }
}

function renderComplianceProjects() {
    const resultsDiv = document.getElementById('complianceResults');
    if (complianceProjects.length === 0) {
        resultsDiv.innerHTML = '<p style="color:#888;text-align:center;padding:40px 0;">No SonarQube projects found.</p>';
        return;
    }

    const statusColors = { PASS: '#22c55e', WARN: '#f59e0b', FAIL: '#ef4444' };
    const qgColors = { OK: '#22c55e', WARN: '#f59e0b', ERROR: '#ef4444' };

    let html = '';
    for (let i = 0; i < complianceProjects.length; i++) {
        const p = complianceProjects[i];
        const status = p.compliance_status || 'UNKNOWN';
        const qg = (p.quality_gate && p.quality_gate.status) || p.quality_gate_status || 'UNKNOWN';
        const sColor = statusColors[status] || '#9ca3af';
        const qColor = qgColors[qg] || '#9ca3af';

        html += `<div style="border:1px solid #e5e7eb;border-radius:8px;margin:8px 0;overflow:hidden;border-left:4px solid ${sColor};">`;
        html += `<div onclick="toggleComplianceDetail(${i})" style="padding:12px 16px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;background:#fff;">`;
        html += `<div style="display:flex;align-items:center;gap:12px;">`;
        html += `<span style="font-weight:600;">${escapeHtml(p.project_key || p.name || '')}</span>`;
        html += `<span style="background:${sColor};color:#fff;padding:2px 10px;border-radius:12px;font-size:0.8em;font-weight:600;">${status}</span>`;
        html += `<span style="background:${qColor}22;color:${qColor};padding:2px 8px;border-radius:4px;font-size:0.78em;">QG: ${qg}</span>`;
        html += `</div><span id="complianceArrow${i}" style="transition:transform 0.2s;">&#9654;</span></div>`;

        html += `<div id="complianceDetail${i}" style="display:none;padding:12px 16px;background:#f8f9fa;border-top:1px solid #e5e7eb;">`;

        // Metrics
        const metrics = p.metrics || {};
        html += `<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:12px;">`;
        const metricItems = [
            { label: 'Bugs', value: metrics.bugs, color: metrics.bugs > 0 ? '#f97316' : '#22c55e' },
            { label: 'Vulns', value: metrics.vulnerabilities, color: metrics.vulnerabilities > 0 ? '#ef4444' : '#22c55e' },
            { label: 'Smells', value: metrics.code_smells, color: metrics.code_smells > 50 ? '#f59e0b' : '#666' },
            { label: 'Coverage', value: metrics.coverage != null ? metrics.coverage + '%' : 'N/A', color: '#3b82f6' },
            { label: 'Duplications', value: metrics.duplicated_lines_density != null ? metrics.duplicated_lines_density + '%' : 'N/A', color: '#666' },
            { label: 'Lines', value: metrics.ncloc, color: '#666' }
        ];
        for (const m of metricItems) {
            if (m.value == null) continue;
            html += `<div style="text-align:center;"><div style="font-size:1.1em;font-weight:600;color:${m.color};">${m.value}</div><div style="font-size:0.75em;color:#888;">${m.label}</div></div>`;
        }
        html += `</div>`;

        // Scan button
        html += `<div style="display:flex;gap:8px;align-items:center;margin-top:8px;">`;
        html += `<button onclick="scanComplianceImage('${escapeHtml(p.project_key || '')}', this)" style="padding:6px 14px;background:#3b82f6;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:0.85em;">Scan Docker Image</button>`;
        html += `<span id="complianceScanResult${i}" style="font-size:0.85em;color:#888;"></span>`;
        html += `</div></div></div>`;
    }

    resultsDiv.innerHTML = html;
}

function toggleComplianceDetail(idx) {
    const detail = document.getElementById(`complianceDetail${idx}`);
    const arrow = document.getElementById(`complianceArrow${idx}`);
    if (detail.style.display === 'none') {
        detail.style.display = 'block';
        arrow.style.transform = 'rotate(90deg)';
    } else {
        detail.style.display = 'none';
        arrow.style.transform = 'rotate(0deg)';
    }
}

async function scanComplianceImage(projectKey, btn) {
    btn.disabled = true;
    btn.textContent = 'Scanning...';
    const resultSpan = btn.nextElementSibling;
    resultSpan.textContent = '';

    try {
        // First find Docker images
        const imgResp = await fetch(`${API_BASE_URL}/api/v1/compliance/project/${encodeURIComponent(projectKey)}/images`);
        if (!imgResp.ok) throw new Error('Failed to find images');
        const imgData = await imgResp.json();

        const images = imgData.images || [];
        if (images.length === 0) {
            resultSpan.textContent = 'No Docker images found in Nexus for this project.';
            resultSpan.style.color = '#f59e0b';
            return;
        }

        // Scan the first matching image
        const image = images[0].name + ':' + (images[0].tag || images[0].version || 'latest');
        const scanResp = await fetch(`${API_BASE_URL}/api/v1/compliance/project/compliance`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_key: projectKey, docker_image: image })
        });
        if (!scanResp.ok) throw new Error('Scan failed');
        const scanData = await scanResp.json();

        if (scanData.trivy) {
            const t = scanData.trivy;
            resultSpan.innerHTML = `<span style="color:#ef4444;font-weight:600;">${t.critical || 0}C</span> / <span style="color:#f97316;">${t.high || 0}H</span> / <span style="color:#f59e0b;">${t.medium || 0}M</span> / <span style="color:#3b82f6;">${t.low || 0}L</span> — ${escapeHtml(image)}`;
            resultSpan.style.color = '';
        } else {
            resultSpan.textContent = 'Scan complete (no vuln data returned)';
        }
    } catch (error) {
        resultSpan.textContent = 'Error: ' + error.message;
        resultSpan.style.color = '#ef4444';
    } finally {
        btn.disabled = false;
        btn.textContent = 'Scan Docker Image';
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


// ========== Access Manager (RBAC) ==========

let rbacData = null;

function openRbacManager() {
    switchView('rbacManagerView');
    loadRbacOverview();
}

async function loadRbacOverview() {
    const content = document.getElementById('rbacContent');
    content.innerHTML = '<div class="connectivity-loading"><span class="spinner"></span> Loading access data from all tools...</div>';
    document.getElementById('rbacSummary').style.display = 'none';

    try {
        const resp = await fetch(`${API_BASE_URL}/api/v1/rbac/overview`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        rbacData = await resp.json();

        // Update summary
        const s = rbacData.summary || {};
        document.getElementById('rbacSummary').style.display = 'flex';
        document.getElementById('rbacTotalUsers').textContent = s.total_users || 0;
        document.getElementById('rbacReadonlyCount').textContent = s.readonly || 0;
        document.getElementById('rbacReadwriteCount').textContent = s.readwrite || 0;
        document.getElementById('rbacAdminCount').textContent = s.admin || 0;

        // Populate user dropdown
        const select = document.getElementById('rbacUserSelect');
        const currentVal = select.value;
        select.innerHTML = '<option value="">-- All Users --</option>';
        for (const user of rbacData.users || []) {
            const opt = document.createElement('option');
            opt.value = user.username;
            opt.textContent = `${user.username}${user.display_name && user.display_name !== user.username ? ' (' + user.display_name + ')' : ''}`;
            select.appendChild(opt);
        }
        if (currentVal) select.value = currentVal;

        renderRbacContent(select.value);
    } catch (error) {
        content.innerHTML = `<div class="connectivity-error">Failed to load access data: ${error.message}</div>`;
    }
}

function onRbacUserSelect(username) {
    renderRbacContent(username);
}

function renderRbacContent(selectedUser) {
    const content = document.getElementById('rbacContent');
    if (!rbacData) { content.innerHTML = '<p style="color:#888;">No data.</p>'; return; }

    const tools = rbacData.tools || [];
    const groupLabels = rbacData.group_labels || {};
    const availableGroups = rbacData.available_groups || [];
    let html = '';

    if (selectedUser) {
        // Single user detail view
        const user = (rbacData.users || []).find(u => u.username === selectedUser);
        if (!user) { content.innerHTML = '<p style="color:#888;">User not found.</p>'; return; }

        html += `<h3 style="margin:0 0 16px;font-size:1em;">Access for: <span style="color:#3b82f6;">${escapeHtml(user.username)}</span>`;
        if (user.display_name && user.display_name !== user.username) {
            html += ` <span style="color:#888;font-weight:normal;">(${escapeHtml(user.display_name)})</span>`;
        }
        html += `</h3>`;

        html += `<table style="width:100%;border-collapse:collapse;font-size:0.9em;">`;
        html += `<thead><tr style="background:#f1f5f9;">`;
        html += `<th style="padding:10px 12px;text-align:left;width:140px;">Tool</th>`;
        html += `<th style="padding:10px 12px;text-align:left;">Current Access</th>`;
        html += `<th style="padding:10px 12px;text-align:left;width:200px;">Change Access</th>`;
        html += `</tr></thead><tbody>`;

        const toolDisplay = { gitlab: 'GitLab', gitea: 'Gitea', sonarqube: 'SonarQube', nexus: 'Nexus', jenkins: 'Jenkins' };
        const toolColors = { gitlab: '#e24329', gitea: '#609926', sonarqube: '#4e9bcd', nexus: '#1ba1c5', jenkins: '#d33833' };

        for (const tool of tools) {
            const td = user.tools[tool] || { groups: [], access_level: 'none' };
            const level = td.access_level || 'none';
            const levelLabel = groupLabels[level] || 'No Access';
            const levelColor = level === 'devops-admin' ? '#ef4444' : level === 'devops-readwrite' ? '#f59e0b' : level === 'devops-readonly' ? '#22c55e' : '#9ca3af';

            html += `<tr style="border-bottom:1px solid #f1f5f9;">`;
            html += `<td style="padding:10px 12px;font-weight:600;color:${toolColors[tool] || '#333'};">${toolDisplay[tool] || tool}</td>`;
            html += `<td style="padding:10px 12px;"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${levelColor};margin-right:8px;"></span>${levelLabel}`;
            if (td.groups.length > 0) {
                html += ` <span style="color:#888;font-size:0.85em;">(${td.groups.join(', ')})</span>`;
            }
            html += `</td>`;
            html += `<td style="padding:10px 12px;">`;
            html += `<select onchange="changeRbacAccess('${escapeHtml(user.username)}', '${tool}', this.value, '${level}')" style="padding:5px 8px;border:1px solid #d1d5db;border-radius:4px;font-size:0.85em;background:#fff;">`;
            html += `<option value="">-- Change --</option>`;
            for (const g of availableGroups) {
                const selected = g === level ? ' selected disabled' : '';
                html += `<option value="${g}"${selected}>${groupLabels[g] || g}</option>`;
            }
            html += `<option value="__revoke__">Revoke All</option>`;
            html += `</select></td>`;
            html += `</tr>`;
        }
        html += `</tbody></table>`;
    }

    // All users matrix
    html += `<div style="margin-top:${selectedUser ? '28px' : '0'};"><h3 style="margin:0 0 12px;font-size:1em;color:#555;border-bottom:2px solid #e5e7eb;padding-bottom:8px;">All Users Overview</h3>`;
    html += `<div style="overflow-x:auto;">`;
    html += `<table style="width:100%;border-collapse:collapse;font-size:0.85em;min-width:600px;">`;
    html += `<thead><tr style="background:#f1f5f9;">`;
    html += `<th style="padding:8px 10px;text-align:left;position:sticky;left:0;background:#f1f5f9;z-index:1;">User</th>`;

    const toolHeaders = { gitlab: 'GitLab', gitea: 'Gitea', sonarqube: 'SonarQube', nexus: 'Nexus', jenkins: 'Jenkins' };
    for (const t of tools) {
        html += `<th style="padding:8px 10px;text-align:center;">${toolHeaders[t] || t}</th>`;
    }
    html += `</tr></thead><tbody>`;

    for (const user of rbacData.users || []) {
        const isSelected = user.username === selectedUser;
        const rowBg = isSelected ? 'background:#eff6ff;' : '';
        html += `<tr style="border-bottom:1px solid #f1f5f9;${rowBg}cursor:pointer;" onclick="document.getElementById('rbacUserSelect').value='${escapeHtml(user.username)}';onRbacUserSelect('${escapeHtml(user.username)}')">`;
        html += `<td style="padding:7px 10px;font-weight:${isSelected ? '700' : '500'};position:sticky;left:0;background:${isSelected ? '#eff6ff' : '#fff'};z-index:1;">${escapeHtml(user.username)}</td>`;

        for (const t of tools) {
            const td = (user.tools || {})[t] || { access_level: 'none' };
            const level = td.access_level || 'none';
            const badge = _rbacBadge(level);
            html += `<td style="padding:7px 10px;text-align:center;">${badge}</td>`;
        }
        html += `</tr>`;
    }
    html += `</tbody></table></div></div>`;

    content.innerHTML = html;
}

function _rbacBadge(level) {
    const map = {
        'devops-admin': { label: 'Admin', bg: '#fce4ec', color: '#c62828' },
        'devops-readwrite': { label: 'R/W', bg: '#fff8e1', color: '#f57f17' },
        'devops-readonly': { label: 'RO', bg: '#e8f5e9', color: '#2e7d32' },
        'none': { label: '-', bg: 'transparent', color: '#bbb' },
    };
    const m = map[level] || map['none'];
    if (level === 'none') return `<span style="color:#ccc;">-</span>`;
    return `<span style="background:${m.bg};color:${m.color};padding:2px 8px;border-radius:10px;font-size:0.8em;font-weight:600;">${m.label}</span>`;
}

async function changeRbacAccess(username, tool, newGroup, currentLevel) {
    if (!newGroup) return;

    // Revoke all current groups first if changing
    if (newGroup === '__revoke__') {
        if (!confirm(`Revoke all access for '${username}' on ${tool}?`)) return;
        // Revoke current level
        if (currentLevel && currentLevel !== 'none') {
            const resp = await fetch(`${API_BASE_URL}/api/v1/rbac/revoke`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, tool, group: currentLevel })
            });
            const data = await resp.json();
            alert(data.message || 'Done');
        }
    } else {
        // Revoke old, grant new
        if (currentLevel && currentLevel !== 'none' && currentLevel !== newGroup) {
            await fetch(`${API_BASE_URL}/api/v1/rbac/revoke`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, tool, group: currentLevel })
            });
        }
        const resp = await fetch(`${API_BASE_URL}/api/v1/rbac/grant`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, tool, group: newGroup })
        });
        const data = await resp.json();
        if (!data.success) {
            alert('Error: ' + (data.message || 'Failed'));
        }
    }

    // Refresh
    await loadRbacOverview();
}


// ========== Tool Directory ==========

let toolDirectoryData = null;

function openToolDirectory() {
    switchView('toolDirectoryView');
    loadToolDirectory();
}

async function loadToolDirectory() {
    const content = document.getElementById('toolDirectoryContent');
    content.innerHTML = '<div class="connectivity-loading"><span class="spinner"></span> Loading tools...</div>';

    try {
        const resp = await fetch(`${API_BASE_URL}/api/v1/rbac/tool-directory`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        toolDirectoryData = await resp.json();
        renderToolDirectory();
    } catch (error) {
        content.innerHTML = `<div class="connectivity-error">Failed to load tool directory: ${error.message}</div>`;
    }
}

function renderToolDirectory() {
    const content = document.getElementById('toolDirectoryContent');
    if (!toolDirectoryData || toolDirectoryData.length === 0) {
        content.innerHTML = '<p style="color:#888;text-align:center;padding:40px;">No tools configured.</p>';
        return;
    }

    let html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px;">';

    for (const tool of toolDirectoryData) {
        const creds = tool.credentials || {};
        const hasCredentials = Object.keys(creds).length > 0;
        const authLabel = tool.auth_type === 'none' ? 'No Auth' : tool.auth_type === 'token' ? 'Token' : 'Basic Auth';

        html += `<div style="border:1px solid #e5e7eb;border-radius:10px;overflow:hidden;background:#fff;border-left:4px solid ${tool.color};">`;

        // Header
        html += `<div style="padding:14px 16px;display:flex;justify-content:space-between;align-items:center;">`;
        html += `<div style="display:flex;align-items:center;gap:10px;">`;
        html += `<span style="font-size:1.3em;">${_toolDirIcon(tool.id)}</span>`;
        html += `<div>`;
        html += `<div style="font-weight:700;font-size:0.95em;color:#1a1a1a;">${escapeHtml(tool.name)}</div>`;
        html += `<div style="font-size:0.78em;color:#888;">${escapeHtml(tool.description)}</div>`;
        html += `</div></div>`;
        html += `<span style="background:${tool.color}22;color:${tool.color};padding:2px 8px;border-radius:10px;font-size:0.75em;font-weight:600;">${authLabel}</span>`;
        html += `</div>`;

        // URL
        html += `<div style="padding:0 16px 10px;display:flex;flex-direction:column;gap:6px;">`;
        html += `<div style="display:flex;align-items:center;gap:8px;">`;
        html += `<span style="font-size:0.78em;color:#888;min-width:30px;">URL</span>`;
        html += `<a href="${escapeHtml(tool.browser_url)}" target="_blank" rel="noopener" style="color:#3b82f6;font-size:0.88em;font-family:monospace;text-decoration:none;word-break:break-all;" onmouseover="this.style.textDecoration='underline'" onmouseout="this.style.textDecoration='none'">${escapeHtml(tool.browser_url)} &#8599;</a>`;
        html += `</div>`;

        // Extra URLs
        if (tool.extra_urls) {
            for (const extra of tool.extra_urls) {
                html += `<div style="display:flex;align-items:center;gap:8px;">`;
                html += `<span style="font-size:0.78em;color:#888;min-width:30px;"></span>`;
                html += `<a href="${escapeHtml(extra.url)}" target="_blank" rel="noopener" style="color:#6b7280;font-size:0.82em;font-family:monospace;text-decoration:none;" onmouseover="this.style.textDecoration='underline'" onmouseout="this.style.textDecoration='none'">${escapeHtml(extra.label)}: ${escapeHtml(extra.url)} &#8599;</a>`;
                html += `</div>`;
            }
        }
        html += `</div>`;

        // Credentials
        if (hasCredentials) {
            const credId = `tooldir_creds_${tool.id}`;
            html += `<div style="padding:8px 16px 12px;background:#f8f9fa;border-top:1px solid #f1f5f9;">`;
            html += `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">`;
            html += `<span style="font-size:0.78em;font-weight:600;color:#666;">Credentials</span>`;
            html += `<button onclick="toggleToolDirCreds('${credId}')" style="background:none;border:1px solid #d1d5db;border-radius:4px;padding:2px 8px;font-size:0.75em;cursor:pointer;color:#555;" id="${credId}_btn">Show</button>`;
            html += `</div>`;
            html += `<div id="${credId}" style="display:none;">`;

            for (const [key, val] of Object.entries(creds)) {
                const displayKey = key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
                html += `<div style="display:flex;align-items:center;gap:8px;margin-bottom:3px;">`;
                html += `<span style="font-size:0.8em;color:#888;min-width:70px;">${escapeHtml(displayKey)}</span>`;
                html += `<code style="font-size:0.82em;background:#fff;padding:2px 8px;border:1px solid #e5e7eb;border-radius:4px;word-break:break-all;flex:1;user-select:all;">${escapeHtml(val)}</code>`;
                html += `<button onclick="copyToolDirCred(this,'${escapeHtml(val).replace(/'/g, "\\'")}')" style="background:none;border:none;cursor:pointer;font-size:0.85em;padding:2px;" title="Copy">&#128203;</button>`;
                html += `</div>`;
            }

            html += `</div></div>`;
        } else {
            html += `<div style="padding:6px 16px 10px;background:#f8f9fa;border-top:1px solid #f1f5f9;">`;
            html += `<span style="font-size:0.78em;color:#aaa;">No authentication required</span>`;
            html += `</div>`;
        }

        html += `</div>`;
    }

    html += '</div>';
    content.innerHTML = html;
}

function _toolDirIcon(id) {
    const icons = {
        gitlab: '&#128230;', gitea: '&#9749;', jenkins: '&#128295;', sonarqube: '&#128737;',
        nexus: '&#128230;', vault: '&#128274;', chromadb: '&#128451;', grafana: '&#128200;',
        prometheus: '&#128293;', minio: '&#128190;', splunk: '&#128202;', jaeger: '&#128269;',
        cadvisor: '&#128202;', trivy: '&#128737;', ollama: '&#129302;', jira: '&#127915;',
        redmine: '&#128203;'
    };
    return icons[id] || '&#128736;';
}

function toggleToolDirCreds(credId) {
    const el = document.getElementById(credId);
    const btn = document.getElementById(credId + '_btn');
    if (el.style.display === 'none') {
        el.style.display = 'block';
        btn.textContent = 'Hide';
    } else {
        el.style.display = 'none';
        btn.textContent = 'Show';
    }
}

function copyToolDirCred(btn, value) {
    navigator.clipboard.writeText(value).then(() => {
        const orig = btn.innerHTML;
        btn.innerHTML = '&#9989;';
        setTimeout(() => btn.innerHTML = orig, 1200);
    });
}
