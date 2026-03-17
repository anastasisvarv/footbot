"""
DataRepository — loads all football data from local parquet/json files
and provides query helpers for Rasa custom actions.

All data is read once from disk on first access and cached in memory.
No live HTTP calls are made — run `python -m pipeline update` to refresh data.

Usage (inside a Rasa action):
    from .data_repository import DataRepository

    repo = DataRepository.get()           # singleton; safe to call on every action
    stats = repo.get_team_stats("Liverpool")
    table = repo.get_standings("Premier League")
"""
from __future__ import annotations

import json
import logging
from difflib import get_close_matches
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Resolve data/ relative to the project root (two levels up from this file: actions/ → rasa/ → footbot/)
_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _ROOT / "data"

# ---------------------------------------------------------------------------
# League name → internal slug mapping
# ---------------------------------------------------------------------------

_LEAGUE_ALIASES: Dict[str, str] = {
    # Slug format (already resolved — passed in from actions after first resolve())
    "premier_league":                "premier_league",
    "la_liga":                       "la_liga",
    "serie_a":                       "serie_a",
    "bundesliga":                    "bundesliga",
    "ligue_1":                       "ligue_1",
    "super_league_greece":           "super_league_greece",
    # Premier League
    "premier league":                "premier_league",
    "english premier league":        "premier_league",
    "epl":                           "premier_league",
    "pl":                            "premier_league",
    "barclays premier league":       "premier_league",
    "england":                       "premier_league",
    # La Liga
    "la liga":                       "la_liga",
    "laliga":                        "la_liga",
    "primera division":              "la_liga",
    "spanish league":                "la_liga",
    "spain":                         "la_liga",
    # Serie A
    "serie a":                       "serie_a",
    "italian league":                "serie_a",
    "calcio":                        "serie_a",
    "italy":                         "serie_a",
    # Bundesliga
    "bundesliga":                    "bundesliga",
    "german league":                 "bundesliga",
    "germany":                       "bundesliga",
    # Ligue 1
    "ligue 1":                       "ligue_1",
    "ligue1":                        "ligue_1",
    "french league":                 "ligue_1",
    "france":                        "ligue_1",
    # Super League Greece
    "super league":                  "super_league_greece",
    "super league greece":           "super_league_greece",
    "greek super league":            "super_league_greece",
    "greek league":                  "super_league_greece",
    "greece":                        "super_league_greece",
}

_LEAGUE_DISPLAY: Dict[str, str] = {
    "premier_league":       "Premier League",
    "la_liga":              "La Liga",
    "serie_a":              "Serie A",
    "bundesliga":           "Bundesliga",
    "ligue_1":              "Ligue 1",
    "super_league_greece":  "Super League Greece",
}


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class DataRepository:
    """
    Singleton data store.  Call ``DataRepository.get()`` rather than
    constructing directly — this avoids re-reading files on every action.
    """

    _instance: Optional["DataRepository"] = None

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        self._data_dir: Path = data_dir or _DATA_DIR

        # league_slug → DataFrame (all seasons combined, sorted newest-first)
        self._matches: Dict[str, pd.DataFrame] = {}

        # league_slug → DataFrame (most-recent season's standings only)
        self._standings: Dict[str, pd.DataFrame] = {}

        # lower-cased alias → canonical team name
        self._alias_map: Dict[str, str] = {}

        self._load_all()

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def get(cls, data_dir: Optional[Path] = None) -> "DataRepository":
        """Return the shared singleton, creating it on first call."""
        if cls._instance is None:
            cls._instance = cls(data_dir)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Force a full reload on the next call to get() (useful after pipeline update)."""
        cls._instance = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_all(self) -> None:
        if not self._data_dir.exists():
            logger.warning(
                "Data directory %s not found. Run: python -m pipeline update",
                self._data_dir,
            )
            return

        for league_dir in sorted(self._data_dir.iterdir()):
            if not league_dir.is_dir():
                continue
            slug = league_dir.name
            seasons = sorted(
                [p.name for p in league_dir.iterdir() if p.is_dir()],
                reverse=True,
            )
            if not seasons:
                continue

            # Matches — merge all seasons, newest first
            season_frames: List[pd.DataFrame] = []
            for season in seasons:
                matches_path = league_dir / season / "matches.parquet"
                if matches_path.exists():
                    df = pd.read_parquet(matches_path)
                    df["league"] = slug
                    df["season"] = season
                    season_frames.append(df)

                # Team aliases — accumulate from all seasons
                teams_path = league_dir / season / "teams.json"
                if teams_path.exists():
                    self._load_teams_file(teams_path)

            if season_frames:
                combined = pd.concat(season_frames, ignore_index=True)
                combined["date"] = pd.to_datetime(combined["date"], errors="coerce")
                combined = combined.sort_values("date", ascending=False).reset_index(drop=True)
                self._matches[slug] = combined

            # Standings — most recent season only
            standings_path = league_dir / seasons[0] / "standings.parquet"
            if standings_path.exists():
                self._standings[slug] = pd.read_parquet(standings_path)

        total_matches = sum(len(df) for df in self._matches.values())
        logger.info(
            "DataRepository loaded — leagues: %s  total matches: %d",
            list(self._matches.keys()),
            total_matches,
        )

    def _load_teams_file(self, path: Path) -> None:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for entry in data.get("teams", []):
                canonical = entry["canonical"]
                self._alias_map[canonical.lower()] = canonical
                for alias in entry.get("aliases", []):
                    self._alias_map[alias.lower()] = canonical
        except Exception as exc:
            logger.warning("Could not load teams from %s: %s", path, exc)

    # ------------------------------------------------------------------
    # Name resolution
    # ------------------------------------------------------------------

    def resolve_team(self, name: str) -> Optional[str]:
        """
        Return the canonical team name for a user-supplied query string.
        Tries exact/alias lookup first, then fuzzy matching, then substring.
        Returns None if no confident match is found.
        """
        key = name.strip().lower()

        # 1. Direct / alias lookup
        if key in self._alias_map:
            return self._alias_map[key]

        # 2. Fuzzy match (cutoff = 0.6 gives reasonable tolerance)
        candidates = list(self._alias_map.keys())
        close = get_close_matches(key, candidates, n=1, cutoff=0.6)
        if close:
            return self._alias_map[close[0]]

        # 3. Substring fallback
        for alias, canonical in self._alias_map.items():
            if key in alias or alias in key:
                return canonical

        return None

    def resolve_league(self, text: str) -> Optional[str]:
        """
        Map free-text league mention to an internal slug.
        Handles both exact keys (e.g. "ligue 1") and substrings (e.g. "french").
        """
        t = text.strip().lower()
        # Exact match
        if t in _LEAGUE_ALIASES:
            return _LEAGUE_ALIASES[t]
        # Substring match
        return next(
            (slug for kw, slug in _LEAGUE_ALIASES.items() if kw in t),
            None,
        )

    def league_display_name(self, slug: str) -> str:
        return _LEAGUE_DISPLAY.get(slug, slug.replace("_", " ").title())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_team_matches(self, canonical: str, n: int = 20) -> pd.DataFrame:
        """Return up to *n* completed matches for *canonical*, newest first."""
        name_lower = canonical.lower()
        frames: List[pd.DataFrame] = []
        for df in self._matches.values():
            mask = (
                df["home_team"].str.lower() == name_lower
            ) | (
                df["away_team"].str.lower() == name_lower
            )
            frames.append(df[mask])
        if not frames:
            return pd.DataFrame()
        combined = pd.concat(frames, ignore_index=True)
        combined = combined.sort_values("date", ascending=False).reset_index(drop=True)
        return combined.head(n)

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    @staticmethod
    def _weighted_avg(values: List[float], decay: float = 0.85) -> float:
        """Exponential decay weighted mean. Index 0 = most recent (weight 1.0)."""
        if not values:
            return 0.0
        weights = [decay ** i for i in range(len(values))]
        total_w = sum(weights)
        return round(sum(v * w for v, w in zip(values, weights)) / total_w, 2)

    def get_team_stats(self, team: str) -> Optional[Dict]:
        """
        Return aggregated stats for a team based on its last 38 matches (full-season window).

        Return dict keys:
            team, played, won, drawn, lost,
            avg_goals_scored, avg_goals_conceded,        ← exponential decay weighted
            avg_goals_scored_home, avg_goals_scored_away,
            avg_goals_conceded_home, avg_goals_conceded_away,
            home_played, away_played,
            league  (primary league slug),
            form (list of "W"/"D"/"L", last 5),
            recent_matches (list of match dicts, last 5)
        Returns None if the team is unknown or has no match data.
        """
        canonical = self.resolve_team(team)
        if not canonical:
            logger.warning("Team not found in alias map: '%s'", team)
            return None

        matches = self._get_team_matches(canonical, n=38)
        if matches.empty:
            logger.warning("No matches found for '%s' (canonical: %s)", team, canonical)
            return None

        name_lower = canonical.lower()
        goals_scored: List[float] = []
        goals_conceded: List[float] = []
        goals_scored_home: List[float] = []
        goals_scored_away: List[float] = []
        goals_conceded_home: List[float] = []
        goals_conceded_away: List[float] = []
        results: List[str] = []
        recent: List[Dict] = []
        league_counts: Dict[str, int] = {}

        for _, row in matches.iterrows():
            if pd.isna(row.get("home_goals")) or pd.isna(row.get("away_goals")):
                continue
            hg = int(row["home_goals"])
            ag = int(row["away_goals"])
            is_home = row["home_team"].lower() == name_lower
            gf = hg if is_home else ag
            ga = ag if is_home else hg

            goals_scored.append(float(gf))
            goals_conceded.append(float(ga))
            results.append("W" if gf > ga else ("D" if gf == ga else "L"))

            if is_home:
                goals_scored_home.append(float(gf))
                goals_conceded_home.append(float(ga))
            else:
                goals_scored_away.append(float(gf))
                goals_conceded_away.append(float(ga))

            league_slug = row.get("league", "")
            league_counts[league_slug] = league_counts.get(league_slug, 0) + 1

            date_str = str(row["date"].date()) if pd.notna(row["date"]) else ""
            recent.append({
                "date":        date_str,
                "home_team":   row["home_team"],
                "away_team":   row["away_team"],
                "home_goals":  hg,
                "away_goals":  ag,
                "competition": self.league_display_name(league_slug),
            })

        if not results:
            return None

        n_played = len(results)
        primary_league = max(league_counts, key=league_counts.get) if league_counts else ""

        return {
            "team":               canonical,
            "played":             n_played,
            "won":                results.count("W"),
            "drawn":              results.count("D"),
            "lost":               results.count("L"),
            "avg_goals_scored":   self._weighted_avg(goals_scored),
            "avg_goals_conceded": self._weighted_avg(goals_conceded),
            "avg_goals_scored_home":   self._weighted_avg(goals_scored_home) if goals_scored_home else None,
            "avg_goals_scored_away":   self._weighted_avg(goals_scored_away) if goals_scored_away else None,
            "avg_goals_conceded_home": self._weighted_avg(goals_conceded_home) if goals_conceded_home else None,
            "avg_goals_conceded_away": self._weighted_avg(goals_conceded_away) if goals_conceded_away else None,
            "home_played":        len(goals_scored_home),
            "away_played":        len(goals_scored_away),
            "league":             primary_league,
            "form":               results[:5],
            "recent_matches":     recent[:5],
        }

    def get_standings(self, league: str) -> List[Dict]:
        """
        Return standings rows for a league.

        Return format (compatible with legacy football_data.get_standings):
            [{"position", "team", "points", "played", "won", "draw", "drawn",
              "lost", "gf", "ga", "gd"}, ...]
        Returns [] if no data is available.
        """
        slug = self.resolve_league(league)
        if not slug:
            logger.warning("League not resolved from: '%s'", league)
            return []

        df = self._standings.get(slug)
        if df is None or df.empty:
            logger.warning("No standings data for slug '%s'", slug)
            return []

        rows: List[Dict] = []
        for position, (_, r) in enumerate(df.iterrows(), start=1):
            rows.append({
                "position": position,
                "team":     r["team"],
                "points":   int(r["points"]),
                "played":   int(r["MP"]),
                "won":      int(r["W"]),
                "draw":     int(r["D"]),   # legacy key used by actions.py
                "drawn":    int(r["D"]),
                "lost":     int(r["L"]),
                "gf":       int(r["GF"]),
                "ga":       int(r["GA"]),
                "gd":       int(r["GD"]),
            })
        return rows

    def get_league_avg_goals(self, slug: str) -> Optional[float]:
        """
        Compute goals-per-match for a league from the most recent season's data.

        Uses only the most recent season (most representative of current tempo).
        Returns None if fewer than 10 completed matches are available so that
        callers can fall back to LEAGUE_AVG_DEFAULTS.
        """
        df = self._matches.get(slug)
        if df is None or df.empty:
            return None

        most_recent_season = df["season"].iloc[0]
        season_df = df[df["season"] == most_recent_season]
        completed = season_df.dropna(subset=["home_goals", "away_goals"])

        if len(completed) < 10:
            logger.info(
                "League '%s': only %d completed matches this season — falling back to default avg",
                slug, len(completed),
            )
            return None

        total_goals = int((completed["home_goals"] + completed["away_goals"]).sum())
        return round(total_goals / len(completed), 3)

    def get_recent_form(self, team: str, n: int = 5) -> List[Dict]:
        """
        Return the last *n* match results for a team.

        Each dict: {date, opponent, home_or_away, score, result}
        """
        canonical = self.resolve_team(team)
        if not canonical:
            return []

        matches = self._get_team_matches(canonical, n=n)
        name_lower = canonical.lower()
        form: List[Dict] = []

        for _, row in matches.iterrows():
            if pd.isna(row.get("home_goals")) or pd.isna(row.get("away_goals")):
                continue
            hg = int(row["home_goals"])
            ag = int(row["away_goals"])
            is_home = row["home_team"].lower() == name_lower
            gf = hg if is_home else ag
            ga = ag if is_home else hg
            opp = row["away_team"] if is_home else row["home_team"]
            date_str = str(row["date"].date()) if pd.notna(row["date"]) else ""
            form.append({
                "date":         date_str,
                "opponent":     opp,
                "home_or_away": "H" if is_home else "A",
                "score":        f"{gf}-{ga}",
                "result":       "W" if gf > ga else ("D" if gf == ga else "L"),
            })

        return form

    def get_head_to_head(self, team1: str, team2: str, n: int = 10) -> Optional[Dict]:
        """
        Return H2H record between two teams from all stored matches.

        Return format (compatible with legacy football_data.get_head_to_head):
            {team1, team2, matches_found, team1_wins, team2_wins, draws, recent_h2h}
        Returns None if either team is unknown or no H2H matches exist.
        """
        can1 = self.resolve_team(team1)
        can2 = self.resolve_team(team2)
        if not can1 or not can2:
            logger.warning("H2H: could not resolve '%s' or '%s'", team1, team2)
            return None

        t1l, t2l = can1.lower(), can2.lower()
        frames: List[pd.DataFrame] = []
        for df in self._matches.values():
            mask = (
                (df["home_team"].str.lower() == t1l) & (df["away_team"].str.lower() == t2l)
            ) | (
                (df["home_team"].str.lower() == t2l) & (df["away_team"].str.lower() == t1l)
            )
            frames.append(df[mask])

        if not frames:
            return None

        h2h_df = (
            pd.concat(frames, ignore_index=True)
            .sort_values("date", ascending=False)
            .head(n)
        )
        if h2h_df.empty:
            return None

        t1_wins = t2_wins = draws = 0
        recent_h2h: List[Dict] = []

        for _, row in h2h_df.iterrows():
            if pd.isna(row.get("home_goals")) or pd.isna(row.get("away_goals")):
                continue
            hg = int(row["home_goals"])
            ag = int(row["away_goals"])
            t1_home = row["home_team"].lower() == t1l
            date_str = str(row["date"].date()) if pd.notna(row["date"]) else ""

            if hg == ag:
                draws += 1
            elif (t1_home and hg > ag) or (not t1_home and ag > hg):
                t1_wins += 1
            else:
                t2_wins += 1

            recent_h2h.append({
                "date":       date_str,
                "home_team":  row["home_team"],
                "away_team":  row["away_team"],
                "home_goals": hg,
                "away_goals": ag,
            })

        return {
            "team1":         can1,
            "team2":         can2,
            "matches_found": len(h2h_df),
            "team1_wins":    t1_wins,
            "team2_wins":    t2_wins,
            "draws":         draws,
            "recent_h2h":    recent_h2h[:5],
        }

    @property
    def is_empty(self) -> bool:
        """True if no data has been loaded (pipeline has not run yet)."""
        return not self._matches and not self._standings
