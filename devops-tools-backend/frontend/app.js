/**
 * AI DevOps Pipeline Generator - Frontend Application
 */

// Configuration
const API_BASE_URL = window.location.origin;
let conversationId = null;
let isLoading = false;

// DOM Elements
const messagesContainer = document.getElementById('messages');
const messageInput = document.getElementById('messageInput');
const sendButton = document.getElementById('sendButton');
const connectionStatus = document.getElementById('connectionStatus');
const conversationIdElement = document.getElementById('conversationId');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
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

    // Handle Enter key
    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Check API health
    checkApiHealth();
});

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
    connectionStatus.className = `status ${status}`;
    connectionStatus.textContent = text;
}

/**
 * Send a message to the chat API
 */
async function sendMessage() {
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
        conversationIdElement.textContent = `Session: ${conversationId.substring(0, 8)}...`;

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
    sendButton.disabled = loading;

    const buttonText = sendButton.querySelector('.button-text');
    const buttonLoading = sendButton.querySelector('.button-loading');

    if (loading) {
        buttonText.style.display = 'none';
        buttonLoading.style.display = 'inline-flex';
        setConnectionStatus('loading', 'Processing...');
    } else {
        buttonText.style.display = 'inline';
        buttonLoading.style.display = 'none';
        setConnectionStatus('connected', 'Connected');
    }
}

/**
 * Scroll chat to bottom
 */
function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

/**
 * Start a new conversation
 */
async function newConversation() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/v1/chat/new`, {
            method: 'POST'
        });

        if (response.ok) {
            const data = await response.json();
            conversationId = data.conversation_id;
            conversationIdElement.textContent = `Session: ${conversationId.substring(0, 8)}...`;

            // Clear messages (keep welcome message)
            messagesContainer.innerHTML = `
                <div class="message assistant">
                    <div class="message-content">
                        <p>Hello! I'm your AI DevOps assistant. I can help you generate CI/CD pipelines for your GitLab repositories.</p>
                        <p>Just provide me with a GitLab repository URL and I'll analyze it and create appropriate Dockerfile and .gitlab-ci.yml files for you.</p>
                        <p><strong>Example:</strong> "Generate a pipeline for http://gitlab-server/root/golang-sample-app"</p>
                    </div>
                </div>
            `;
        }
    } catch (error) {
        console.error('Error creating new conversation:', error);
    }
}
