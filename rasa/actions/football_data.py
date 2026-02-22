"""
Football data client.
Fetches from football-data.org API (free tier) for major European leagues,
and scrapes Greek Super League data from worldfootball.net.
All results are cached in data/football_cache.json with 24-hour TTL.

Team coverage: all teams in all 5 API-supported leagues are discovered
dynamically from the standings endpoint, so no hardcoded list is needed.
"""

import json
import os
import re
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

LEAGUE_CODES: Dict[str, str] = {
    "premier league": "PL",
    "la liga": "PD",
    "serie a": "SA",
    "bundesliga": "BL1",
    "ligue 1": "FL1",
}

# Fallback hardcoded IDs — used only if the dynamic index hasn't been built yet
_FALLBACK_IDS: Dict[str, int] = {
    "liverpool": 64, "arsenal": 57, "manchester city": 65, "chelsea": 61,
    "manchester united": 66, "tottenham": 73, "newcastle": 67,
    "aston villa": 58, "brighton": 397, "west ham": 563,
    "real madrid": 86, "barcelona": 81, "atletico madrid": 78,
    "sevilla": 559, "real betis": 558, "valencia": 95,
    "inter": 108, "juventus": 109, "ac milan": 98,
    "napoli": 113, "lazio": 110, "roma": 100,
    "bayern munich": 5, "borussia dortmund": 4, "bayer leverkusen": 3,
    "rb leipzig": 721, "vfl wolfsburg": 11,
    "psg": 524, "marseille": 516, "lyon": 523, "monaco": 548, "nice": 522,
}

# Common prefixes / suffixes to strip when normalising API team names
_STRIP_PREFIXES = re.compile(
    r"^(fc|ac|as|sc|ss|us|cf|vfb|vfl|rb|tsg|ogc|bsc|rc|rsc|sv|sk|fk|afc|fcd)\s+",
    re.IGNORECASE,
)
_STRIP_SUFFIXES = re.compile(
    r"\s+(fc|cf|sc|ac|fk|sk|if|afc|ssc|calcio|de|1899|1900|1904|1907|1908|1909|1910|1912)$",
    re.IGNORECASE,
)


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
# Dynamic team index
# ---------------------------------------------------------------------------

def _api_name_to_keys(name: str, short_name: str = "") -> List[str]:
    """
    Given an API team name (e.g. "FC Bayern München"), return all normalised
    keys we want to index it under so fuzzy user queries can match it.
    """
    keys = set()
    base = name.lower().strip()
    keys.add(base)                                # "fc bayern münchen"

    # strip prefix
    stripped = _STRIP_PREFIXES.sub("", base).strip()
    keys.add(stripped)                            # "bayern münchen"

    # strip suffix
    stripped2 = _STRIP_SUFFIXES.sub("", stripped).strip()
    keys.add(stripped2)                           # same or shorter

    # also strip suffix from original
    stripped3 = _STRIP_SUFFIXES.sub("", base).strip()
    keys.add(stripped3)

    if short_name:
        keys.add(short_name.lower().strip())      # "Bayern Munich" → "bayern munich"

    # replace special chars: ü→u, é→e, ö→o, á→a, etc.
    def deaccent(s: str) -> str:
        return (s.replace("ü", "u").replace("ö", "o").replace("ä", "a")
                  .replace("é", "e").replace("è", "e").replace("ê", "e")
                  .replace("á", "a").replace("à", "a").replace("â", "a")
                  .replace("í", "i").replace("ó", "o").replace("ú", "u")
                  .replace("ñ", "n").replace("ç", "c"))

    for k in list(keys):
        keys.add(deaccent(k))

    return [k for k in keys if k]


def _build_team_index() -> Dict[str, int]:
    """
    Fetch standings for all 5 API leagues and build a comprehensive
    normalised_name → team_id mapping. Cached for 24 hours.
    """
    cached = _cache_get("team_index")
    if cached:
        return cached

    index: Dict[str, int] = {}

    for league_name, code in LEAGUE_CODES.items():
        data = _api_get(f"/competitions/{code}/standings")
        if not data:
            continue
        table = data.get("standings", [{}])[0].get("table", [])
        for row in table:
            team = row.get("team", {})
            team_id = team.get("id")
            if not team_id:
                continue
            full_name = team.get("name", "")
            short_name = team.get("shortName", "")
            for key in _api_name_to_keys(full_name, short_name):
                index[key] = team_id

    if index:
        _cache_set("team_index", index)
        logger.info("Team index built: %d entries covering all league teams", len(index))
    else:
        logger.warning("Team index is empty — API may be unavailable")

    return index


def _resolve_team_id(team_name: str) -> Tuple[Optional[int], str]:
    """
    Return (team_id, matched_key) for a user-supplied team name.
    Tries dynamic index first, then falls back to hardcoded IDs.
    Returns (None, "") if no match found.
    """
    norm = _normalise_team(team_name)
    query_keys = _api_name_to_keys(norm, norm)

    # 1. Try dynamic index
    index = _build_team_index()
    for key in query_keys:
        if key in index:
            return index[key], key

    # 2. Substring / partial match against index
    for key in query_keys:
        for idx_key, tid in index.items():
            if key in idx_key or idx_key in key:
                return tid, idx_key

    # 3. Fallback hardcoded map
    for key in query_keys:
        if key in _FALLBACK_IDS:
            return _FALLBACK_IDS[key], key

    return None, ""


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

    full_table = data.get("standings", [{}])[0].get("table", [])

    # Opportunistically populate the team index from the full table
    _update_team_index_from_table(full_table)

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
        for r in full_table[:5]
    ]
    _cache_set(cache_key, rows)
    return rows


def _update_team_index_from_table(table: List[Dict]) -> None:
    """Merge new team name→id pairs into the cached team index."""
    if not table:
        return
    cache = _load_cache()
    entry = cache.get("team_index", {})
    index: Dict[str, int] = entry.get("data", {}) if isinstance(entry, dict) and "data" in entry else {}

    for row in table:
        team = row.get("team", {})
        team_id = team.get("id")
        if not team_id:
            continue
        for key in _api_name_to_keys(team.get("name", ""), team.get("shortName", "")):
            index[key] = team_id

    cache["team_index"] = {"ts": time.time(), "data": index}
    _save_cache(cache)


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

    # Static fallback
    fallback = [
        {"position": 1, "team": "Olympiacos", "points": 55, "played": 24, "won": 17, "draw": 4, "lost": 3, "gf": 48, "ga": 20, "gd": 28},
        {"position": 2, "team": "PAOK",       "points": 52, "played": 24, "won": 16, "draw": 4, "lost": 4, "gf": 44, "ga": 22, "gd": 22},
        {"position": 3, "team": "AEK Athens", "points": 48, "played": 24, "won": 14, "draw": 6, "lost": 4, "gf": 40, "ga": 25, "gd": 15},
        {"position": 4, "team": "Panathinaikos", "points": 45, "played": 24, "won": 13, "draw": 6, "lost": 5, "gf": 38, "ga": 27, "gd": 11},
        {"position": 5, "team": "ARIS",       "points": 38, "played": 24, "won": 11, "draw": 5, "lost": 8, "gf": 33, "ga": 32, "gd": 1},
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
    """Return recent finished matches for a team."""
    team_id, _ = _resolve_team_id(team_name)
    if not team_id:
        logger.warning("Could not resolve team ID for '%s'", team_name)
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
        score = m.get("score", {}).get("fullTime", {})
        matches.append({
            "date": m.get("utcDate", "")[:10],
            "home_team": m["homeTeam"]["name"],
            "away_team": m["awayTeam"]["name"],
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
    # Find the canonical name this team appears as in the match data
    canonical = None
    for m in matches:
        if _teams_match(norm, m["home_team"]):
            canonical = m["home_team"]
            break
        if _teams_match(norm, m["away_team"]):
            canonical = m["away_team"]
            break

    if not canonical:
        return _fallback_team_stats(team_name)

    goals_scored, goals_conceded, results = [], [], []

    for m in matches:
        hg, ag = m["home_goals"], m["away_goals"]
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
    return {
        "team": canonical,
        "played": played,
        "won": results.count("W"),
        "drawn": results.count("D"),
        "lost": results.count("L"),
        "avg_goals_scored": round(sum(goals_scored) / played, 2),
        "avg_goals_conceded": round(sum(goals_conceded) / played, 2),
        "form": results[-5:] if len(results) >= 5 else results,
        "recent_matches": matches[:5],
    }


def _fallback_team_stats(team_name: str) -> Dict:
    """Static fallback used when API is unavailable or team not found."""
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
        "played": 10, "won": 5, "drawn": 3, "lost": 2,
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
    h2h = [m for m in matches if _teams_match(norm2, m["home_team"]) or _teams_match(norm2, m["away_team"])]

    if not h2h:
        return None

    norm1 = _normalise_team(team1)
    t1_wins = t2_wins = draws = 0
    for m in h2h:
        hg, ag = m["home_goals"], m["away_goals"]
        if hg is None or ag is None:
            continue
        t1_home = _teams_match(norm1, m["home_team"])
        if hg == ag:
            draws += 1
        elif (t1_home and hg > ag) or (not t1_home and ag > hg):
            t1_wins += 1
        else:
            t2_wins += 1

    result = {
        "team1": team1.title(),
        "team2": team2.title(),
        "matches_found": len(h2h),
        "team1_wins": t1_wins,
        "team2_wins": t2_wins,
        "draws": draws,
        "recent_h2h": h2h[:5],
    }
    _cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _normalise_team(name: str) -> str:
    """Lowercase, strip, resolve common user-facing aliases."""
    ALIASES = {
        "man city": "manchester city",
        "man united": "manchester united",
        "man utd": "manchester united",
        "paris saint-germain": "psg",
        "paris saint germain": "psg",
        "paris sg": "psg",
        "inter milan": "inter",
        "internazionale": "inter",
        "atletico": "atletico madrid",
        "atleti": "atletico madrid",
        "atletico de madrid": "atletico madrid",
        "spurs": "tottenham",
        "tottenham hotspur": "tottenham",
        "bvb": "borussia dortmund",
        "dortmund": "borussia dortmund",
        "leverkusen": "bayer leverkusen",
        "leipzig": "rb leipzig",
        "red bull leipzig": "rb leipzig",
        "milan": "ac milan",
        "rossoneri": "ac milan",
        "olympiakos": "olympiacos",
        "aek": "aek athens",
        "pao": "panathinaikos",
        "villa": "aston villa",
        "hammers": "west ham",
        "west ham united": "west ham",
        "newcastle united": "newcastle",
        "wolves": "wolverhampton",
        "wolfsburg": "vfl wolfsburg",
        "gladbach": "borussia monchengladbach",
        "monchengladbach": "borussia monchengladbach",
        "hoffenheim": "tsg hoffenheim",
        "tsg 1899 hoffenheim": "tsg hoffenheim",
        "freiburg": "sc freiburg",
        "eintracht": "eintracht frankfurt",
        "frankfurt": "eintracht frankfurt",
        "mainz": "1. fsv mainz 05",
        "cologne": "1. fc koln",
        "koln": "1. fc koln",
        "augsburg": "fc augsburg",
        "union berlin": "1. fc union berlin",
        "saint-etienne": "as saint-etienne",
        "st etienne": "as saint-etienne",
        "rennes": "stade rennais",
        "strasbourg": "rc strasbourg",
        "lens": "rc lens",
        "lille": "losc lille",
        "reims": "stade de reims",
        "nantes": "fc nantes",
        "bordeaux": "fc girondins de bordeaux",
        "torino": "torino fc",
        "fiorentina": "acf fiorentina",
        "atalanta": "atalanta bc",
        "bologna": "bologna fc",
        "udinese": "udinese calcio",
        "sampdoria": "uc sampdoria",
        "genoa": "genoa cfc",
        "cagliari": "cagliari calcio",
        "celta": "celta de vigo",
        "celta vigo": "celta de vigo",
        "athletic": "athletic club",
        "athletic bilbao": "athletic club",
        "sociedad": "real sociedad",
        "real sociedad": "real sociedad",
        "osasuna": "ca osasuna",
        "girona": "girona fc",
        "mallorca": "rcd mallorca",
        "espanyol": "rcd espanyol",
        "valladolid": "real valladolid",
        "villarreal": "villarreal cf",
        "getafe": "getafe cf",
        "rayo": "rayo vallecano",
    }
    norm = name.lower().strip()
    return ALIASES.get(norm, norm)


def _teams_match(query_norm: str, api_name: str) -> bool:
    """True if the normalised query matches an API team name."""
    api_norm = api_name.lower().strip()
    if query_norm in api_norm or api_norm in query_norm:
        return True
    # Try stripped versions
    api_stripped = _STRIP_PREFIXES.sub("", api_norm).strip()
    api_stripped = _STRIP_SUFFIXES.sub("", api_stripped).strip()
    if query_norm in api_stripped or api_stripped in query_norm:
        return True
    return False


def resolve_league(text: str) -> str:
    """Map free-text league mention to a canonical name."""
    t = text.lower()
    if any(w in t for w in ["premier", "epl", "english"]):
        return "Premier League"
    if any(w in t for w in ["la liga", "laliga", "spain", "pd"]):
        return "La Liga"
    if any(w in t for w in ["serie a", "italian", "italy"]):
        return "Serie A"
    if any(w in t for w in ["bundesliga", "german", "germany"]):
        return "Bundesliga"
    if any(w in t for w in ["ligue 1", "french", "france"]):
        return "Ligue 1"
    if any(w in t for w in ["super league", "greek", "greece"]):
        return "Super League"
    return text
