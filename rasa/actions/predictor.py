"""
Poisson distribution match prediction engine.
Used by professional betting services — predicts match outcomes from team
average goals scored/conceded vs the league average.
"""

from typing import Dict, Optional, Tuple
import math

# Δοκιμή scipy πρώτα· fallback σε pure-Python Poisson PMF αν δεν είναι εγκατεστημένο
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


# Προεπιλεγμένοι μέσοι όροι πρωταθλήματος (γκολ ανά αγώνα) όταν δεν υπάρχουν πραγματικά δεδομένα
LEAGUE_AVG_DEFAULTS: Dict[str, float] = {
    "premier league": 2.65,
    "la liga": 2.55,
    "serie a": 2.60,
    "bundesliga": 2.95,
    "ligue 1": 2.50,
    "super league": 2.40,
    "default": 2.65,
}

MAX_GOALS = 7          # μέγεθος πλέγματος: 0..MAX_GOALS για κάθε ομάδα
HOME_ADVANTAGE = 1.20  # τυπικός πολλαπλασιαστής πλεονεκτήματος έδρας


def predict(
    home_stats: Dict,
    away_stats: Dict,
    league: str = "default",
    league_avg: Optional[float] = None,
) -> Dict:
    """
    Run Poisson prediction for a home vs away matchup.

    Args:
        home_stats: dict with 'avg_goals_scored' and 'avg_goals_conceded' (required).
                    Optionally: 'avg_goals_scored_home', 'avg_goals_conceded_home'
                    for venue-aware prediction.
        away_stats: dict with 'avg_goals_scored' and 'avg_goals_conceded' (required).
                    Optionally: 'avg_goals_scored_away', 'avg_goals_conceded_away'.
        league:     league slug/name for LEAGUE_AVG_DEFAULTS lookup (used only if
                    league_avg is None).
        league_avg: Real computed goals-per-match average for the league. If provided,
                    overrides the LEAGUE_AVG_DEFAULTS lookup.

    Returns:
        dict with home_win_pct, draw_pct, away_win_pct, home_xg, away_xg,
             most_likely_score, most_likely_prob
    """
    if league_avg is None:
        league_avg = LEAGUE_AVG_DEFAULTS.get(league.lower(), LEAGUE_AVG_DEFAULTS["default"])

    # Χρήση στατιστικών ανά έδρα όταν υπάρχουν και τα τέσσερα split keys.
    # Ο πολλαπλασιαστής HOME_ADVANTAGE ΔΕΝ εφαρμόζεται εδώ — το venue effect
    # είναι ήδη ενσωματωμένο στους μέσους όρους home/away split.
    _has_splits = (
        home_stats.get("avg_goals_scored_home") is not None
        and home_stats.get("avg_goals_conceded_home") is not None
        and away_stats.get("avg_goals_scored_away") is not None
        and away_stats.get("avg_goals_conceded_away") is not None
    )

    if _has_splits:
        home_xg = (
            (home_stats["avg_goals_scored_home"] / league_avg)
            * (away_stats["avg_goals_conceded_away"] / league_avg)
            * league_avg
        )
        away_xg = (
            (away_stats["avg_goals_scored_away"] / league_avg)
            * (home_stats["avg_goals_conceded_home"] / league_avg)
            * league_avg
        )
    else:
        # Fallback: συνολικοί μέσοι όροι + πολλαπλασιαστής HOME_ADVANTAGE
        home_attack  = home_stats["avg_goals_scored"]  / league_avg
        home_defense = home_stats["avg_goals_conceded"] / league_avg
        away_attack  = away_stats["avg_goals_scored"]  / league_avg
        away_defense = away_stats["avg_goals_conceded"] / league_avg
        home_xg = home_attack * away_defense * league_avg * HOME_ADVANTAGE
        away_xg = away_attack * home_defense * league_avg

    # Περιορισμός σε λογικό εύρος
    home_xg = max(0.1, min(home_xg, 8.0))
    away_xg  = max(0.1, min(away_xg, 8.0))

    # Κατασκευή πλέγματος πιθανοτήτων
    grid: Dict[Tuple[int, int], float] = {}
    for hg in range(MAX_GOALS + 1):
        for ag in range(MAX_GOALS + 1):
            grid[(hg, ag)] = _pmf(hg, home_xg) * _pmf(ag, away_xg)

    home_win_pct = sum(p for (hg, ag), p in grid.items() if hg > ag)
    draw_pct     = sum(p for (hg, ag), p in grid.items() if hg == ag)
    away_win_pct = sum(p for (hg, ag), p in grid.items() if hg < ag)

    # Πιο πιθανό αποτέλεσμα
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
