// ============= FOOTBOT CLIENT =============

class FootbotClient {
    constructor() {
        this.messagesContainer = document.getElementById('chatbot-messages');
        this.inputField = document.getElementById('chatbot-input');
        this.sendBtn = document.getElementById('send-btn');
        this.statusBadge = document.getElementById('connection-status');
        this.rasaUrl = '/webhooks/rest/webhook';
        this.senderId = this._getSessionId();
        this._isSending = false;

        this.setupEventListeners();
        this.checkConnection();
    }

    _getSessionId() {
        let id = localStorage.getItem('footbot_session_id');
        if (!id) {
            id = 'user_' + Math.random().toString(36).substring(2, 11) + '_' + Date.now();
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
            const resp = await fetch('/health', { method: 'GET', signal: AbortSignal.timeout(3000) });
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

    _setInputLocked(locked) {
        this._isSending = locked;
        this.sendBtn.disabled = locked;
        this.inputField.disabled = locked;
        this.sendBtn.style.opacity = locked ? '0.5' : '1';
    }

    async handleUserMessage() {
        if (this._isSending) return;
        const message = this.inputField.value.trim();
        if (!message) return;

        this.addMessage(message, 'user');
        this.inputField.value = '';
        this._setInputLocked(true);
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
        } finally {
            this._setInputLocked(false);
            this.inputField.focus();
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

    // -----------------------------------------------------------------------
    // Text rendering helpers
    // -----------------------------------------------------------------------

    /**
     * Render a bot message string as HTML.
     * Handles:
     *   **bold**  → <strong>
     *   \n        → <br>
     */
    _renderText(text) {
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>');
    }

    /**
     * Try to parse win-probability data from a prediction bot message.
     * Returns { homeLabel, drawLabel, awayLabel, homeVal, drawVal, awayVal }
     * or null if the message is not a prediction.
     */
    _parsePrediction(text) {
        if (!text.includes('Win Probabilities:')) return null;

        // Extract percentage lines: "  TeamName: **42.3%**"
        const pctRe = /([^\n:]+):\s*\*?\*?(\d+(?:\.\d+)?)%/g;
        const matches = [];
        let m;
        // Only scan inside the "Win Probabilities" block
        const block = text.split('Win Probabilities:')[1] || '';
        const blockEnd = block.indexOf('\n\n');
        const probBlock = blockEnd >= 0 ? block.substring(0, blockEnd) : block;
        while ((m = pctRe.exec(probBlock)) !== null) {
            matches.push({ label: m[1].trim(), value: parseFloat(m[2]) });
        }

        if (matches.length < 3) return null;
        return {
            homeLabel: matches[0].label,
            drawLabel: matches[1].label,
            awayLabel: matches[2].label,
            homeVal:   matches[0].value,
            drawVal:   matches[1].value,
            awayVal:   matches[2].value,
        };
    }

    // -----------------------------------------------------------------------
    // Message rendering
    // -----------------------------------------------------------------------

    addMessage(text, type = 'bot') {
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${type}-message`;

        const paragraph = document.createElement('p');

        if (type === 'bot') {
            paragraph.innerHTML = this._renderText(text);
        } else {
            // User messages: escape HTML only, no markdown
            paragraph.textContent = text;
        }

        messageDiv.appendChild(paragraph);

        // For prediction bot messages, append a probability chart
        if (type === 'bot') {
            const pred = this._parsePrediction(text);
            if (pred) {
                messageDiv.appendChild(this._buildProbChart(pred));
            }
        }

        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }

    /**
     * Build a Chart.js horizontal bar chart showing win probabilities.
     */
    _buildProbChart(pred) {
        const wrapper = document.createElement('div');
        wrapper.className = 'prob-chart-wrapper';

        const canvas = document.createElement('canvas');
        canvas.className = 'prob-chart';
        canvas.setAttribute('aria-label', 'Win probability chart');
        wrapper.appendChild(canvas);

        // Defer chart creation so the canvas is in the DOM
        requestAnimationFrame(() => {
            new Chart(canvas, {
                type: 'bar',
                data: {
                    labels: [pred.homeLabel, pred.drawLabel, pred.awayLabel],
                    datasets: [{
                        data: [pred.homeVal, pred.drawVal, pred.awayVal],
                        backgroundColor: ['#1565c0', '#546e7a', '#b71c1c'],
                        borderRadius: 6,
                        borderSkipped: false,
                    }]
                },
                options: {
                    indexAxis: 'y',
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: ctx => ` ${ctx.raw.toFixed(1)}%`
                            }
                        }
                    },
                    scales: {
                        x: {
                            min: 0,
                            max: 100,
                            grid: { color: 'rgba(255,255,255,0.07)' },
                            ticks: {
                                color: '#b0bec5',
                                callback: v => v + '%',
                                font: { size: 11 }
                            }
                        },
                        y: {
                            grid: { display: false },
                            ticks: {
                                color: '#e0e0e0',
                                font: { size: 12, weight: 'bold' },
                                maxRotation: 0
                            }
                        }
                    }
                }
            });
        });

        return wrapper;
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
