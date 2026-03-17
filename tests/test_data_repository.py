"""
Tests for rasa/actions/data_repository.py

Run with: pytest tests/test_data_repository.py -v
Fully offline — no parquet files needed. DataFrames are injected directly.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rasa" / "actions"))

from data_repository import DataRepository


# ---------------------------------------------------------------------------
# Fixtures (δεδομένα δοκιμής)
# ---------------------------------------------------------------------------

def _make_matches(rows, league, season="2025-2026"):
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["home_goals"] = pd.array(df["home_goals"], dtype="Int64")
    df["away_goals"] = pd.array(df["away_goals"], dtype="Int64")
    df["league"] = league
    df["season"] = season
    return df.sort_values("date", ascending=False).reset_index(drop=True)


@pytest.fixture(autouse=True)
def reset_singleton():
    DataRepository.reset()
    yield
    DataRepository.reset()


@pytest.fixture()
def repo(tmp_path):
    return DataRepository(data_dir=tmp_path)


# ---------------------------------------------------------------------------
# resolve_team() (επίλυση ονόματος ομάδας)
# ---------------------------------------------------------------------------

class TestResolveTeam:
    def test_exact(self, repo):
        repo._alias_map["liverpool"] = "Liverpool"
        assert repo.resolve_team("Liverpool") == "Liverpool"

    def test_case_insensitive(self, repo):
        repo._alias_map["liverpool"] = "Liverpool"
        assert repo.resolve_team("LIVERPOOL") == "Liverpool"

    def test_alias(self, repo):
        repo._alias_map["liverpool"] = "Liverpool"
        repo._alias_map["the reds"] = "Liverpool"
        assert repo.resolve_team("The Reds") == "Liverpool"

    def test_fuzzy(self, repo):
        repo._alias_map["liverpool"] = "Liverpool"
        assert repo.resolve_team("liverpol") == "Liverpool"

    def test_substring_fallback(self, repo):
        repo._alias_map["manchester city"] = "Manchester City"
        assert repo.resolve_team("man city") == "Manchester City"

    def test_unknown_returns_none(self, repo):
        assert repo.resolve_team("Nonexistent FC") is None


# ---------------------------------------------------------------------------
# resolve_league() (επίλυση ονόματος πρωταθλήματος)
# ---------------------------------------------------------------------------

class TestResolveLeague:
    def test_display_name(self, repo):
        assert repo.resolve_league("premier league") == "premier_league"

    def test_abbreviation(self, repo):
        assert repo.resolve_league("EPL") == "premier_league"

    def test_slug_passthrough(self, repo):
        assert repo.resolve_league("premier_league") == "premier_league"

    def test_country_name(self, repo):
        assert repo.resolve_league("england") == "premier_league"

    def test_la_liga(self, repo):
        assert repo.resolve_league("La Liga") == "la_liga"

    def test_bundesliga(self, repo):
        assert repo.resolve_league("Bundesliga") == "bundesliga"

    def test_unknown_returns_none(self, repo):
        assert repo.resolve_league("Scottish Premiership") is None


# ---------------------------------------------------------------------------
# get_league_avg_goals() (μέσος όρος γκολ πρωταθλήματος)
# ---------------------------------------------------------------------------

class TestGetLeagueAvgGoals:
    def test_correct_average(self, repo):
        # 4 αγώνες: 2+1, 1+1, 3+0, 0+2 → 10 γκολ / 4 = 2.5
        rows = [
            {"date": "2025-09-01", "home_team": "A", "away_team": "B", "home_goals": 2, "away_goals": 1},
            {"date": "2025-09-08", "home_team": "C", "away_team": "D", "home_goals": 1, "away_goals": 1},
            {"date": "2025-09-15", "home_team": "A", "away_team": "C", "home_goals": 3, "away_goals": 0},
            {"date": "2025-09-22", "home_team": "B", "away_team": "D", "home_goals": 0, "away_goals": 2},
        ] * 3  # 12 γραμμές → πάνω από το όριο των 10 αγώνων
        repo._matches["premier_league"] = _make_matches(rows, "premier_league")
        assert repo.get_league_avg_goals("premier_league") == pytest.approx(2.5, abs=0.01)

    def test_unknown_league_returns_none(self, repo):
        assert repo.get_league_avg_goals("scottish_premiership") is None

    def test_below_threshold_returns_none(self, repo):
        rows = [
            {"date": f"2025-09-0{i}", "home_team": "A", "away_team": "B",
             "home_goals": 1, "away_goals": 1}
            for i in range(1, 6)  # μόνο 5 αγώνες
        ]
        repo._matches["premier_league"] = _make_matches(rows, "premier_league")
        assert repo.get_league_avg_goals("premier_league") is None

    def test_uses_most_recent_season(self, repo):
        old = _make_matches(
            [{"date": f"2024-09-{i:02d}", "home_team": "A", "away_team": "B",
              "home_goals": 1, "away_goals": 0} for i in range(1, 13)],
            "premier_league", season="2024-2025",
        )
        new = _make_matches(
            [{"date": f"2025-09-{i:02d}", "home_team": "A", "away_team": "B",
              "home_goals": 3, "away_goals": 0} for i in range(1, 13)],
            "premier_league", season="2025-2026",
        )
        combined = pd.concat([new, old], ignore_index=True).sort_values(
            "date", ascending=False).reset_index(drop=True)
        repo._matches["premier_league"] = combined
        # Πιο πρόσφατη σεζόν: 3 γκολ/αγώνα
        assert repo.get_league_avg_goals("premier_league") == pytest.approx(3.0, abs=0.01)

    def test_ignores_null_rows(self, repo):
        # Ανάμειξη ολοκληρωμένων + null γραμμών
        rows = (
            [{"date": "2025-09-01", "home_team": "A", "away_team": "B",
              "home_goals": 2, "away_goals": 1}] * 8
            + [{"date": "2025-09-15", "home_team": "C", "away_team": "D",
                "home_goals": None, "away_goals": None}] * 4
        )
        repo._matches["premier_league"] = _make_matches(rows, "premier_league")
        # 8 ολοκληρωμένοι → κάτω από το όριο των 10 αγώνων
        assert repo.get_league_avg_goals("premier_league") is None


# ---------------------------------------------------------------------------
# get_team_stats() — νέα πεδία
# ---------------------------------------------------------------------------

def _inject_team_matches(repo):
    """10 νίκες εντός έδρας (2-1) + 10 ισοπαλίες εκτός (1-1) για Liverpool."""
    home_rows = [
        {"date": f"2025-{m:02d}-01", "home_team": "Liverpool", "away_team": "Arsenal",
         "home_goals": 2, "away_goals": 1}
        for m in range(1, 11)
    ]
    away_rows = [
        {"date": f"2025-{m:02d}-15", "home_team": "Arsenal", "away_team": "Liverpool",
         "home_goals": 1, "away_goals": 1}
        for m in range(1, 11)
    ]
    repo._matches["premier_league"] = _make_matches(home_rows + away_rows, "premier_league")
    repo._alias_map["liverpool"] = "Liverpool"


class TestGetTeamStatsNewFields:
    def test_league_field(self, repo):
        _inject_team_matches(repo)
        stats = repo.get_team_stats("Liverpool")
        assert stats["league"] == "premier_league"

    def test_home_away_split_keys_present(self, repo):
        _inject_team_matches(repo)
        stats = repo.get_team_stats("Liverpool")
        for key in ("avg_goals_scored_home", "avg_goals_scored_away",
                    "avg_goals_conceded_home", "avg_goals_conceded_away"):
            assert stats[key] is not None, f"{key} should not be None"

    def test_home_played_away_played(self, repo):
        _inject_team_matches(repo)
        stats = repo.get_team_stats("Liverpool")
        assert stats["home_played"] == 10
        assert stats["away_played"] == 10

    def test_split_values_correct(self, repo):
        _inject_team_matches(repo)
        stats = repo.get_team_stats("Liverpool")
        # Όλοι οι εντός έδρας αγώνες: 2 γκολ, 1 δεχτός
        assert stats["avg_goals_scored_home"] == pytest.approx(2.0, abs=0.01)
        assert stats["avg_goals_conceded_home"] == pytest.approx(1.0, abs=0.01)
        # Όλοι οι εκτός έδρας αγώνες: 1 γκολ, 1 δεχτός
        assert stats["avg_goals_scored_away"] == pytest.approx(1.0, abs=0.01)
        assert stats["avg_goals_conceded_away"] == pytest.approx(1.0, abs=0.01)

    def test_backward_compat_keys(self, repo):
        _inject_team_matches(repo)
        stats = repo.get_team_stats("Liverpool")
        for key in ("team", "played", "won", "drawn", "lost",
                    "avg_goals_scored", "avg_goals_conceded",
                    "form", "recent_matches"):
            assert key in stats, f"Missing backward-compat key: {key}"

    def test_unknown_team_returns_none(self, repo):
        assert repo.get_team_stats("Nonexistent FC") is None


# ---------------------------------------------------------------------------
# _weighted_avg() (εκθετικά σταθμισμένος μέσος)
# ---------------------------------------------------------------------------

class TestWeightedAvg:
    def test_uniform(self):
        assert DataRepository._weighted_avg([2.0, 2.0, 2.0]) == pytest.approx(2.0, abs=0.01)

    def test_empty(self):
        assert DataRepository._weighted_avg([]) == 0.0

    def test_single(self):
        assert DataRepository._weighted_avg([3.5]) == pytest.approx(3.5, abs=0.01)

    def test_recent_weighted_higher(self):
        # [3, 3, 1, 1] πιο πρόσφατα πρώτα → σταθμισμένος μέσος > απλός μέσος 2.0
        result = DataRepository._weighted_avg([3.0, 3.0, 1.0, 1.0])
        assert result > 2.0
