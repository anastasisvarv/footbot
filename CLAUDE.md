# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

Footbot is a football AI chatbot.  A static HTML/JS frontend talks to a **Rasa 3.6.x**
NLU/dialogue backend (port 5005), which delegates all custom logic to a **Rasa action
server** (port 5055).  The action server loads data exclusively from **local parquet/json
files** produced by the FBref scraper pipeline — no live API calls at runtime.

## Data Source

All data is scraped from **FBref.com** only.  No API keys are required.

League base URLs:
- Premier League:      https://fbref.com/en/comps/9/Premier-League-Stats
- La Liga:             https://fbref.com/en/comps/12/La-Liga-Stats
- Serie A:             https://fbref.com/en/comps/11/Serie-A-Stats
- Bundesliga:          https://fbref.com/en/comps/20/Bundesliga-Stats
- Ligue 1:             https://fbref.com/en/comps/13/Ligue-1-Stats
- Super League Greece: https://fbref.com/en/comps/27/Super-League-Greece-Stats

3 seasons per league are scraped (current + 2 previous, discovered programmatically).

## Environment Setup (macOS arm64)

Rasa 3.6.x requires **Python 3.10 exactly** (not 3.9, not 3.11+).

```bash
pyenv install 3.10.14          # one-time
pyenv local 3.10.14
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Common Commands

**Scrape / refresh data** (required before starting the chatbot for the first time):
```bash
source venv/bin/activate
python -m pipeline update                    # all 6 leagues
python -m pipeline update --league serie_a   # one league only
python -m pipeline validate                  # check stored data
```

**Train the Rasa model** (required after any change to `rasa/data/` or `rasa/config.yml`):
```bash
source venv/bin/activate
rasa train --domain rasa/domain.yml --data rasa/data --config rasa/config.yml --out rasa/models/
```

**Start both servers** (action server must start before Rasa server):
```bash
# Action server — run from rasa/ so the 'actions' package is importable
cd rasa && rasa run actions --port 5055 > ../logs/actions.log 2>&1 &

# Rasa server
rasa run --enable-api --cors "*" --port 5005 \
    --endpoints rasa/endpoints.yml --credentials rasa/credentials.yml \
    > logs/rasa.log 2>&1 &
```

Alternatively: `./start.sh`

**Serve the frontend:**
```bash
python3 -m http.server 8080    # open http://localhost:8080
```

**Test a message end-to-end:**
```bash
curl -s -X POST http://localhost:5005/webhooks/rest/webhook \
  -H "Content-Type: application/json" \
  -d '{"sender":"test","message":"predict Liverpool vs Arsenal"}' | python3 -m json.tool
```

**Validate training data:**
```bash
rasa data validate --domain rasa/domain.yml --data rasa/data
```

**Kill servers by port:**
```bash
lsof -ti:5005 | xargs kill -9
lsof -ti:5055 | xargs kill -9
```

## Architecture

```
index.html / script.js / styles.css   ← static frontend
        │  POST /webhooks/rest/webhook
        ▼
Rasa server (port 5005)               ← NLU + dialogue management
  • DIETClassifier  — intent + entity extraction
  • MemoizationPolicy + TEDPolicy + RulePolicy — action selection
        │  POST /webhook
        ▼
Action server (port 5055)             ← rasa/actions/
  • actions.py          — 6 Action classes (NO live HTTP)
  • data_repository.py  — loads parquet/JSON, provides query helpers
  • predictor.py        — Poisson distribution engine (stateless)
        ▲
        │  reads from
data/
  <league_slug>/<season>/
    matches.parquet      ← date, home_team, away_team, goals, round
    standings.parquet    ← team, MP, W, D, L, GF, GA, GD, points
    teams.json           ← canonical name + aliases
    metadata.json        ← source, scraped_at, row_counts
        ▲
        │  written by
pipeline/                ← python -m pipeline update
```

## Pipeline Design

### Scraping rules (pipeline/scraper.py)
- Fixed delay: `time.sleep(1.0)` after **every** HTTP request — no exceptions.
- No concurrency: all requests are sequential.
- Tables inside HTML comments: `_all_tables()` parses both the live DOM and
  HTML comment blocks (FBref quirk — many stat tables are comment-embedded).
- User-Agent mimics a real browser to avoid 403s.
- Retries: up to 3 attempts with back-off; 404/403/410 are not retried.

### Season URL discovery (pipeline/scraper.py::get_seasons)
- Fetches the base competition page.
- Extracts season slug from `<a href>` tags matching the pattern
  `/en/comps/{id}/YYYY-YYYY/YYYY-YYYY-{slug}-Stats`.
- Current season lives at the base URL (no year prefix in the path).
- Takes current + 2 most-recent previous seasons.

### Data cleaning (pipeline/transforms.py)
- One identical schema for all leagues and seasons.
- Goals are stored as nullable `Int64` (pandas extension type → parquet compatible).
- Deduplication: on `(date, home_team, away_team)`.
- Team aliases: generated from FBref canonical names — prefix/suffix stripping,
  diacritic removal (e.g. "FC Bayern München" → "Bayern Munich").

## DataRepository (rasa/actions/data_repository.py)

Singleton loaded once on action-server startup.  All in-memory.

```python
repo = DataRepository.get()            # singleton
stats = repo.get_team_stats("Liverpool")
table = repo.get_standings("Premier League")
form  = repo.get_recent_form("Arsenal", n=5)
h2h   = repo.get_head_to_head("Liverpool", "Arsenal")
slug  = repo.resolve_league("EPL")    # → "premier_league"
name  = repo.resolve_team("Man City") # → "Manchester City"
```

Team name resolution order:
1. Exact/alias lookup in `_alias_map` (built from `teams.json` files)
2. Fuzzy matching via `difflib.get_close_matches` (cutoff 0.6)
3. Substring fallback

To force a reload after `python -m pipeline update`:
```python
DataRepository.reset()
repo = DataRepository.get()
```

## NLU Pipeline Design

`EntitySynonymMapper` is **intentionally omitted** from `rasa/config.yml`.
It causes role-conflict warnings because the same team name (e.g. "Arsenal")
appears as both `team:home` and `team:away`.  Alias resolution is handled instead
by `DataRepository.resolve_team()`.

The `team` entity uses **roles** (`team:home`, `team:away`) for predict/compare/h2h
intents.  `_get_teams()` in `actions.py` extracts by role first, then falls back
to positional order.

## DIET Retraining Gotcha

When you add only a **lookup table** to `nlu.yml`, Rasa reuses cached DIET weights
(~30 s train) because the training *examples* haven't changed.  To force a full
DIET retrain (needed for new team names), add actual annotated examples like
`[Brentford](team:home)` to at least one intent.  Full retrain ≈ 25 min on M4.

## Prediction Engine (rasa/actions/predictor.py)

Stateless Poisson model.  Takes `home_stats` and `away_stats` dicts (both must
have `avg_goals_scored` and `avg_goals_conceded`).  Tuning knobs:
- `HOME_ADVANTAGE = 1.20`
- `LEAGUE_AVG_DEFAULTS` — per-league goals-per-match averages

## Key Files

| File | Purpose |
|------|---------|
| `pipeline/config.py` | League configs (FBref IDs, slugs, DATA_DIR) |
| `pipeline/scraper.py` | HTTP + HTML parsing (rate-limited, retry) |
| `pipeline/transforms.py` | DataFrame cleaning, alias generation |
| `pipeline/storage.py` | Read/write parquet + JSON |
| `pipeline/validator.py` | Data quality checks |
| `pipeline/__main__.py` | CLI (`update` / `validate`) |
| `rasa/actions/data_repository.py` | Singleton data store |
| `rasa/actions/actions.py` | 6 Rasa custom action classes |
| `rasa/actions/predictor.py` | Poisson engine (unchanged) |
| `rasa/config.yml` | NLU pipeline + policies |
| `rasa/domain.yml` | Intents, entities, slots, responses, actions |
| `rasa/data/nlu.yml` | Training examples + lookup table + synonyms |
| `rasa/data/rules.yml` | Intent → action mappings |

## Adding a New Intent

1. Add intent to `rasa/domain.yml` (intents list + utter_* or action entry)
2. Add training examples to `rasa/data/nlu.yml` (with entity annotations if needed)
3. Add a rule to `rasa/data/rules.yml`
4. If custom action: add `Action` subclass to `rasa/actions/actions.py`,
   register in domain `actions:` list
5. Retrain: `rasa train ...`

## Deprecated / Pending Removal

See `CLEANUP.md` for the full list.  Short version:
- `rasa/actions/football_data.py` — replaced by `data_repository.py`
- `scraper/fetch_data.py` — replaced by `python -m pipeline update`
- `python-dotenv` in `requirements.txt` — no longer needed (no API keys)
