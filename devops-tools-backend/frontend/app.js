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
    'github-actions': {
        name: 'GitHub Actions Generator',
        icon: '🐙',
        endpoint: '/api/v1/github-pipeline/',
        welcomeMessage: `Hello! I'm your AI DevOps assistant for GitHub Actions (via Gitea).

I can help you generate CI/CD workflows for your Gitea repositories with GitHub Actions-compatible syntax.

Just provide me with a Gitea repository URL and I'll analyze it and create appropriate Dockerfile and .github/workflows/ci.yml files for you.

**Example:** "Generate a workflow for http://gitea-server:3000/admin/java-test-project"`
    },
    'connectivity-validator': {
        name: 'Tool Connectivity Validator',
        icon: '🔗',
        viewType: 'connectivity'
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

    // Show dashboard, hide tool view and connectivity view
    document.getElementById('dashboardView').classList.remove('hidden');
    document.getElementById('toolView').classList.add('hidden');
    document.getElementById('connectivityView').classList.add('hidden');

    currentTool = null;
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

    // Update tool header
    document.getElementById('toolIcon').textContent = config.icon;
    document.getElementById('toolName').textContent = config.name;

    // Reset chat with welcome message
    resetChat(config.welcomeMessage);

    // Hide dashboard, show tool view
    document.getElementById('dashboardView').classList.add('hidden');
    document.getElementById('toolView').classList.remove('hidden');
    document.getElementById('connectivityView').classList.add('hidden');

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
        const response = await fetch(`${API_BASE_URL}/api/v1/chat/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: message,
                conversation_id: conversationId
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
        if (data.monitoring && data.monitoring.project_id && data.monitoring.branch) {
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
        const response = await fetch(
            `${API_BASE_URL}/api/v1/pipeline/progress/${projectId}/${encodeURIComponent(branch)}`
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
// Connectivity Validator
// ============================================================================

function openConnectivityView() {
    document.getElementById('dashboardView').classList.add('hidden');
    document.getElementById('toolView').classList.add('hidden');
    document.getElementById('connectivityView').classList.remove('hidden');
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

function buildProgressHTML(data) {
    const icons = {
        'monitoring': '&#9203;',
        'pipeline_running': '&#9654;&#65039;',
        'pipeline_failed': '&#10060;',
        'fixing': '&#128295;',
        'fix_committed': '&#128296;',
        'success': '&#9989;',
        'failed': '&#10060;'
    };
    const colors = {
        'monitoring': '#f59e0b',
        'pipeline_running': '#3b82f6',
        'pipeline_failed': '#ef4444',
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
    html += `<p style="margin:0 0 4px 0;">${data.current_message}</p>`;

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
            html += `<div style="padding:2px 0;"><code style="color:#999;">${e.timestamp}</code> ${eIcon} ${e.message}</div>`;
        }
        html += '</div></details>';
    }

    if (!data.completed) {
        html += '<p style="font-size:0.8em;color:#999;margin:6px 0 0 0;">Auto-updating every 10s...</p>';
    }

    html += '</div>';
    return html;
}
