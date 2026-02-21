"""
Poisson distribution match prediction engine.
Used by professional betting services — predicts match outcomes from team
average goals scored/conceded vs the league average.
"""

from typing import Dict, Optional, Tuple
import math

# Try scipy first; fall back to pure-Python Poisson PMF if not installed
try:
    from scipy.stats import poisson as _scipy_poisson

    def _pmf(k: int, lam: float) -> float:
        return float(_scipy_poisson.pmf(k, lam))

except ImportError:
    def _pmf(k: int, lam: float) -> float:
        """Pure-Python Poisson PMF: e^(-λ) * λ^k / k!"""
        if lam <= 0:
            return 1.0 if k == 0 else 0.0
        return math.exp(-lam) * (lam ** k) / math.factorial(k)


# Default league averages (goals per match) used when real data unavailable
LEAGUE_AVG_DEFAULTS: Dict[str, float] = {
    "premier league": 2.65,
    "la liga": 2.55,
    "serie a": 2.60,
    "bundesliga": 2.95,
    "ligue 1": 2.50,
    "super league": 2.40,
    "default": 2.65,
}

MAX_GOALS = 7          # grid size: 0..MAX_GOALS for each team
HOME_ADVANTAGE = 1.20  # standard home advantage multiplier


def predict(
    home_stats: Dict,
    away_stats: Dict,
    league: str = "default",
) -> Dict:
    """
    Run Poisson prediction for a home vs away matchup.

    Args:
        home_stats: dict with 'avg_goals_scored' and 'avg_goals_conceded'
        away_stats: dict with 'avg_goals_scored' and 'avg_goals_conceded'
        league:     league name for avg lookup

    Returns:
        dict with home_win_pct, draw_pct, away_win_pct, home_xg, away_xg,
             most_likely_score, scoreline_grid
    """
    league_avg = LEAGUE_AVG_DEFAULTS.get(league.lower(), LEAGUE_AVG_DEFAULTS["default"])

    home_attack  = home_stats["avg_goals_scored"]  / league_avg
    home_defense = home_stats["avg_goals_conceded"] / league_avg
    away_attack  = away_stats["avg_goals_scored"]  / league_avg
    away_defense = away_stats["avg_goals_conceded"] / league_avg

    # Expected goals (xG)
    home_xg = home_attack * away_defense * league_avg * HOME_ADVANTAGE
    away_xg = away_attack * home_defense * league_avg

    # Clamp to reasonable range
    home_xg = max(0.1, min(home_xg, 8.0))
    away_xg  = max(0.1, min(away_xg, 8.0))

    # Build probability grid
    grid: Dict[Tuple[int, int], float] = {}
    for hg in range(MAX_GOALS + 1):
        for ag in range(MAX_GOALS + 1):
            grid[(hg, ag)] = _pmf(hg, home_xg) * _pmf(ag, away_xg)

    home_win_pct = sum(p for (hg, ag), p in grid.items() if hg > ag)
    draw_pct     = sum(p for (hg, ag), p in grid.items() if hg == ag)
    away_win_pct = sum(p for (hg, ag), p in grid.items() if hg < ag)

    # Most likely scoreline
    most_likely_score = max(grid, key=grid.get)

    return {
        "home_win_pct": round(home_win_pct * 100, 1),
        "draw_pct":     round(draw_pct * 100, 1),
        "away_win_pct": round(away_win_pct * 100, 1),
        "home_xg":      round(home_xg, 2),
        "away_xg":      round(away_xg, 2),
        "most_likely_score": f"{most_likely_score[0]}-{most_likely_score[1]}",
        "most_likely_prob":  round(grid[most_likely_score] * 100, 1),
    }


def format_form(form: list) -> str:
    """Convert form list to visual string e.g. ['W','D','L'] → 'W D L'"""
    icons = {"W": "✅", "D": "⬜", "L": "❌"}
    return " ".join(icons.get(r, r) for r in form)
