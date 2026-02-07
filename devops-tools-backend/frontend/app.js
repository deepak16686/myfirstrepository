/**
 * AI Platform - DevOps & Infrastructure Frontend Application
 */

// Configuration
const API_BASE_URL = window.location.origin;
let conversationId = null;
let isLoading = false;
let currentCategory = 'devops';
let currentTool = null;

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

    // Show dashboard, hide tool view
    document.getElementById('dashboardView').classList.remove('hidden');
    document.getElementById('toolView').classList.add('hidden');

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

    // Update tool header
    document.getElementById('toolIcon').textContent = config.icon;
    document.getElementById('toolName').textContent = config.name;

    // Reset chat with welcome message
    resetChat(config.welcomeMessage);

    // Hide dashboard, show tool view
    document.getElementById('dashboardView').classList.add('hidden');
    document.getElementById('toolView').classList.remove('hidden');

    // Focus on input
    if (messageInput) {
        messageInput.focus();
    }
}

/**
 * Go back to dashboard
 */
function goBack() {
    showCategory(currentCategory);
}

/**
 * Reset chat with a welcome message
 */
function resetChat(welcomeMessage) {
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
