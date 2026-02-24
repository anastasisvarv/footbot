# Footbot ⚽

A football AI chatbot that predicts match outcomes, shows standings, and answers
stats questions using a Rasa NLU backend and a local FBref data pipeline.

---

## Architecture

```
index.html / script.js / styles.css   ← static frontend (no build step)
        │  POST /webhooks/rest/webhook
        ▼
Rasa server (port 5005)               ← NLU + dialogue management
  • DIETClassifier  — intent + entity extraction
  • RulePolicy      — intent → action routing
        │  POST /webhook
        ▼
Action server (port 5055)             ← rasa/actions/
  • actions.py          — 6 Action classes
  • data_repository.py  — loads local parquet/json, provides query helpers
  • predictor.py        — Poisson distribution engine (stateless)
        ▲
        │  reads from
data/
  <league_slug>/<season>/
    matches.parquet
    standings.parquet
    teams.json
    metadata.json
        ▲
        │  written by
pipeline/                             ← FBref scraper CLI
  python -m pipeline update
```

---

## Supported Leagues

| League            | Slug                  | Source               |
|-------------------|-----------------------|----------------------|
| Premier League    | `premier_league`      | FBref (comp 9)       |
| La Liga           | `la_liga`             | FBref (comp 12)      |
| Serie A           | `serie_a`             | FBref (comp 11)      |
| Bundesliga        | `bundesliga`          | FBref (comp 20)      |
| Ligue 1           | `ligue_1`             | FBref (comp 13)      |
| Super League Greece | `super_league_greece` | FBref (comp 27)    |

Current season + 2 previous seasons are scraped per league.

---

## Setup

### Requirements

- Python **3.10.14** exactly (Rasa 3.6.x does not support 3.11+)
- macOS arm64: uses `tensorflow-macos` / `tensorflow-metal`

```bash
pyenv install 3.10.14
pyenv local 3.10.14
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Data Pipeline

### Scrape / refresh local data

```bash
source venv/bin/activate

# Scrape all 6 leagues (current + 2 previous seasons each)
python -m pipeline update

# Scrape one league only
python -m pipeline update --league premier_league

# Validate stored data
python -m pipeline validate
```

Data is written to `data/<league_slug>/<season>/` as parquet + JSON files.
**No API keys required** — all data is scraped from FBref.

> **Rate limiting:** a 1-second delay is enforced after every HTTP request.
> A full update (6 leagues × 3 seasons × 2 pages each) takes roughly 4–5 minutes.

---

## Running the Chatbot

### 1 — Start servers

```bash
source venv/bin/activate
./start.sh
```

Or manually:

```bash
# Action server (must start first)
cd rasa && rasa run actions --port 5055 > ../logs/actions.log 2>&1 &

# Rasa server
rasa run --enable-api --cors "*" --port 5005 \
    --endpoints rasa/endpoints.yml \
    --credentials rasa/credentials.yml > logs/rasa.log 2>&1 &
```

### 2 — Serve the frontend

```bash
python3 -m http.server 8080
# Open http://localhost:8080
```

### 3 — Test

```bash
curl -s -X POST http://localhost:5005/webhooks/rest/webhook \
  -H "Content-Type: application/json" \
  -d '{"sender":"test","message":"predict Liverpool vs Arsenal"}' \
  | python3 -m json.tool
```

### Kill servers

```bash
lsof -ti:5005 | xargs kill -9
lsof -ti:5055 | xargs kill -9
```

---

## Retraining Rasa

Required after any change to `rasa/data/` or `rasa/config.yml`:

```bash
source venv/bin/activate
rasa train \
    --domain rasa/domain.yml \
    --data rasa/data \
    --config rasa/config.yml \
    --out rasa/models/
```

Full retrain takes ~25 minutes on M4 (DIETClassifier 100 epochs).

---

## Key Files

| File | Purpose |
|------|---------|
| `pipeline/config.py` | League configs (FBref IDs, slugs) |
| `pipeline/scraper.py` | HTTP client + FBref HTML parsing |
| `pipeline/transforms.py` | DataFrame cleaning + team alias generation |
| `pipeline/storage.py` | Read/write parquet + JSON |
| `pipeline/validator.py` | Data quality checks |
| `pipeline/__main__.py` | CLI entry point |
| `rasa/actions/data_repository.py` | Singleton data store for Rasa actions |
| `rasa/actions/actions.py` | 6 Rasa custom action classes |
| `rasa/actions/predictor.py` | Poisson prediction engine |
| `rasa/config.yml` | NLU pipeline + policies |
| `rasa/domain.yml` | Intents, entities, slots, responses |
| `rasa/data/nlu.yml` | Training examples + lookup table |
| `rasa/data/rules.yml` | Intent → action mappings |

---

## Adding a New Intent

1. Add intent to `rasa/domain.yml` (intents list + response or action)
2. Add ≥5 annotated training examples to `rasa/data/nlu.yml`
3. Add a rule to `rasa/data/rules.yml`
4. If a custom action is needed: add `Action` subclass to `rasa/actions/actions.py`,
   register in `rasa/domain.yml` actions list
5. Retrain: `rasa train ...`
