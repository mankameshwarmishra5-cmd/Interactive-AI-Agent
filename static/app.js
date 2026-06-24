// ============================================================
//  Interactive Agent — Frontend App Logic  (v2.0)
//  Phase 7: Multi-state badges, toasts, streaming, stats,
//            char counter, error notifications.
// ============================================================

const SESSION_ID = `session_${Date.now()}`;

// ── DOM references ──────────────────────────────────────────
const chatForm          = document.getElementById('chat-form');
const userInput         = document.getElementById('user-message-input');
const messagesContainer = document.getElementById('messages-container');
const sendButton        = document.getElementById('send-button');
const typingIndicator   = document.getElementById('typing-indicator');
const clearChatBtn      = document.getElementById('clear-chat-btn');
const toastContainer    = document.getElementById('toast-container');
const charCounter       = document.getElementById('char-counter');
const streamToggle      = document.getElementById('stream-toggle');

// Status DOM
const sdkStatus     = document.getElementById('sdk-status');
const keyStatus     = document.getElementById('key-status');
const engineStatus  = document.getElementById('engine-status');
const engineBadge   = document.getElementById('engine-badge');
const badgeText     = document.getElementById('badge-text');
const agentSubtitle = document.getElementById('agent-subtitle');

// Stats DOM
const statMessages = document.getElementById('stat-messages');
const statSessions = document.getElementById('stat-sessions');
const statUptime   = document.getElementById('stat-uptime');

// Internal state
let messageCount    = 0;
let welcomeRemoved  = false;

// ──────────────────────────────────────────────────────────
//  Toast notifications  (Phase 7)
// ──────────────────────────────────────────────────────────
/**
 * Shows a temporary toast notification.
 * @param {string} message  — Text to display.
 * @param {'info'|'success'|'warning'|'error'} type — Visual variant.
 * @param {number} duration — Auto-dismiss ms (0 = persistent).
 */
function showToast(message, type = 'info', duration = 4000) {
    const icons = {
        info:    'fa-circle-info',
        success: 'fa-circle-check',
        warning: 'fa-triangle-exclamation',
        error:   'fa-circle-xmark',
    };
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <i class="fa-solid ${icons[type] || icons.info}"></i>
        <span>${message}</span>
        <button class="toast-close" aria-label="Dismiss">&times;</button>
    `;
    toast.querySelector('.toast-close').addEventListener('click', () => toast.remove());
    toastContainer.appendChild(toast);

    // Trigger entrance animation
    requestAnimationFrame(() => toast.classList.add('toast-visible'));

    if (duration > 0) {
        setTimeout(() => {
            toast.classList.remove('toast-visible');
            setTimeout(() => toast.remove(), 400);
        }, duration);
    }
}

// ──────────────────────────────────────────────────────────
//  Status Panel  (Phase 7 — multi-state badges)
// ──────────────────────────────────────────────────────────
const STATUS_CONFIG = {
    live: {
        badge:    'live',
        label:    'LIVE MODE',
        color:    'hsl(145, 80%, 50%)',
        subtitle: 'Powered by Gemini 2.5 Flash · Connected',
        icon:     'fa-bolt',
    },
    fallback: {
        badge:    'fallback',
        label:    'FALLBACK',
        color:    'hsl(38, 92%, 50%)',
        subtitle: 'Gemini unavailable · Using simulation fallback',
        icon:     'fa-rotate-left',
    },
    quota_exceeded: {
        badge:    'quota',
        label:    'QUOTA EXCEEDED',
        color:    'hsl(0, 84%, 60%)',
        subtitle: 'Gemini quota exhausted · Simulation active',
        icon:     'fa-ban',
    },
    api_key_missing: {
        badge:    'key-missing',
        label:    'NO API KEY',
        color:    'hsl(38, 92%, 50%)',
        subtitle: 'API key missing · Add GEMINI_API_KEY to .env',
        icon:     'fa-key',
    },
    sdk_missing: {
        badge:    'sdk-missing',
        label:    'SDK MISSING',
        color:    'hsl(220, 10%, 55%)',
        subtitle: 'google-genai not installed · Run pip install google-genai',
        icon:     'fa-plug-circle-xmark',
    },
    initializing: {
        badge:    '',
        label:    'STANDBY',
        color:    'hsl(220, 10%, 55%)',
        subtitle: 'Initializing connection...',
        icon:     'fa-bolt',
    },
};

async function fetchStatus() {
    try {
        const res  = await fetch(`/api/status?session_id=${SESSION_ID}`);
        const data = await res.json();

        // SDK status
        sdkStatus.innerHTML = data.genai_installed
            ? '<span class="pulse-indicator pulse-green"></span> Installed'
            : '<span class="pulse-indicator pulse-orange"></span> Not Installed';

        // API key status
        keyStatus.innerHTML = data.api_key_configured
            ? '<span class="pulse-indicator pulse-green"></span> Configured'
            : '<span class="pulse-indicator pulse-orange"></span> Missing';

        // Engine / mode
        const cfg = STATUS_CONFIG[data.gemini_status] || STATUS_CONFIG.initializing;

        engineStatus.textContent = data.gemini_status.replace(/_/g, ' ').toUpperCase();
        engineStatus.style.color = cfg.color;

        engineBadge.className   = `engine-badge ${cfg.badge}`;
        const iconEl = engineBadge.querySelector('i');
        if (iconEl) iconEl.className = `fa-solid ${cfg.icon}`;
        badgeText.textContent   = cfg.label;
        agentSubtitle.textContent = cfg.subtitle;

        // Show one-time toast on quota / key error
        if (data.gemini_status === 'quota_exceeded') {
            showToast('Gemini quota exhausted — switched to simulation mode.', 'warning', 6000);
        } else if (data.gemini_status === 'api_key_missing') {
            showToast('Gemini API key missing or invalid. Check your .env file.', 'error', 0);
        }

    } catch (err) {
        sdkStatus.innerHTML     = '<span class="pulse-indicator pulse-gray"></span> Error';
        keyStatus.innerHTML     = '<span class="pulse-indicator pulse-gray"></span> Error';
        engineStatus.textContent = 'Offline';
        agentSubtitle.textContent = 'Cannot connect to backend server';
        showToast('Cannot reach backend server. Is main.py running?', 'error', 0);
        console.error('Status fetch failed:', err);
    }
}

// ──────────────────────────────────────────────────────────
//  Metrics (Phase 7 — session stats sidebar)
// ──────────────────────────────────────────────────────────
async function fetchMetrics() {
    try {
        const res  = await fetch('/api/metrics');
        const data = await res.json();

        if (statSessions) statSessions.textContent = data.active_sessions;

        const upSec = Math.floor(data.uptime_seconds);
        const h = Math.floor(upSec / 3600);
        const m = Math.floor((upSec % 3600) / 60);
        const s = upSec % 60;
        if (statUptime) {
            statUptime.textContent = h > 0
                ? `${h}h ${m}m`
                : m > 0 ? `${m}m ${s}s` : `${s}s`;
        }
    } catch (_) {
        // Metrics are non-critical; fail silently
    }
}

// ──────────────────────────────────────────────────────────
//  Message Rendering
// ──────────────────────────────────────────────────────────
function removeWelcome() {
    if (!welcomeRemoved) {
        const welcome = document.getElementById('welcome-message');
        if (welcome) welcome.remove();
        welcomeRemoved = true;
    }
}

function renderMessage(text, role) {
    removeWelcome();
    const wrapper = document.createElement('div');
    wrapper.classList.add('message-wrapper', role);

    const bubble = document.createElement('div');
    bubble.classList.add('message-bubble');

    if (role === 'agent') {
        bubble.innerHTML = marked.parse(text);
    } else {
        bubble.textContent = text;
    }

    wrapper.appendChild(bubble);
    messagesContainer.appendChild(wrapper);
    scrollToBottom();
    return bubble;  // Return for streaming updates
}

/**
 * Creates an empty agent bubble that can be updated incrementally (streaming).
 * Returns the bubble element.
 */
function createStreamBubble() {
    removeWelcome();
    const wrapper = document.createElement('div');
    wrapper.classList.add('message-wrapper', 'agent');

    const bubble = document.createElement('div');
    bubble.classList.add('message-bubble', 'streaming');
    bubble.innerHTML = '<span class="stream-cursor">▍</span>';

    wrapper.appendChild(bubble);
    messagesContainer.appendChild(wrapper);
    scrollToBottom();
    return bubble;
}

function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// ──────────────────────────────────────────────────────────
//  Typing Indicator
// ──────────────────────────────────────────────────────────
function showTyping() {
    typingIndicator.style.display = 'flex';
    scrollToBottom();
}

function hideTyping() {
    typingIndicator.style.display = 'none';
}

// ──────────────────────────────────────────────────────────
//  Standard (non-streaming) Send
// ──────────────────────────────────────────────────────────
async function sendMessage(message) {
    setInputDisabled(true);
    showTyping();

    try {
        const res = await fetch('/api/chat', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ message, session_id: SESSION_ID }),
        });

        hideTyping();

        if (res.status === 429) {
            showToast('Rate limit reached (30 msg/min). Please slow down.', 'warning');
            renderMessage('⚠️ **Rate limit reached.** Please wait a moment before sending another message.', 'agent');
            return;
        }

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
            throw new Error(err.detail || `HTTP ${res.status}`);
        }

        const data = await res.json();
        renderMessage(data.response, 'agent');

        // Update badge if status changed (e.g. quota just hit)
        updateBadge(data.gemini_status);
        incrementMessageCount();

    } catch (err) {
        hideTyping();
        renderMessage(
            `### ⚠️ Connection Error\n\nCould not reach the backend.\n\n\`\`\`\n${err.message}\n\`\`\`\n\nMake sure the server is running: \`python main.py\``,
            'agent'
        );
        showToast(`Error: ${err.message}`, 'error');
        console.error('Chat API error:', err);
    } finally {
        setInputDisabled(false);
        userInput.focus();
    }
}

// ──────────────────────────────────────────────────────────
//  Streaming Send  (Phase 4 — SSE)
// ──────────────────────────────────────────────────────────
async function sendMessageStreaming(message) {
    setInputDisabled(true);
    showTyping();

    const params = new URLSearchParams({ message, session_id: SESSION_ID });
    const url    = `/api/chat/stream?${params}`;

    const bubble  = createStreamBubble();
    let   rawText = '';
    let   started = false;

    try {
        const res = await fetch(url);

        if (res.status === 429) {
            hideTyping();
            bubble.innerHTML = marked.parse('⚠️ **Rate limit reached.** Please wait a moment.');
            bubble.classList.remove('streaming');
            showToast('Rate limit (30 msg/min). Please slow down.', 'warning');
            return;
        }

        if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
        }

        hideTyping();
        started = true;

        const reader  = res.body.getReader();
        const decoder = new TextDecoder();
        let   buffer  = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete line in buffer

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                const payload = line.slice(6);

                if (payload === '[DONE]') {
                    // Finalize — render full markdown
                    bubble.innerHTML = marked.parse(rawText);
                    bubble.classList.remove('streaming');
                    incrementMessageCount();
                    continue;
                }
                if (payload.startsWith('STATUS:')) {
                    updateBadge(payload.slice(7));
                    continue;
                }
                if (payload.startsWith('ERROR:')) {
                    bubble.innerHTML = marked.parse(`⚠️ **Error:** ${payload.slice(6)}`);
                    bubble.classList.remove('streaming');
                    showToast(payload.slice(6), 'error');
                    continue;
                }

                // Accumulate word chunks
                rawText += payload.replace(/\\n/g, '\n');
                // Live preview with cursor
                bubble.innerHTML = marked.parse(rawText) + '<span class="stream-cursor">▍</span>';
                scrollToBottom();
            }
        }

    } catch (err) {
        if (!started) hideTyping();
        bubble.innerHTML = marked.parse(
            `### ⚠️ Stream Error\n\nFell back — \`${err.message}\``
        );
        bubble.classList.remove('streaming');
        showToast(`Stream error: ${err.message}`, 'error');
        console.error('Stream error:', err);
    } finally {
        setInputDisabled(false);
        userInput.focus();
    }
}

// ──────────────────────────────────────────────────────────
//  Badge update helper
// ──────────────────────────────────────────────────────────
function updateBadge(geminiStatus) {
    const cfg = STATUS_CONFIG[geminiStatus];
    if (!cfg) return;
    engineBadge.className = `engine-badge ${cfg.badge}`;
    const iconEl = engineBadge.querySelector('i');
    if (iconEl) iconEl.className = `fa-solid ${cfg.icon}`;
    badgeText.textContent     = cfg.label;
    agentSubtitle.textContent = cfg.subtitle;
    engineStatus.textContent  = geminiStatus.replace(/_/g, ' ').toUpperCase();
    engineStatus.style.color  = cfg.color;
}

// ──────────────────────────────────────────────────────────
//  Clear Chat
// ──────────────────────────────────────────────────────────
async function clearChat() {
    try {
        await fetch('/api/clear', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ session_id: SESSION_ID }),
        });
    } catch (err) {
        console.warn('Clear API call failed:', err);
    }

    messageCount    = 0;
    welcomeRemoved  = false;
    if (statMessages) statMessages.textContent = '0';

    messagesContainer.innerHTML = '';
    const welcomeDiv = document.createElement('div');
    welcomeDiv.className = 'welcome-message-wrapper';
    welcomeDiv.id        = 'welcome-message';
    welcomeDiv.innerHTML = `
        <div class="welcome-card">
            <i class="fa-solid fa-bolt-lightning welcome-icon"></i>
            <h2>Ready for Interaction</h2>
            <p>I am a Python-based interactive agent powered by Gemini 2.5 Flash. Ask me anything, request code, use tools, or just chat!</p>
            <div class="suggestions">
                <button class="suggest-btn" id="sug-status" data-text="What is your current configuration status?">
                    <i class="fa-solid fa-circle-nodes"></i> Check System Status
                </button>
                <button class="suggest-btn" id="sug-code" data-text="Give me a Python code template showing how to write a function">
                    <i class="fa-brands fa-python"></i> Python Template
                </button>
                <button class="suggest-btn" id="sug-time" data-text="What is the current time and date?">
                    <i class="fa-solid fa-clock"></i> Current Time
                </button>
                <button class="suggest-btn" id="sug-joke" data-text="Tell me a developer joke">
                    <i class="fa-solid fa-face-laugh-beam"></i> Tell a Joke
                </button>
            </div>
        </div>
    `;
    messagesContainer.appendChild(welcomeDiv);
    bindSuggestions();
    showToast('Chat history cleared.', 'success', 2500);
}

// ──────────────────────────────────────────────────────────
//  Helper Utilities
// ──────────────────────────────────────────────────────────
function setInputDisabled(disabled) {
    userInput.disabled         = disabled;
    sendButton.disabled        = disabled;
    sendButton.style.opacity   = disabled ? '0.5' : '1';
}

function incrementMessageCount() {
    messageCount++;
    if (statMessages) statMessages.textContent = messageCount;
}

// ──────────────────────────────────────────────────────────
//  Suggestion Buttons
// ──────────────────────────────────────────────────────────
function bindSuggestions() {
    document.querySelectorAll('.suggest-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const text = btn.getAttribute('data-text');
            if (!text) return;
            renderMessage(text, 'user');
            const useStream = streamToggle && streamToggle.checked;
            useStream ? sendMessageStreaming(text) : sendMessage(text);
        });
    });
}

// ──────────────────────────────────────────────────────────
//  Character Counter
// ──────────────────────────────────────────────────────────
if (userInput && charCounter) {
    userInput.addEventListener('input', () => {
        const len = userInput.value.length;
        charCounter.textContent = `${len} / 4000`;
        charCounter.style.color = len > 3800
            ? 'hsl(0, 84%, 60%)'
            : len > 3000
                ? 'hsl(38, 92%, 50%)'
                : '';
    });
}

// ──────────────────────────────────────────────────────────
//  Event Listeners
// ──────────────────────────────────────────────────────────
chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const message = userInput.value.trim();
    if (!message) return;
    userInput.value = '';
    if (charCounter) charCounter.textContent = '0 / 4000';
    renderMessage(message, 'user');
    const useStream = streamToggle && streamToggle.checked;
    useStream ? sendMessageStreaming(message) : sendMessage(message);
});

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        chatForm.dispatchEvent(new Event('submit'));
    }
});

clearChatBtn.addEventListener('click', () => {
    if (confirm('Clear entire chat history?')) clearChat();
});

// ──────────────────────────────────────────────────────────
//  Initialise on page load
// ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    fetchStatus();
    fetchMetrics();
    bindSuggestions();
    userInput.focus();

    // Refresh metrics every 30 seconds
    setInterval(fetchMetrics, 30_000);
    // Re-check status every 60 seconds (catches quota recovery)
    setInterval(fetchStatus, 60_000);
});
