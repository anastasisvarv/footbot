# Footbot ⚽ — AI Football Match Predictor

> **Πτυχιακή Εργασία** — Web Εφαρμογή Πρόβλεψης Ποδοσφαιρικών Αγώνων με Ενσωμάτωση Chatbot Τεχνητής Νοημοσύνης

---

## Περιγραφή (Abstract)

Το **Footbot** είναι μια ολοκληρωμένη web εφαρμογή που συνδυάζει:

1. **Chatbot Φυσικής Γλώσσας** — Βασισμένο στο Rasa 3.6.x (NLU + DIETClassifier + TEDPolicy), κατανοεί ελεύθερο κείμενο (9 intents, entities με roles home/away)
2. **Στατιστικό Μοντέλο Πρόβλεψης** — Κατανομή Poisson (Dixon-Coles, 1997), venue-aware με exponential decay weighting
3. **Αυτοματοποιημένη Άντληση Δεδομένων** — Web scraper για FBref.com (6 πρωταθλήματα, 3 σεζόν εκάστου), χωρίς API keys
4. **Διαδραστικό Frontend** — Dark-theme HTML/CSS/JS UI με Chart.js γραφήματα πιθανοτήτων real-time

---

## Αρχιτεκτονική Συστήματος

```
┌─────────────────────────────────────────────────────────────┐
│  FRONTEND  (index.html / script.js / styles.css)            │
│  - FootbotClient class  (session management, Chart.js)      │
│  - Chart.js win-probability bar chart (real-time)           │
└──────────────────────┬──────────────────────────────────────┘
                       │  POST /webhooks/rest/webhook
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  RASA SERVER  (port 5005)                                   │
│  - DIETClassifier — intent + entity extraction              │
│  - TEDPolicy + RulePolicy — dialogue management             │
└──────────────────────┬──────────────────────────────────────┘
                       │  POST /webhook
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  ACTION SERVER  (port 5055)   rasa/actions/                 │
│  - actions.py        — 6 custom Action classes              │
│  - data_repository.py — singleton, all in-memory            │
│  - predictor.py      — Poisson engine (Dixon-Coles)         │
└──────────────────────┬──────────────────────────────────────┘
                       │  reads parquet/JSON
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  DATA LAYER   data/<league_slug>/<season>/                  │
│  - matches.parquet   — ημερομηνία, ομάδες, γκολ            │
│  - standings.parquet — βαθμολογία πρωταθλήματος            │
│  - teams.json        — canonical ονόματα + aliases          │
│  - metadata.json     — πηγή, ημ. scraping, counts          │
└──────────────────────┬──────────────────────────────────────┘
                       │  written by
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  PIPELINE   pipeline/                                       │
│  python -m pipeline update                                  │
│  - scraper.py   — undetected-chromedriver (Cloudflare)      │
│  - transforms.py — καθαρισμός δεδομένων, aliases           │
│  - storage.py   — parquet + JSON I/O                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Υποστηριζόμενα Πρωταθλήματα

| Πρωτάθλημα          | Slug                  | FBref ID | Χώρα    |
|---------------------|-----------------------|----------|---------|
| Premier League      | `premier_league`      | 9        | England |
| La Liga             | `la_liga`             | 12       | Spain   |
| Serie A             | `serie_a`             | 11       | Italy   |
| Bundesliga          | `bundesliga`          | 20       | Germany |
| Ligue 1             | `ligue_1`             | 13       | France  |
| Super League Greece | `super_league_greece` | 27       | Greece  |

Για κάθε πρωτάθλημα αποθηκεύονται: **τρέχουσα σεζόν + 2 προηγούμενες**.

---

## Μοντέλο Πρόβλεψης (Θεωρητικό Υπόβαθρο)

### Κατανομή Poisson (Dixon-Coles, 1997)

Το σύστημα χρησιμοποιεί το **Dixon-Coles Poisson model** — industry standard για προβλέψεις ποδοσφαίρου:

```
λ_home = (αttack_home / league_avg) × (defense_away / league_avg) × league_avg
λ_away = (attack_away / league_avg) × (defense_home / league_avg) × league_avg

P(score = h-a) = Poisson(h; λ_home) × Poisson(a; λ_away)
```

#### Βελτιώσεις υλοποίησης:
- **Venue splits**: χρησιμοποιεί HOME stats για home teams και AWAY stats για away teams (αντί για overall μέσους όρους)
- **Exponential decay** (0.85/match): πιο πρόσφατα παιχνίδια έχουν μεγαλύτερο βάρος
- **Real league average**: υπολογίζεται από πραγματικά scraped δεδομένα (όχι hardcoded)

#### Αξιολόγηση μοντέλου:

```bash
python evaluate.py --league premier_league --export results.csv
```

Μετρικές που υπολογίζονται:
- **Accuracy** — ποσοστό σωστών 1X2 προβλέψεων
- **Brier Score** — βαθμός βαθμονόμησης πιθανοτήτων (0=τέλειο, 0.667=τυχαίο)
- **RPS** (Ranked Probability Score) — industry standard για ποδόσφαιρο (0=τέλειο, 0.25=τυχαίο)

Σύγκριση με baselines:
- Home-bias (πάντα προβλέπω home win: 50/25/25%)
- Uniform (33%/33%/33%)
- Historical frequency (εμπειρική κατανομή)

---

## NLU Pipeline (Rasa)

### Intents (9)
| Intent              | Παράδειγμα ερώτησης                        |
|---------------------|--------------------------------------------|
| `greet`             | "hello", "γεια σου"                        |
| `goodbye`           | "bye", "αντίο"                             |
| `help`              | "τι μπορείς να κάνεις;"                    |
| `predict_match`     | "predict Liverpool vs Arsenal"             |
| `get_team_stats`    | "Liverpool stats"                          |
| `compare_teams`     | "compare Real Madrid vs Barcelona"         |
| `get_standings`     | "show Premier League table"                |
| `get_recent_form`   | "Liverpool recent form"                    |
| `get_head_to_head`  | "Liverpool vs Arsenal head to head"        |

### Entities
- `team` με roles `home`/`away` — για σωστή αντιστοίχιση σε predict/compare/h2h
- `league` — αναγνώριση πρωταθλήματος από ελεύθερο κείμενο

### Γιατί Rasa και όχι Flask/Django;
Το Rasa προσφέρει **built-in NLU pipeline** (tokenizer → featurizer → DIETClassifier) και **dialogue management** (RulePolicy + TEDPolicy) που θα απαιτούσε εκατοντάδες γραμμές κώδικα σε Flask. Παρέχει επίσης entity roles, conversation tracking, και fallback handling out-of-the-box.

---

## Εγκατάσταση (Πλήρης Οδηγός)

### Προαπαιτούμενα
- **Python 3.10.14 ακριβώς** (Rasa 3.6.x δεν τρέχει σε 3.11+)
- **Google Chrome** (για τον scraper — χρησιμοποιεί undetected-chromedriver)
- macOS arm64: χρειάζεται `tensorflow-macos` + `tensorflow-metal`

### Βήμα 1 — Python Environment

```bash
# Εγκατάσταση pyenv (αν δεν υπάρχει)
brew install pyenv

# Εγκατάσταση Python 3.10.14
pyenv install 3.10.14
pyenv local 3.10.14

# Δημιουργία virtual environment
python -m venv venv
source venv/bin/activate

# Εγκατάσταση dependencies
pip install -r requirements.txt
```

### Βήμα 2 — Άντληση Δεδομένων (scraping)

```bash
source venv/bin/activate

# Όλα τα πρωταθλήματα (4-5 λεπτά)
python -m pipeline update

# Ή μόνο ένα πρωτάθλημα
python -m pipeline update --league premier_league

# Επαλήθευση δεδομένων
python -m pipeline validate
```

> ⚠️ Ο scraper ανοίγει πραγματικό παράθυρο Chrome. Απαιτείται internet σύνδεση.

### Βήμα 3 — Εκπαίδευση Rasa (αν χρειαστεί)

```bash
source venv/bin/activate
rasa train \
    --domain rasa/domain.yml \
    --data rasa/data \
    --config rasa/config.yml \
    --out rasa/models/
```

> Διαρκεί ~25 λεπτά (DIETClassifier 100 epochs + TEDPolicy).
> Απαιτείται μόνο μετά από αλλαγές στο `rasa/data/` ή `rasa/config.yml`.

### Βήμα 4 — Εκκίνηση

```bash
source venv/bin/activate
./start.sh

# Frontend
python3 -m http.server 8080
# Άνοιγμα: http://localhost:8080
```

---

## Εκτέλεση Αξιολόγησης Μοντέλου

```bash
source venv/bin/activate

# Αξιολόγηση όλων των πρωταθλημάτων
python evaluate.py

# Ένα πρωτάθλημα με export σε CSV
python evaluate.py --league premier_league --export results.csv

# Αυστηρότερη αξιολόγηση (≥8 προηγούμενα παιχνίδια ανά ομάδα)
python evaluate.py --min-matches 8
```

### Παράδειγμα αποτελέσματος:
```
======================================================================
  FOOTBOT — MODEL EVALUATION REPORT
======================================================================
  Prediction model : Poisson (Dixon-Coles, venue-aware)
  Test matches     : 247
  Leagues          : Premier League, La Liga, Serie A

  METRIC                 POISSON  HOME-BIAS    UNIFORM  HIST-FREQ
  --------------------------------------------------------------------
  Accuracy (1X2)          0.4777     0.4231     0.2717     0.4352
  Brier Score ↓           0.5891     0.6250     0.6667     0.6124
  RPS ↓                   0.2021     0.2312     0.2500     0.2198
```

---

## Εκτέλεση Unit Tests

```bash
source venv/bin/activate
pytest tests/ -v   # 52 tests, ~1 δευτερόλεπτο
```

### Κάλυψη tests:
| Module              | Tests | Τι δοκιμάζεται                           |
|---------------------|-------|------------------------------------------|
| `predictor.py`      | 28    | Poisson grid, venue splits, edge cases   |
| `data_repository.py`| 24    | Team/league resolution, stats, H2H       |

---

## Παραδείγματα Ερωτήσεων

```
predict Liverpool vs Arsenal
show Premier League table
Liverpool recent form
compare Real Madrid vs Barcelona
Liverpool vs Arsenal head to head
Liverpool stats
show Bundesliga standings
predict Bayern Munich vs Borussia Dortmund
```

---

## Βασικά Αρχεία

| Αρχείο | Σκοπός |
|--------|--------|
| `index.html` | Frontend template (static HTML5) |
| `script.js` | FootbotClient class — Rasa API calls, Chart.js |
| `styles.css` | Dark theme — 469 γραμμές CSS |
| `evaluate.py` | Backtesting script — Accuracy/Brier/RPS |
| `pipeline/config.py` | League configs (FBref IDs, slugs) |
| `pipeline/scraper.py` | HTTP + HTML parsing (rate-limited) |
| `pipeline/transforms.py` | DataFrame cleaning + alias generation |
| `pipeline/storage.py` | Read/write parquet + JSON |
| `pipeline/validator.py` | Data quality checks |
| `pipeline/__main__.py` | CLI (`update` / `validate`) |
| `rasa/config.yml` | NLU pipeline + policies |
| `rasa/domain.yml` | 9 intents, 2 entities, 6 custom actions |
| `rasa/data/nlu.yml` | 200+ annotated training examples |
| `rasa/data/rules.yml` | Intent → action mappings |
| `rasa/data/stories.yml` | Multi-turn conversation flows |
| `rasa/actions/actions.py` | 6 Rasa Action classes |
| `rasa/actions/data_repository.py` | Singleton data store (all in-memory) |
| `rasa/actions/predictor.py` | Poisson engine (Dixon-Coles) |
| `tests/test_predictor.py` | 28 unit tests |
| `tests/test_data_repository.py` | 24 unit tests |

---

## Διαχείριση Servers

```bash
# Τερματισμός servers
lsof -ti:5005 | xargs kill -9   # Rasa
lsof -ti:5055 | xargs kill -9   # Action server

# Test API
curl -s -X POST http://localhost:5005/webhooks/rest/webhook \
  -H "Content-Type: application/json" \
  -d '{"sender":"test","message":"predict Liverpool vs Arsenal"}' \
  | python3 -m json.tool
```

---

## Βιβλιογραφία

- Maher, M.J. (1982). *Modelling association football scores.* Statistica Neerlandica, 36(3), 109-118.
- Dixon, M. & Coles, S. (1997). *Modelling Association Football Scores and Inefficiencies in the Football Betting Market.* Applied Statistics, 46(2), 265-280.
- Constantinou, A.C. & Fenton, N.E. (2012). *Solving the problem of inadequate scoring rules for assessing probabilistic football forecast models.* Journal of Quantitative Analysis in Sports, 8(1).
- Rasa Open Source. (2023). *Rasa Documentation v3.6.* https://rasa.com/docs/rasa/

---

## Τεχνολογίες

| Τεχνολογία | Έκδοση | Χρήση |
|------------|--------|-------|
| Python | 3.10.14 | Backend |
| Rasa | 3.6.21 | NLU + Dialogue |
| TensorFlow | 2.11.0 | DIETClassifier / TEDPolicy |
| pandas | 2.0.3 | Data processing |
| PyArrow | 14.0.1 | Parquet I/O |
| scipy | 1.11.4 | Poisson distribution |
| Chart.js | 4.4.0 | Frontend charts |
| undetected-chromedriver | 3.5.5 | FBref scraping |
| pytest | 7.4.4 | Unit testing |

---

*Footbot AI Chatbot Predictor © 2026*
