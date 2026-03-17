"""
Tests for rasa/actions/predictor.py

Run with: pytest tests/test_predictor.py -v
No Rasa server, no parquet files, no network required.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rasa" / "actions"))

import predictor as pred


# ---------------------------------------------------------------------------
# Βοηθητικές συναρτήσεις
# ---------------------------------------------------------------------------

def _stats(scored=1.5, conceded=1.2,
           scored_home=None, conceded_home=None,
           scored_away=None, conceded_away=None):
    d = {"avg_goals_scored": scored, "avg_goals_conceded": conceded}
    if scored_home is not None:
        d["avg_goals_scored_home"] = scored_home
        d["avg_goals_conceded_home"] = conceded_home
    if scored_away is not None:
        d["avg_goals_scored_away"] = scored_away
        d["avg_goals_conceded_away"] = conceded_away
    return d


# ---------------------------------------------------------------------------
# Δομή εξόδου
# ---------------------------------------------------------------------------

class TestPredictOutputStructure:
    def test_required_keys(self):
        result = pred.predict(_stats(), _stats())
        assert {"home_win_pct", "draw_pct", "away_win_pct",
                "home_xg", "away_xg",
                "most_likely_score", "most_likely_prob"}.issubset(result)

    def test_probabilities_sum_to_100(self):
        result = pred.predict(_stats(2.0, 1.0), _stats(1.5, 1.3))
        total = result["home_win_pct"] + result["draw_pct"] + result["away_win_pct"]
        assert abs(total - 100.0) < 1.0

    def test_xg_in_valid_range(self):
        result = pred.predict(_stats(), _stats())
        assert 0.1 <= result["home_xg"] <= 8.0
        assert 0.1 <= result["away_xg"] <= 8.0

    def test_most_likely_score_format(self):
        parts = pred.predict(_stats(), _stats())["most_likely_score"].split("-")
        assert len(parts) == 2 and all(p.isdigit() for p in parts)

    def test_most_likely_prob_positive(self):
        assert pred.predict(_stats(), _stats())["most_likely_prob"] > 0


# ---------------------------------------------------------------------------
# Παράμετρος league_avg
# ---------------------------------------------------------------------------

class TestPredictLeagueAvg:
    def test_none_falls_back_to_defaults(self):
        h, a = _stats(2.0, 1.2), _stats(1.4, 1.5)
        assert pred.predict(h, a, league="default") == pred.predict(h, a, league="default", league_avg=None)

    def test_explicit_value_changes_result(self):
        h, a = _stats(2.0, 1.0), _stats(1.5, 1.3)
        assert pred.predict(h, a, league_avg=2.2) != pred.predict(h, a, league_avg=3.2)

    def test_realistic_float_accepted(self):
        result = pred.predict(_stats(1.8, 1.1), _stats(1.3, 1.6),
                              league="premier_league", league_avg=2.756)
        assert isinstance(result["home_win_pct"], float)


# ---------------------------------------------------------------------------
# Δρομολόγηση home/away split
# ---------------------------------------------------------------------------

class TestPredictHomeAwaySplits:
    def test_split_path_differs_from_fallback(self):
        home_split = _stats(2.0, 1.0, scored_home=2.5, conceded_home=0.7)
        away_split = _stats(1.5, 1.3, scored_away=1.2, conceded_away=1.6)
        home_plain = _stats(2.0, 1.0)
        away_plain = _stats(1.5, 1.3)
        assert (pred.predict(home_split, away_split, league_avg=2.65) !=
                pred.predict(home_plain, away_plain, league_avg=2.65))

    def test_fallback_when_away_splits_missing(self):
        home = _stats(2.0, 1.0, scored_home=2.5, conceded_home=0.7)
        away = _stats(1.5, 1.3)  # no away splits
        result = pred.predict(home, away, league_avg=2.65)
        assert isinstance(result["home_win_pct"], float)

    def test_symmetric_overall_favours_home(self):
        s = _stats(1.5, 1.5)
        result = pred.predict(s, s, league_avg=2.65)
        assert result["home_win_pct"] > result["away_win_pct"]

    def test_symmetric_splits_nearly_equal(self):
        s = _stats(1.5, 1.5, scored_home=1.5, conceded_home=1.5,
                   scored_away=1.5, conceded_away=1.5)
        result = pred.predict(s, s, league_avg=2.65)
        assert abs(result["home_win_pct"] - result["away_win_pct"]) < 2.0


# ---------------------------------------------------------------------------
# Ακραίες τιμές εισόδου
# ---------------------------------------------------------------------------

class TestPredictExtremes:
    def test_dominant_home_team(self):
        # Το xG περιορίζεται στο 8.0 και το πλέγμα καλύπτει μόνο 0-7 γκολ,
        # οπότε η πιθανότητα είναι κομμένη· το key check είναι home win > away win.
        result = pred.predict(_stats(5.0, 0.5), _stats(0.5, 4.0))
        assert result["home_win_pct"] > result["away_win_pct"]
        assert result["home_win_pct"] > 40.0

    def test_very_defensive_xg_clamped(self):
        result = pred.predict(_stats(0.3, 0.3), _stats(0.3, 0.3))
        assert result["home_xg"] >= 0.1
        assert result["away_xg"] >= 0.1

    def test_probabilities_always_non_negative(self):
        for s in [0.3, 1.0, 3.5]:
            for c in [0.3, 1.0, 3.5]:
                r = pred.predict(_stats(s, c), _stats(s, c))
                assert r["home_win_pct"] >= 0
                assert r["draw_pct"] >= 0
                assert r["away_win_pct"] >= 0


# ---------------------------------------------------------------------------
# format_form()
# (μορφοποίηση φόρμας)
# ---------------------------------------------------------------------------

class TestFormatForm:
    def test_win_icon(self):
        assert "✅" in pred.format_form(["W"])

    def test_loss_icon(self):
        assert "❌" in pred.format_form(["L"])

    def test_draw_icon(self):
        assert "⬜" in pred.format_form(["D"])

    def test_empty(self):
        assert pred.format_form([]) == ""

    def test_unknown_code_passes_through(self):
        assert "X" in pred.format_form(["X"])

    def test_space_separated(self):
        assert len(pred.format_form(["W", "D", "L"]).split(" ")) == 3


# ---------------------------------------------------------------------------
# Έλεγχος ορθότητας LEAGUE_AVG_DEFAULTS
# ---------------------------------------------------------------------------

class TestLeagueAvgDefaults:
    def test_default_key_exists(self):
        assert "default" in pred.LEAGUE_AVG_DEFAULTS

    def test_all_values_positive(self):
        for k, v in pred.LEAGUE_AVG_DEFAULTS.items():
            assert v > 0, f"Non-positive for '{k}': {v}"

    def test_values_in_realistic_range(self):
        for k, v in pred.LEAGUE_AVG_DEFAULTS.items():
            assert 1.5 <= v <= 5.0, f"Unrealistic for '{k}': {v}"
