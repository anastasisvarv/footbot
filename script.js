// ============= CHATBOT LOGIC =============

class FootbotAI {
    constructor() {
        this.messagesContainer = document.getElementById('chatbot-messages');
        this.inputField = document.getElementById('chatbot-input');
        this.sendBtn = document.getElementById('send-btn');
        
        this.setupEventListeners();
        this.teamDatabase = this.initializeTeamData();
    }

    setupEventListeners() {
        // Main chat handlers
        this.sendBtn.addEventListener('click', () => this.handleUserMessage());
        this.inputField.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.handleUserMessage();
        });

        // Quick prediction buttons
        document.querySelectorAll('.quick-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const prediction = btn.dataset.prediction;
                this.inputField.value = prediction;
                this.inputField.focus();
                this.handleUserMessage();
            });
        });

        // Query buttons
        document.querySelectorAll('.query-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const query = btn.dataset.query;
                this.inputField.value = query;
                this.inputField.focus();
                this.handleUserMessage();
            });
        });
    }

    handleUserMessage() {
        const message = this.inputField.value.trim();
        if (!message) return;

        // Add user message to chat
        this.addMessage(message, 'user');
        this.inputField.value = '';

        // Show typing indicator
        this.showTypingIndicator();

        // Simulate processing time and get response
        setTimeout(() => {
            this.removeTypingIndicator();
            const response = this.generateResponse(message);
            this.addMessage(response.text, response.type);

            // Auto-scroll to bottom
            this.scrollToBottom();
        }, 800 + Math.random() * 700);
    }

    addMessage(text, type = 'bot') {
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${type}-message`;
        
        const paragraph = document.createElement('p');
        paragraph.textContent = text;
        
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

    initializeTeamData() {
        return {
            // PREMIER LEAGUE (England)
            'manchester city': { 
                seasons: { 
                    '2023-24': { strength: 92, form: 9, injury: 0 },
                    '2024-25': { strength: 91, form: 8, injury: 1 },
                    '2025-26': { strength: 92, form: 9, injury: 0 }
                }
            },
            'liverpool': { 
                seasons: { 
                    '2023-24': { strength: 88, form: 8, injury: 1 },
                    '2024-25': { strength: 89, form: 8, injury: 0 },
                    '2025-26': { strength: 90, form: 9, injury: 0 }
                }
            },
            'arsenal': { 
                seasons: { 
                    '2023-24': { strength: 84, form: 7, injury: 2 },
                    '2024-25': { strength: 86, form: 8, injury: 1 },
                    '2025-26': { strength: 87, form: 8, injury: 1 }
                }
            },
            'manchester united': { 
                seasons: { 
                    '2023-24': { strength: 85, form: 7, injury: 2 },
                    '2024-25': { strength: 84, form: 6, injury: 3 },
                    '2025-26': { strength: 85, form: 7, injury: 2 }
                }
            },
            'chelsea': { 
                seasons: { 
                    '2023-24': { strength: 82, form: 6, injury: 3 },
                    '2024-25': { strength: 83, form: 7, injury: 2 },
                    '2025-26': { strength: 84, form: 7, injury: 2 }
                }
            },
            'tottenham': { 
                seasons: { 
                    '2023-24': { strength: 80, form: 5, injury: 4 },
                    '2024-25': { strength: 82, form: 6, injury: 2 },
                    '2025-26': { strength: 83, form: 7, injury: 2 }
                }
            },
            'aston villa': { 
                seasons: { 
                    '2023-24': { strength: 78, form: 6, injury: 2 },
                    '2024-25': { strength: 80, form: 7, injury: 1 },
                    '2025-26': { strength: 81, form: 7, injury: 1 }
                }
            },
            'newcastle': { 
                seasons: { 
                    '2023-24': { strength: 76, form: 5, injury: 3 },
                    '2024-25': { strength: 78, form: 6, injury: 2 },
                    '2025-26': { strength: 79, form: 6, injury: 2 }
                }
            },
            'brighton': { 
                seasons: { 
                    '2023-24': { strength: 75, form: 5, injury: 2 },
                    '2024-25': { strength: 76, form: 5, injury: 2 },
                    '2025-26': { strength: 77, form: 6, injury: 1 }
                }
            },
            'west ham': { 
                seasons: { 
                    '2023-24': { strength: 73, form: 4, injury: 3 },
                    '2024-25': { strength: 74, form: 5, injury: 2 },
                    '2025-26': { strength: 75, form: 5, injury: 2 }
                }
            },

            // LA LIGA (Spain)
            'real madrid': { 
                seasons: { 
                    '2023-24': { strength: 90, form: 8, injury: 1 },
                    '2024-25': { strength: 91, form: 9, injury: 0 },
                    '2025-26': { strength: 92, form: 9, injury: 0 }
                }
            },
            'barcelona': { 
                seasons: { 
                    '2023-24': { strength: 86, form: 7, injury: 2 },
                    '2024-25': { strength: 87, form: 8, injury: 1 },
                    '2025-26': { strength: 88, form: 8, injury: 1 }
                }
            },
            'atletico madrid': { 
                seasons: { 
                    '2023-24': { strength: 84, form: 6, injury: 3 },
                    '2024-25': { strength: 85, form: 7, injury: 2 },
                    '2025-26': { strength: 86, form: 7, injury: 2 }
                }
            },
            'sevilla': { 
                seasons: { 
                    '2023-24': { strength: 77, form: 5, injury: 3 },
                    '2024-25': { strength: 78, form: 6, injury: 2 },
                    '2025-26': { strength: 79, form: 6, injury: 2 }
                }
            },
            'real betis': { 
                seasons: { 
                    '2023-24': { strength: 75, form: 5, injury: 2 },
                    '2024-25': { strength: 76, form: 5, injury: 2 },
                    '2025-26': { strength: 77, form: 6, injury: 1 }
                }
            },
            'valencia': { 
                seasons: { 
                    '2023-24': { strength: 74, form: 4, injury: 4 },
                    '2024-25': { strength: 75, form: 5, injury: 3 },
                    '2025-26': { strength: 76, form: 5, injury: 2 }
                }
            },

            // SERIE A (Italy)
            'inter': { 
                seasons: { 
                    '2023-24': { strength: 88, form: 8, injury: 1 },
                    '2024-25': { strength: 89, form: 8, injury: 1 },
                    '2025-26': { strength: 90, form: 9, injury: 0 }
                }
            },
            'juventus': { 
                seasons: { 
                    '2023-24': { strength: 85, form: 6, injury: 3 },
                    '2024-25': { strength: 86, form: 7, injury: 2 },
                    '2025-26': { strength: 87, form: 8, injury: 1 }
                }
            },
            'ac milan': { 
                seasons: { 
                    '2023-24': { strength: 84, form: 7, injury: 2 },
                    '2024-25': { strength: 85, form: 7, injury: 2 },
                    '2025-26': { strength: 86, form: 8, injury: 1 }
                }
            },
            'napoli': { 
                seasons: { 
                    '2023-24': { strength: 82, form: 6, injury: 2 },
                    '2024-25': { strength: 83, form: 6, injury: 2 },
                    '2025-26': { strength: 84, form: 7, injury: 2 }
                }
            },
            'lazio': { 
                seasons: { 
                    '2023-24': { strength: 78, form: 6, injury: 2 },
                    '2024-25': { strength: 79, form: 6, injury: 2 },
                    '2025-26': { strength: 80, form: 7, injury: 1 }
                }
            },
            'roma': { 
                seasons: { 
                    '2023-24': { strength: 76, form: 5, injury: 3 },
                    '2024-25': { strength: 77, form: 5, injury: 3 },
                    '2025-26': { strength: 78, form: 6, injury: 2 }
                }
            },

            // BUNDESLIGA (Germany)
            'bayern munich': { 
                seasons: { 
                    '2023-24': { strength: 89, form: 8, injury: 1 },
                    '2024-25': { strength: 90, form: 9, injury: 0 },
                    '2025-26': { strength: 91, form: 9, injury: 0 }
                }
            },
            'borussia dortmund': { 
                seasons: { 
                    '2023-24': { strength: 85, form: 7, injury: 2 },
                    '2024-25': { strength: 86, form: 7, injury: 2 },
                    '2025-26': { strength: 87, form: 8, injury: 1 }
                }
            },
            'leverkusen': { 
                seasons: { 
                    '2023-24': { strength: 83, form: 8, injury: 1 },
                    '2024-25': { strength: 84, form: 8, injury: 1 },
                    '2025-26': { strength: 85, form: 8, injury: 1 }
                }
            },
            'vfl wolfsburg': { 
                seasons: { 
                    '2023-24': { strength: 76, form: 5, injury: 3 },
                    '2024-25': { strength: 77, form: 6, injury: 2 },
                    '2025-26': { strength: 78, form: 6, injury: 2 }
                }
            },
            'rb leipzig': { 
                seasons: { 
                    '2023-24': { strength: 78, form: 6, injury: 2 },
                    '2024-25': { strength: 79, form: 6, injury: 2 },
                    '2025-26': { strength: 80, form: 7, injury: 1 }
                }
            },

            // LIGUE 1 (France)
            'paris saint-germain': { 
                seasons: { 
                    '2023-24': { strength: 87, form: 7, injury: 2 },
                    '2024-25': { strength: 88, form: 8, injury: 1 },
                    '2025-26': { strength: 89, form: 8, injury: 1 }
                }
            },
            'marseille': { 
                seasons: { 
                    '2023-24': { strength: 79, form: 6, injury: 2 },
                    '2024-25': { strength: 80, form: 6, injury: 2 },
                    '2025-26': { strength: 81, form: 7, injury: 1 }
                }
            },
            'lyon': { 
                seasons: { 
                    '2023-24': { strength: 77, form: 5, injury: 3 },
                    '2024-25': { strength: 78, form: 6, injury: 2 },
                    '2025-26': { strength: 79, form: 6, injury: 2 }
                }
            },
            'monaco': { 
                seasons: { 
                    '2023-24': { strength: 76, form: 5, injury: 3 },
                    '2024-25': { strength: 77, form: 5, injury: 2 },
                    '2025-26': { strength: 78, form: 6, injury: 2 }
                }
            },
            'nice': { 
                seasons: { 
                    '2023-24': { strength: 74, form: 4, injury: 4 },
                    '2024-25': { strength: 75, form: 5, injury: 3 },
                    '2025-26': { strength: 76, form: 5, injury: 2 }
                }
            },

            // SUPER LEAGUE (Greece)
            'olympiacos': { 
                seasons: { 
                    '2023-24': { strength: 85, form: 8, injury: 1 },
                    '2024-25': { strength: 86, form: 8, injury: 1 },
                    '2025-26': { strength: 87, form: 8, injury: 0 }
                }
            },
            'aek athens': { 
                seasons: { 
                    '2023-24': { strength: 83, form: 7, injury: 2 },
                    '2024-25': { strength: 84, form: 7, injury: 2 },
                    '2025-26': { strength: 85, form: 8, injury: 1 }
                }
            },
            'panathinaikos': { 
                seasons: { 
                    '2023-24': { strength: 81, form: 6, injury: 3 },
                    '2024-25': { strength: 82, form: 7, injury: 2 },
                    '2025-26': { strength: 83, form: 7, injury: 2 }
                }
            },
            'paok': { 
                seasons: { 
                    '2023-24': { strength: 80, form: 6, injury: 2 },
                    '2024-25': { strength: 81, form: 6, injury: 2 },
                    '2025-26': { strength: 82, form: 7, injury: 1 }
                }
            },
            'aris': { 
                seasons: { 
                    '2023-24': { strength: 77, form: 5, injury: 3 },
                    '2024-25': { strength: 78, form: 6, injury: 2 },
                    '2025-26': { strength: 79, form: 6, injury: 2 }
                }
            },
            'asteras tripolis': { 
                seasons: { 
                    '2023-24': { strength: 75, form: 5, injury: 2 },
                    '2024-25': { strength: 76, form: 5, injury: 2 },
                    '2025-26': { strength: 77, form: 6, injury: 1 }
                }
            },
        };
    }

    predictMatch(team1, team2, season = '2025-26') {
        const t1Data = this.teamDatabase[team1.toLowerCase()];
        const t2Data = this.teamDatabase[team2.toLowerCase()];

        // Get team data for specified season or use current season
        const t1 = t1Data?.seasons?.[season] || t1Data?.seasons?.['2025-26'] || { strength: 75, form: 5, injury: 2 };
        const t2 = t2Data?.seasons?.[season] || t2Data?.seasons?.['2025-26'] || { strength: 75, form: 5, injury: 2 };

        // Calculate prediction based on strength, form, and injury status
        const t1Score = (t1.strength * 0.6) + (t1.form * 5) - (t1.injury * 3);
        const t2Score = (t2.strength * 0.6) + (t2.form * 5) - (t2.injury * 3);

        const total = t1Score + t2Score;
        const t1Percentage = Math.round((t1Score / total) * 100);
        const t2Percentage = 100 - t1Percentage;

        // Predict goals
        const t1Goals = Math.round((t1Score / 100) * 2.5);
        const t2Goals = Math.round((t2Score / 100) * 2.5);

        return {
            team1,
            team2,
            season,
            team1Win: t1Percentage,
            team2Win: t2Percentage,
            predictedScore: `${t1Goals}-${t2Goals}`,
            confidence: Math.max(t1Percentage, t2Percentage),
            t1Stats: t1,
            t2Stats: t2
        };
    }

    generateResponse(userInput) {
        const input = userInput.toLowerCase();

        // Greeting responses
        if (this.matchKeywords(input, ['hello', 'hi', 'hey', 'greetings'])) {
            const greetings = [
                "👋 Hello! I'm Footbot AI, your intelligent football predictor. Ready to make some accurate match predictions?",
                "Hey there! Let's predict some football matches together! Ask me anything about upcoming games.",
                "Hi! I'm here to give you precise match predictions and analysis. What match would you like me to analyze?"
            ];
            return { text: greetings[Math.floor(Math.random() * greetings.length)], type: 'bot-message' };
        }

        // Prediction requests (e.g., "predict manchester united vs liverpool")
        if (this.matchKeywords(input, ['predict', 'who will win', 'winner', 'vs', 'vs.'])) {
            const teams = this.extractTeams(input);
            const season = this.extractSeason(input) || '2025-26';
            
            if (teams.length === 2) {
                const prediction = this.predictMatch(teams[0], teams[1], season);
                const seasonLabel = season === '2023-24' ? 'Last Season' : season === '2024-25' ? 'Previous Season' : 'Current Season';
                const result = `🎯 MATCH PREDICTION: ${prediction.team1.toUpperCase()} vs ${prediction.team2.toUpperCase()}
📅 Season: ${seasonLabel} (${season})

📊 Win Probability:
  • ${prediction.team1.toUpperCase()}: ${prediction.team1Win}%
  • ${prediction.team2.toUpperCase()}: ${prediction.team2Win}%

⚽ Predicted Score: ${prediction.predictedScore}
🎲 Confidence Level: ${prediction.confidence}%

Team Stats (${season}):
  ${prediction.team1.toUpperCase()}: Strength ${prediction.t1Stats.strength}/100, Form ${prediction.t1Stats.form}/10
  ${prediction.team2.toUpperCase()}: Strength ${prediction.t2Stats.strength}/100, Form ${prediction.t2Stats.form}/10`;
                return { text: result, type: 'bot-message prediction' };
            } else if (teams.length === 1) {
                return { text: "I need both teams to make a prediction. Try: 'predict Liverpool vs Manchester City'", type: 'bot-message' };
            }
        }

        // Stats request
        if (this.matchKeywords(input, ['stats', 'statistics', 'team stats', 'how is', 'form', 'strength'])) {
            const teamName = this.extractTeamName(input);
            const season = this.extractSeason(input) || '2025-26';
            
            if (teamName && this.teamDatabase[teamName]) {
                const seasonLabel = season === '2023-24' ? 'Last Season' : season === '2024-25' ? 'Previous Season' : 'Current Season';
                const stats = this.teamDatabase[teamName].seasons?.[season] || this.teamDatabase[teamName].seasons?.['2025-26'];
                const formDescriptor = stats.form >= 7 ? 'Excellent 🔥' : stats.form >= 5 ? 'Good ✅' : 'Struggling ⚠️';
                return {
                    text: `📈 ${teamName.toUpperCase()} STATISTICS
📅 Season: ${seasonLabel} (${season})

Team Strength: ${stats.strength}/100 ⭐
Current Form: ${stats.form}/10 ${formDescriptor}
Injured Players: ${stats.injury}

Overall Assessment: Strong team with excellent fundamentals!`,
                    type: 'bot-message'
                };
            }
        }

        // Goals prediction
        if (this.matchKeywords(input, ['goals', 'score', 'how many goals', 'total goals'])) {
            const teams = this.extractTeams(input);
            const season = this.extractSeason(input) || '2025-26';
            
            if (teams.length === 2) {
                const prediction = this.predictMatch(teams[0], teams[1], season);
                const totalGoals = parseInt(prediction.predictedScore.split('-')[0]) + parseInt(prediction.predictedScore.split('-')[1]);
                return {
                    text: `⚽ GOAL PREDICTION: ${prediction.team1.toUpperCase()} vs ${prediction.team2.toUpperCase()}\n\nPredicted Score: ${prediction.predictedScore}\nExpected Total Goals: ${totalGoals}\n\nExpect an ${totalGoals > 2.5 ? 'exciting, high-scoring' : 'tactical, low-scoring'} match!`,
                    type: 'bot-message prediction'
                };
            }
        }

        // Help request
        if (this.matchKeywords(input, ['help', 'what can you do', 'how do i', 'commands', 'features', 'capabilities'])) {
            return {
                text: `⚡ HERE'S WHAT I CAN DO:\n\n🎯 Match Predictions:\n"predict Liverpool vs Man City"\n"predict Bayern 2023-24 vs Dortmund 2023-24"\n\n📊 Team Stats:\n"stats for Barcelona"\n"stats for Real Madrid 2024-25"\n\n⚔️ Team Comparisons:\n"compare Real Madrid vs Bayern Munich"\n\n⚽ Goal Predictions:\n"how many goals in Man Utd vs Arsenal"\n\n📅 Seasons: 2023-24, 2024-25, 2025-26\n🏆 Top 5 Leagues + Super League\n💡 Just ask me anything about football!`,
                type: 'bot-message'
            };
        }

        // Comparison request
        if (this.matchKeywords(input, ['compare', 'better', 'stronger', 'vs', 'which is better'])) {
            const teams = this.extractTeams(input);
            const season = this.extractSeason(input) || '2025-26';
            
            if (teams.length === 2) {
                const t1Data = this.teamDatabase[teams[0].toLowerCase()]?.seasons?.[season] || this.teamDatabase[teams[0].toLowerCase()]?.seasons?.['2025-26'];
                const t2Data = this.teamDatabase[teams[1].toLowerCase()]?.seasons?.[season] || this.teamDatabase[teams[1].toLowerCase()]?.seasons?.['2025-26'];
                
                if (!t1Data || !t2Data) {
                    return { text: "I couldn't find complete data for these teams.", type: 'bot-message' };
                }
                
                const stronger = t1Data.strength > t2Data.strength ? teams[0] : teams[1];
                const diff = Math.abs(t1Data.strength - t2Data.strength);
                return {
                    text: `🏆 TEAM COMPARISON:\n\n${teams[0].toUpperCase()}: ${t1Data.strength}/100 ⭐\n${teams[1].toUpperCase()}: ${t2Data.strength}/100 ⭐\n\n${stronger.toUpperCase()} is stronger by ${diff} points.\nThis would be a competitive matchup with ${stronger} as favorites!`,
                    type: 'bot-message'
                };
            }
        }

        // Default responses
        const defaultResponses = [
            "🤔 That's interesting! For best results, ask me to predict a match (e.g., 'predict Man City vs Liverpool')",
            "I'm specialized in match predictions! Try asking me about a specific matchup.",
            "⚽ I'm your football prediction expert! Ask me to predict any match or compare teams.",
            "Could you rephrase that? I work best with match predictions and team analysis."
        ];

        return { text: defaultResponses[Math.floor(Math.random() * defaultResponses.length)], type: 'bot-message' };
    }

    matchKeywords(text, keywords) {
        return keywords.some(keyword => text.includes(keyword));
    }

    extractTeams(text) {
        const teams = [];
        for (const team in this.teamDatabase) {
            if (text.includes(team)) {
                teams.push(team);
            }
        }
        return teams;
    }

    extractTeamName(text) {
        for (const team in this.teamDatabase) {
            if (text.includes(team)) {
                return team;
            }
        }
        return null;
    }

    extractSeason(text) {
        const seasons = ['2023-24', '2024-25', '2025-26'];
        for (const season of seasons) {
            if (text.includes(season)) {
                return season;
            }
        }
        return null;
    }
}

// Initialize chatbot when page loads
window.addEventListener('load', () => {
    new FootbotAI();
    console.log('⚽ Footbot AI Predictor initialized successfully!');
});

