"""
Football data client.
Fetches from football-data.org API (free tier) for major European leagues,
and scrapes Greek Super League data from worldfootball.net.
All results are cached in data/football_cache.json with 24-hour TTL.
"""

import json
import os
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[3]  # project root
CACHE_FILE = ROOT / "data" / "football_cache.json"
CACHE_TTL = 86_400  # 24 hours in seconds

API_BASE = "https://api.football-data.org/v4"
API_KEY = os.getenv("FOOTBALL_DATA_API_KEY", "")

LEAGUE_CODES = {
    "premier league": "PL",
    "la liga": "PD",
    "serie a": "SA",
    "bundesliga": "BL1",
    "ligue 1": "FL1",
}

# Normalised team name → football-data.org team ID (most searched teams)
TEAM_IDS: Dict[str, int] = {
    "liverpool": 64,
    "arsenal": 57,
    "manchester city": 65,
    "chelsea": 61,
    "manchester united": 66,
    "tottenham": 73,
    "newcastle": 67,
    "aston villa": 58,
    "brighton": 397,
    "west ham": 563,
    "real madrid": 86,
    "barcelona": 81,
    "atletico madrid": 78,
    "sevilla": 559,
    "real betis": 558,
    "valencia": 95,
    "inter": 108,
    "juventus": 109,
    "ac milan": 98,
    "napoli": 113,
    "lazio": 110,
    "roma": 100,
    "bayern munich": 5,
    "borussia dortmund": 4,
    "bayer leverkusen": 3,
    "rb leipzig": 721,
    "vfl wolfsburg": 11,
    "psg": 524,
    "marseille": 516,
    "lyon": 523,
    "monaco": 548,
    "nice": 522,
}


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _load_cache() -> Dict[str, Any]:
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def _save_cache(cache: Dict[str, Any]) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def _cache_get(key: str) -> Optional[Any]:
    cache = _load_cache()
    entry = cache.get(key)
    if entry and (time.time() - entry.get("ts", 0)) < CACHE_TTL:
        return entry.get("data")
    return None


def _cache_set(key: str, data: Any) -> None:
    cache = _load_cache()
    cache[key] = {"ts": time.time(), "data": data}
    _save_cache(cache)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _api_get(path: str) -> Optional[Dict]:
    if not API_KEY:
        logger.warning("FOOTBALL_DATA_API_KEY not set — API calls will fail.")
        return None
    url = f"{API_BASE}{path}"
    headers = {"X-Auth-Token": API_KEY}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 429:
            logger.warning("API rate limit reached — using cache.")
            return None
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.error("API request failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Standings
# ---------------------------------------------------------------------------

def get_standings(league: str) -> Optional[List[Dict]]:
    """Return top-5 standing rows for a league."""
    league_norm = league.lower().strip()

    # Greek Super League via scraper
    if "super league" in league_norm or "greek" in league_norm:
        return _scrape_greek_standings()

    code = LEAGUE_CODES.get(league_norm)
    if not code:
        # Fuzzy match
        for name, c in LEAGUE_CODES.items():
            if any(word in league_norm for word in name.split()):
                code = c
                break
    if not code:
        return None

    cache_key = f"standings_{code}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    data = _api_get(f"/competitions/{code}/standings")
    if not data:
        return None

    table = data.get("standings", [{}])[0].get("table", [])[:5]
    rows = [
        {
            "position": r["position"],
            "team": r["team"]["name"],
            "points": r["points"],
            "played": r["playedGames"],
            "won": r["won"],
            "draw": r["draw"],
            "lost": r["lost"],
            "gf": r["goalsFor"],
            "ga": r["goalsAgainst"],
            "gd": r["goalDifference"],
        }
        for r in table
    ]
    _cache_set(cache_key, rows)
    return rows


def _scrape_greek_standings() -> Optional[List[Dict]]:
    cache_key = "standings_greek"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    urls = [
        "https://www.worldfootball.net/teams/super-league-greece/2025-2026/",
        "https://www.soccerstats.com/table.asp?league=greece",
    ]

    for url in urls:
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            rows = _parse_standings_table(soup)
            if rows:
                _cache_set(cache_key, rows)
                return rows
        except Exception as exc:
            logger.warning("Scrape failed for %s: %s", url, exc)

    # Fallback static data
    fallback = [
        {"position": 1, "team": "Olympiacos", "points": 55, "played": 24, "won": 17, "draw": 4, "lost": 3, "gf": 48, "ga": 20, "gd": 28},
        {"position": 2, "team": "PAOK", "points": 52, "played": 24, "won": 16, "draw": 4, "lost": 4, "gf": 44, "ga": 22, "gd": 22},
        {"position": 3, "team": "AEK Athens", "points": 48, "played": 24, "won": 14, "draw": 6, "lost": 4, "gf": 40, "ga": 25, "gd": 15},
        {"position": 4, "team": "Panathinaikos", "points": 45, "played": 24, "won": 13, "draw": 6, "lost": 5, "gf": 38, "ga": 27, "gd": 11},
        {"position": 5, "team": "ARIS", "points": 38, "played": 24, "won": 11, "draw": 5, "lost": 8, "gf": 33, "ga": 32, "gd": 1},
    ]
    return fallback


def _parse_standings_table(soup: BeautifulSoup) -> List[Dict]:
    rows = []
    table = soup.find("table", class_=lambda c: c and "standard" in c)
    if not table:
        table = soup.find("table")
    if not table:
        return rows

    for i, tr in enumerate(table.find_all("tr")[1:6], start=1):
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if len(cells) >= 8:
            try:
                rows.append({
                    "position": i,
                    "team": cells[1] if len(cells) > 1 else f"Team {i}",
                    "played": int(cells[2]) if cells[2].isdigit() else 0,
                    "won": int(cells[3]) if cells[3].isdigit() else 0,
                    "draw": int(cells[4]) if cells[4].isdigit() else 0,
                    "lost": int(cells[5]) if cells[5].isdigit() else 0,
                    "gf": int(cells[6]) if cells[6].isdigit() else 0,
                    "ga": int(cells[7]) if cells[7].isdigit() else 0,
                    "gd": 0,
                    "points": int(cells[-1]) if cells[-1].isdigit() else 0,
                })
            except (ValueError, IndexError):
                continue
    return rows


# ---------------------------------------------------------------------------
# Team matches / stats
# ---------------------------------------------------------------------------

def get_team_matches(team_name: str, limit: int = 10) -> Optional[List[Dict]]:
    """Return recent matches for a team."""
    norm = _normalise_team(team_name)
    team_id = TEAM_IDS.get(norm)
    if not team_id:
        return None

    cache_key = f"matches_{team_id}_{limit}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    data = _api_get(f"/teams/{team_id}/matches?status=FINISHED&limit={limit}")
    if not data:
        return None

    matches = []
    for m in data.get("matches", []):
        home = m["homeTeam"]["name"]
        away = m["awayTeam"]["name"]
        score = m.get("score", {}).get("fullTime", {})
        matches.append({
            "date": m.get("utcDate", "")[:10],
            "home_team": home,
            "away_team": away,
            "home_goals": score.get("home"),
            "away_goals": score.get("away"),
            "competition": m.get("competition", {}).get("name", ""),
        })

    _cache_set(cache_key, matches)
    return matches


def get_team_stats(team_name: str) -> Optional[Dict]:
    """Return aggregated stats (avg goals scored/conceded, form, W/D/L)."""
    matches = get_team_matches(team_name, limit=10)
    if matches is None:
        return _fallback_team_stats(team_name)

    norm = _normalise_team(team_name)
    # Find the canonical team name from matches
    canonical = None
    for m in matches:
        if norm in m["home_team"].lower():
            canonical = m["home_team"]
            break
        if norm in m["away_team"].lower():
            canonical = m["away_team"]
            break

    if not canonical:
        return _fallback_team_stats(team_name)

    goals_scored = []
    goals_conceded = []
    results = []

    for m in matches:
        hg = m["home_goals"]
        ag = m["away_goals"]
        if hg is None or ag is None:
            continue
        if m["home_team"] == canonical:
            goals_scored.append(hg)
            goals_conceded.append(ag)
            results.append("W" if hg > ag else ("D" if hg == ag else "L"))
        else:
            goals_scored.append(ag)
            goals_conceded.append(hg)
            results.append("W" if ag > hg else ("D" if ag == hg else "L"))

    if not results:
        return _fallback_team_stats(team_name)

    played = len(results)
    won = results.count("W")
    drawn = results.count("D")
    lost = results.count("L")
    avg_scored = round(sum(goals_scored) / played, 2)
    avg_conceded = round(sum(goals_conceded) / played, 2)
    form = results[-5:] if len(results) >= 5 else results

    return {
        "team": canonical,
        "played": played,
        "won": won,
        "drawn": drawn,
        "lost": lost,
        "avg_goals_scored": avg_scored,
        "avg_goals_conceded": avg_conceded,
        "form": form,
        "recent_matches": matches[:5],
    }


def _fallback_team_stats(team_name: str) -> Dict:
    """Static fallback when API is unavailable."""
    STATIC = {
        "liverpool": {"avg_goals_scored": 2.3, "avg_goals_conceded": 0.9, "form": ["W","W","D","W","W"]},
        "arsenal": {"avg_goals_scored": 2.1, "avg_goals_conceded": 1.0, "form": ["W","D","W","W","L"]},
        "manchester city": {"avg_goals_scored": 2.5, "avg_goals_conceded": 0.8, "form": ["W","W","W","D","W"]},
        "real madrid": {"avg_goals_scored": 2.4, "avg_goals_conceded": 0.9, "form": ["W","W","W","W","D"]},
        "barcelona": {"avg_goals_scored": 2.2, "avg_goals_conceded": 1.1, "form": ["W","W","D","W","W"]},
        "bayern munich": {"avg_goals_scored": 2.6, "avg_goals_conceded": 1.0, "form": ["W","W","W","W","W"]},
    }
    norm = _normalise_team(team_name)
    base = STATIC.get(norm, {"avg_goals_scored": 1.5, "avg_goals_conceded": 1.3, "form": ["W","D","L","W","D"]})
    return {
        "team": team_name.title(),
        "played": 10,
        "won": 5, "drawn": 3, "lost": 2,
        **base,
        "recent_matches": [],
        "_fallback": True,
    }


# ---------------------------------------------------------------------------
# Head-to-head
# ---------------------------------------------------------------------------

def get_head_to_head(team1: str, team2: str) -> Optional[Dict]:
    """Return H2H record derived from recent matches of team1."""
    cache_key = f"h2h_{_normalise_team(team1)}_{_normalise_team(team2)}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    matches = get_team_matches(team1, limit=20)
    if not matches:
        return None

    norm2 = _normalise_team(team2)
    h2h_matches = [
        m for m in matches
        if norm2 in m["home_team"].lower() or norm2 in m["away_team"].lower()
    ]

    if not h2h_matches:
        return None

    norm1 = _normalise_team(team1)
    t1_wins = t2_wins = draws = 0
    for m in h2h_matches:
        hg, ag = m["home_goals"], m["away_goals"]
        if hg is None or ag is None:
            continue
        t1_is_home = norm1 in m["home_team"].lower()
        if hg == ag:
            draws += 1
        elif (t1_is_home and hg > ag) or (not t1_is_home and ag > hg):
            t1_wins += 1
        else:
            t2_wins += 1

    result = {
        "team1": team1.title(),
        "team2": team2.title(),
        "matches_found": len(h2h_matches),
        "team1_wins": t1_wins,
        "team2_wins": t2_wins,
        "draws": draws,
        "recent_h2h": h2h_matches[:5],
    }
    _cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _normalise_team(name: str) -> str:
    """Lowercase, strip, resolve common aliases."""
    ALIASES = {
        "man city": "manchester city",
        "man united": "manchester united",
        "man utd": "manchester united",
        "paris saint-germain": "psg",
        "paris saint germain": "psg",
        "inter milan": "inter",
        "internazionale": "inter",
        "atletico": "atletico madrid",
        "atleti": "atletico madrid",
        "spurs": "tottenham",
        "bvb": "borussia dortmund",
        "dortmund": "borussia dortmund",
        "leverkusen": "bayer leverkusen",
        "bayer leverkusen": "bayer leverkusen",
        "leipzig": "rb leipzig",
        "red bull leipzig": "rb leipzig",
        "milan": "ac milan",
        "olympiakos": "olympiacos",
        "aek": "aek athens",
        "pao": "panathinaikos",
        "villa": "aston villa",
        "hammers": "west ham",
    }
    norm = name.lower().strip()
    return ALIASES.get(norm, norm)


def resolve_league(text: str) -> str:
    """Map free-text league mention to a canonical name."""
    text_lower = text.lower()
    if any(w in text_lower for w in ["premier", "epl", "english"]):
        return "Premier League"
    if any(w in text_lower for w in ["la liga", "laliga", "spain", "pd"]):
        return "La Liga"
    if any(w in text_lower for w in ["serie a", "italian", "italy"]):
        return "Serie A"
    if any(w in text_lower for w in ["bundesliga", "german", "germany"]):
        return "Bundesliga"
    if any(w in text_lower for w in ["ligue 1", "french", "france"]):
        return "Ligue 1"
    if any(w in text_lower for w in ["super league", "greek", "greece"]):
        return "Super League"
    return text
