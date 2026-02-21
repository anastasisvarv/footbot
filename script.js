// ============= FOOTBOT CLIENT =============

class FootbotClient {
    constructor() {
        this.messagesContainer = document.getElementById('chatbot-messages');
        this.inputField = document.getElementById('chatbot-input');
        this.sendBtn = document.getElementById('send-btn');
        this.statusBadge = document.getElementById('connection-status');
        this.rasaUrl = 'http://localhost:5005/webhooks/rest/webhook';
        this.senderId = this._getSessionId();

        this.setupEventListeners();
        this.checkConnection();
    }

    _getSessionId() {
        let id = localStorage.getItem('footbot_session_id');
        if (!id) {
            id = 'user_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
            localStorage.setItem('footbot_session_id', id);
        }
        return id;
    }

    setupEventListeners() {
        this.sendBtn.addEventListener('click', () => this.handleUserMessage());
        this.inputField.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.handleUserMessage();
        });

        // League click shortcuts
        document.querySelectorAll('.league-item[data-query]').forEach(item => {
            item.addEventListener('click', () => {
                const query = item.dataset.query;
                this.inputField.value = query;
                this.inputField.focus();
                this.handleUserMessage();
            });
        });

        // Quick query badges
        document.querySelectorAll('.season-badge[data-query]').forEach(badge => {
            badge.addEventListener('click', () => {
                const query = badge.dataset.query;
                this.inputField.value = query;
                this.inputField.focus();
                this.handleUserMessage();
            });
        });
    }

    async checkConnection() {
        this._setStatus('checking', 'Connecting...');
        try {
            const resp = await fetch('http://localhost:5005/', { method: 'GET', signal: AbortSignal.timeout(3000) });
            if (resp.ok || resp.status === 404) {
                this._setStatus('connected', 'Live');
            } else {
                this._setStatus('error', 'Error');
            }
        } catch {
            this._setStatus('offline', 'Offline');
        }
    }

    _setStatus(state, label) {
        this.statusBadge.textContent = label;
        this.statusBadge.className = 'status-badge';
        if (state === 'connected') this.statusBadge.classList.add('status-connected');
        else if (state === 'offline') this.statusBadge.classList.add('status-offline');
        else if (state === 'error') this.statusBadge.classList.add('status-error');
        else this.statusBadge.classList.add('status-checking');
    }

    async handleUserMessage() {
        const message = this.inputField.value.trim();
        if (!message) return;

        this.addMessage(message, 'user');
        this.inputField.value = '';

        this.showTypingIndicator();

        try {
            const responses = await this._sendToRasa(message);
            this.removeTypingIndicator();

            if (responses && responses.length > 0) {
                responses.forEach(r => {
                    if (r.text) this.addMessage(r.text, 'bot');
                });
            } else {
                this.addMessage("I didn't get a response. Is the Rasa server running? Try: ./start.sh", 'bot');
            }
        } catch (err) {
            this.removeTypingIndicator();
            this._setStatus('offline', 'Offline');
            this.addMessage(
                "⚠️ Cannot reach the Rasa server.\n\nTo start it, run:\n  ./start.sh\n\nOr manually:\n  cd rasa && rasa run --enable-api --cors \"*\" &\n  rasa run actions &",
                'bot'
            );
        }

        this.scrollToBottom();
    }

    async _sendToRasa(message) {
        const resp = await fetch(this.rasaUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sender: this.senderId, message }),
            signal: AbortSignal.timeout(15000)
        });

        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return resp.json();
    }

    addMessage(text, type = 'bot') {
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${type}-message`;

        const paragraph = document.createElement('p');
        // Render newlines as <br> for multi-line bot responses
        paragraph.innerHTML = text.replace(/\n/g, '<br>');

        messageDiv.appendChild(paragraph);
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }

    showTypingIndicator() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message bot-message';
        messageDiv.id = 'typing-indicator';
        messageDiv.innerHTML = `
            <div class="typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        `;
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }

    removeTypingIndicator() {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) indicator.remove();
    }

    scrollToBottom() {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }
}

window.addEventListener('load', () => {
    new FootbotClient();
    console.log('⚽ Footbot Client initialized — connecting to Rasa...');
});
