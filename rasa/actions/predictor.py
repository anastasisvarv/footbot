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

# Ποσοστό των τερμάτων ενός αγώνα που σημειώνει κατά μέσο όρο η γηπεδούχος.
# Χρησιμοποιείται μόνο ως εφεδρεία, όταν δεν δίνονται πραγματικοί μέσοι όροι
# γηπεδούχου/φιλοξενούμενης. Τιμή από τα δεδομένα των έξι πρωταθλημάτων.
HOME_GOAL_SHARE = 0.545


def predict(
    home_stats: Dict,
    away_stats: Dict,
    league: str = "default",
    league_avg: Optional[float] = None,
    league_home_avg: Optional[float] = None,
    league_away_avg: Optional[float] = None,
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
        league_avg: Real computed goals-per-match average for the league (both teams
                    combined). If provided, overrides the LEAGUE_AVG_DEFAULTS lookup.
        league_home_avg: League average goals scored by the HOME team per match.
        league_away_avg: League average goals scored by the AWAY team per match.
                    When both are given they are used as the normalisers for the
                    strength indices; otherwise they are derived from league_avg
                    using HOME_GOAL_SHARE.

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

    # Οι δείκτες ισχύος πρέπει να κανονικοποιούνται με μέσο όρο ΑΝΑ ΟΜΑΔΑ, όχι με
    # τον συνολικό μέσο όρο τερμάτων ανά αγώνα (που αφορά και τις δύο ομάδες μαζί).
    # Για τα venue splits ο σωστός παρονομαστής είναι ο μέσος όρος τερμάτων της
    # γηπεδούχου (Lh) για το λ της γηπεδούχου και της φιλοξενούμενης (La) για το λ
    # της φιλοξενούμενης. Σημειώνεται ότι τα τέρματα που δέχεται η φιλοξενούμενη
    # εκτός έδρας αντιστοιχούν στα τέρματα που σημειώνουν οι γηπεδούχοι, άρα
    # κανονικοποιούνται επίσης με Lh (και αντιστρόφως).
    if league_home_avg is not None and league_away_avg is not None:
        Lh, La = league_home_avg, league_away_avg
    else:
        Lh = league_avg * HOME_GOAL_SHARE
        La = league_avg * (1.0 - HOME_GOAL_SHARE)

    if _has_splits:
        home_attack  = home_stats["avg_goals_scored_home"]   / Lh
        away_defense = away_stats["avg_goals_conceded_away"] / Lh
        home_xg = home_attack * away_defense * Lh

        away_attack  = away_stats["avg_goals_scored_away"]    / La
        home_defense = home_stats["avg_goals_conceded_home"]  / La
        away_xg = away_attack * home_defense * La
    else:
        # Fallback: συνολικοί μέσοι όροι, κανονικοποιημένοι με τον μέσο όρο ανά
        # ομάδα, συν ρητός πολλαπλασιαστής πλεονεκτήματος έδρας.
        per_team = league_avg / 2.0
        home_attack  = home_stats["avg_goals_scored"]   / per_team
        home_defense = home_stats["avg_goals_conceded"] / per_team
        away_attack  = away_stats["avg_goals_scored"]   / per_team
        away_defense = away_stats["avg_goals_conceded"] / per_team
        home_xg = home_attack * away_defense * per_team * HOME_ADVANTAGE
        away_xg = away_attack * home_defense * per_team

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
