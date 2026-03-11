#!/usr/bin/env python3
"""
Footbot Backtesting & Model Evaluation
=======================================

Evaluates the Poisson prediction model on completed historical matches
using a rolling-window approach to prevent data leakage.

Metrics reported
----------------
  Accuracy    — percentage of correctly predicted 1X2 outcomes
  Brier Score — probability calibration error (lower is better; 0 = perfect)
  RPS         — Ranked Probability Score (industry standard for football; lower = better)

Baselines compared
------------------
  Home-bias   — always predict home win with fixed probabilities (50/25/25)
  Uniform     — assign equal probability to all three outcomes (33/33/33)
  Historical  — use the actual H/D/A frequency from the test set as a constant model

Usage
-----
  python evaluate.py                           # all leagues, most recent season
  python evaluate.py --league premier_league   # one league only
  python evaluate.py --export results.csv      # also save per-match predictions to CSV
  python evaluate.py --min-matches 8           # require ≥8 prior matches (default 5)

References
----------
  Maher, M.J. (1982). Modelling association football scores.
  Dixon, M. & Coles, S. (1997). Modelling Association Football Scores and Inefficiencies.
  Constantinou, A.C. & Fenton, N.E. (2012). Solving the problem of inadequate scoring
    rules for assessing probabilistic football forecast models.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from pipeline.config import DATA_DIR, LEAGUES
from rasa.actions.predictor import LEAGUE_AVG_DEFAULTS, predict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _weighted_avg(values: List[float], decay: float = 0.85) -> float:
    """Exponential-decay weighted mean; index 0 = most recent."""
    if not values:
        return 0.0
    weights = [decay ** i for i in range(len(values))]
    total_w = sum(weights)
    return round(sum(v * w for v, w in zip(values, weights)) / total_w, 2)


def _team_stats_before(
    all_matches: pd.DataFrame,
    team: str,
    before_date,
    max_n: int = 38,
    min_n: int = 5,
) -> Optional[Dict]:
    """
    Compute exponential-decay-weighted stats for *team* using only matches
    that were played strictly before *before_date*.

    Returns None when fewer than *min_n* completed matches are available,
    which prevents predictions with unreliable statistics.
    """
    name_lower = team.lower()
    mask = (
        (
            (all_matches["home_team"].str.lower() == name_lower)
            | (all_matches["away_team"].str.lower() == name_lower)
        )
        & (all_matches["date"] < before_date)
        & all_matches["home_goals"].notna()
        & all_matches["away_goals"].notna()
    )
    prior = all_matches[mask].sort_values("date", ascending=False).head(max_n)
    if len(prior) < min_n:
        return None

    gs, gc = [], []
    gs_h, gs_a, gc_h, gc_a = [], [], [], []

    for _, row in prior.iterrows():
        hg = int(row["home_goals"])
        ag = int(row["away_goals"])
        is_home = row["home_team"].lower() == name_lower
        gf = hg if is_home else ag
        ga = ag if is_home else hg

        gs.append(float(gf))
        gc.append(float(ga))
        if is_home:
            gs_h.append(float(gf))
            gc_h.append(float(ga))
        else:
            gs_a.append(float(gf))
            gc_a.append(float(ga))

    return {
        "avg_goals_scored":        _weighted_avg(gs),
        "avg_goals_conceded":      _weighted_avg(gc),
        "avg_goals_scored_home":   _weighted_avg(gs_h) if gs_h else None,
        "avg_goals_scored_away":   _weighted_avg(gs_a) if gs_a else None,
        "avg_goals_conceded_home": _weighted_avg(gc_h) if gc_h else None,
        "avg_goals_conceded_away": _weighted_avg(gc_a) if gc_a else None,
    }


# ---------------------------------------------------------------------------
# Metric functions
# ---------------------------------------------------------------------------

def brier_score(p_h: float, p_d: float, p_a: float, outcome: str) -> float:
    """
    Multi-outcome Brier Score.

    Range: [0, 2]   0 = perfect,  2 = worst possible.
    For a 3-outcome problem the expected score for a random model ≈ 0.667.
    """
    o_h = 1.0 if outcome == "H" else 0.0
    o_d = 1.0 if outcome == "D" else 0.0
    o_a = 1.0 if outcome == "A" else 0.0
    return (p_h - o_h) ** 2 + (p_d - o_d) ** 2 + (p_a - o_a) ** 2


def rps(p_h: float, p_d: float, p_a: float, outcome: str) -> float:
    """
    Ranked Probability Score for 3 ordered outcomes (H > D > A).

    Range: [0, 1]   0 = perfect,  1 = worst.
    Preferred over Brier Score for football because it rewards
    probability mass placed near the correct outcome.

    Formula: RPS = 0.5 * sum_j [ (cumP_j - cumO_j)^2 ]
    """
    cum_p = [p_h, p_h + p_d]
    cum_o = [1.0 if outcome == "H" else 0.0,
             0.0 if outcome == "A" else 1.0]
    return 0.5 * sum((cp - co) ** 2 for cp, co in zip(cum_p, cum_o))


# ---------------------------------------------------------------------------
# Per-league backtesting
# ---------------------------------------------------------------------------

def evaluate_league(
    slug: str,
    league_name: str,
    min_prior_matches: int = 5,
) -> List[Dict]:
    """
    Run backtesting for a single league.

    Strategy
    --------
    * Test set  : all completed matches from the most recent scraped season.
    * Train set : all matches from earlier seasons (no overlap with test).
    * League avg: computed from completed prior-season matches (no test leakage).
    * Per match : team stats computed from all matches strictly before match date.

    Returns a list of per-match result dicts.
    """
    league_dir = DATA_DIR / slug
    if not league_dir.exists():
        print(f"  [SKIP] No data directory for {league_name}")
        return []

    seasons = sorted(
        [p.name for p in league_dir.iterdir() if p.is_dir()],
        reverse=True,
    )
    if not seasons:
        return []

    # Load all seasons
    frames: List[pd.DataFrame] = []
    for season in seasons:
        mp = league_dir / season / "matches.parquet"
        if mp.exists():
            df = pd.read_parquet(mp)
            df["season"] = season
            frames.append(df)

    if not frames:
        print(f"  [SKIP] No parquet files for {league_name}")
        return []

    all_matches = pd.concat(frames, ignore_index=True)
    all_matches["date"] = pd.to_datetime(all_matches["date"], errors="coerce")
    all_matches = all_matches.dropna(subset=["date"])

    # Test set: most recent season, completed matches only
    test_season = seasons[0]
    test_df = (
        all_matches[
            (all_matches["season"] == test_season)
            & all_matches["home_goals"].notna()
            & all_matches["away_goals"].notna()
        ]
        .sort_values("date")
        .reset_index(drop=True)
    )

    if len(test_df) < 10:
        print(
            f"  [SKIP] {league_name}: only {len(test_df)} completed matches "
            f"in {test_season} — need ≥10"
        )
        return []

    # League average from prior seasons (avoids test-set leakage)
    prior_completed = all_matches[
        (all_matches["season"] != test_season)
        & all_matches["home_goals"].notna()
        & all_matches["away_goals"].notna()
    ]
    if len(prior_completed) >= 20:
        total_goals = int(
            (prior_completed["home_goals"] + prior_completed["away_goals"]).sum()
        )
        league_avg: float = round(total_goals / len(prior_completed), 3)
    else:
        league_avg = LEAGUE_AVG_DEFAULTS.get(
            league_name.lower(), LEAGUE_AVG_DEFAULTS["default"]
        )

    results: List[Dict] = []
    skipped = 0

    for _, match in test_df.iterrows():
        home_team = match["home_team"]
        away_team = match["away_team"]
        match_date = match["date"]
        hg = int(match["home_goals"])
        ag = int(match["away_goals"])

        # Actual 1X2 outcome
        if hg > ag:
            actual = "H"
        elif hg == ag:
            actual = "D"
        else:
            actual = "A"

        # Compute stats using strictly prior data
        home_stats = _team_stats_before(
            all_matches, home_team, match_date, min_n=min_prior_matches
        )
        away_stats = _team_stats_before(
            all_matches, away_team, match_date, min_n=min_prior_matches
        )

        if not home_stats or not away_stats:
            skipped += 1
            continue

        pred = predict(home_stats, away_stats, league=slug, league_avg=league_avg)
        p_h = pred["home_win_pct"] / 100.0
        p_d = pred["draw_pct"] / 100.0
        p_a = pred["away_win_pct"] / 100.0

        predicted = max(
            [("H", p_h), ("D", p_d), ("A", p_a)], key=lambda x: x[1]
        )[0]

        results.append(
            {
                "league":            league_name,
                "season":            test_season,
                "date":              str(match_date.date()),
                "home_team":         home_team,
                "away_team":         away_team,
                "actual_score":      f"{hg}-{ag}",
                "actual_outcome":    actual,
                "predicted_outcome": predicted,
                "correct":           predicted == actual,
                "p_home":            round(p_h, 4),
                "p_draw":            round(p_d, 4),
                "p_away":            round(p_a, 4),
                "brier":             round(brier_score(p_h, p_d, p_a, actual), 4),
                "rps":               round(rps(p_h, p_d, p_a, actual), 4),
                "home_xg":           pred["home_xg"],
                "away_xg":           pred["away_xg"],
                "most_likely_score": pred["most_likely_score"],
                "league_avg_used":   round(league_avg, 3),
            }
        )

    print(
        f"  {league_name:<25} {len(results):>4} predictions  "
        f"({skipped} skipped — insufficient prior data)"
    )
    return results


# ---------------------------------------------------------------------------
# Baseline metrics
# ---------------------------------------------------------------------------

def baseline_metrics(results: List[Dict]) -> Dict:
    """
    Compute metrics for three naïve baseline models.

    Home-bias     p(H)=0.50, p(D)=0.25, p(A)=0.25
    Uniform       p(H)=p(D)=p(A)=1/3
    Historical    constant probabilities equal to empirical H/D/A frequencies
    """
    n = len(results)
    if n == 0:
        return {}

    outcomes = [r["actual_outcome"] for r in results]
    h_freq = outcomes.count("H") / n
    d_freq = outcomes.count("D") / n
    a_freq = outcomes.count("A") / n

    def _metrics(p_h, p_d, p_a):
        acc_pred = max([("H", p_h), ("D", p_d), ("A", p_a)], key=lambda x: x[1])[0]
        acc  = sum(1 for o in outcomes if o == acc_pred) / n
        bs   = sum(brier_score(p_h, p_d, p_a, o) for o in outcomes) / n
        rps_ = sum(rps(p_h, p_d, p_a, o) for o in outcomes) / n
        return {"accuracy": acc, "brier": bs, "rps": rps_}

    return {
        "home_bias":      _metrics(0.50, 0.25, 0.25),
        "uniform":        _metrics(1 / 3, 1 / 3, 1 / 3),
        "historical_freq": _metrics(h_freq, d_freq, a_freq),
        "h_freq": h_freq,
        "d_freq": d_freq,
        "a_freq": a_freq,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def print_report(all_results: List[Dict], baselines: Dict) -> None:
    """Print a formatted evaluation report to stdout."""
    n = len(all_results)
    if n == 0:
        print("\n  No predictions were produced. Check that data is available.")
        print("  Run:  python -m pipeline update\n")
        return

    accuracy   = sum(1 for r in all_results if r["correct"]) / n
    avg_brier  = sum(r["brier"] for r in all_results) / n
    avg_rps    = sum(r["rps"] for r in all_results) / n

    # Per-league breakdown
    leagues_seen = sorted({r["league"] for r in all_results})
    per_league: Dict[str, Dict] = {}
    for league in leagues_seen:
        lr = [r for r in all_results if r["league"] == league]
        ln = len(lr)
        per_league[league] = {
            "n":        ln,
            "accuracy": sum(1 for r in lr if r["correct"]) / ln,
            "brier":    sum(r["brier"] for r in lr) / ln,
            "rps":      sum(r["rps"] for r in lr) / ln,
        }

    W = 70
    print("\n" + "=" * W)
    print("  FOOTBOT — MODEL EVALUATION REPORT")
    print("=" * W)
    print(f"  Prediction model : Poisson (Dixon-Coles, venue-aware)")
    print(f"  Test matches     : {n}")
    print(f"  Leagues          : {', '.join(leagues_seen)}")
    print()

    # Overall results
    print(f"  {'METRIC':<22} {'POISSON':>10}  {'HOME-BIAS':>10}  {'UNIFORM':>10}  {'HIST-FREQ':>10}")
    print("  " + "-" * (W - 2))
    for metric, label in [("accuracy", "Accuracy (1X2)"), ("brier", "Brier Score ↓"), ("rps", "RPS ↓")]:
        row = f"  {label:<22} {all_results and (accuracy if metric == 'accuracy' else (avg_brier if metric == 'brier' else avg_rps)):>10.4f}"
        for bsl in ["home_bias", "uniform", "historical_freq"]:
            row += f"  {baselines.get(bsl, {}).get(metric, 0):>10.4f}"
        print(row)

    print()
    print(f"  Outcome distribution  H:{_pct(baselines['h_freq'])}  D:{_pct(baselines['d_freq'])}  A:{_pct(baselines['a_freq'])}")

    # Per-league table
    print()
    print(f"  {'LEAGUE':<28} {'N':>5}  {'ACCURACY':>9}  {'BRIER':>7}  {'RPS':>7}")
    print("  " + "-" * (W - 2))
    for league, m in per_league.items():
        print(
            f"  {league:<28} {m['n']:>5}  {m['accuracy']:>9.4f}  "
            f"{m['brier']:>7.4f}  {m['rps']:>7.4f}"
        )

    # Interpretation guide
    print()
    print("  INTERPRETATION")
    print("  " + "-" * (W - 2))
    print("  Brier Score: 0.00 = perfect | 0.667 = random (3-outcome) | 2.00 = worst")
    print("  RPS:         0.00 = perfect | 0.25  = random             | 1.00 = worst")
    print(
        f"\n  The Poisson model {'OUTPERFORMS' if avg_rps < baselines['home_bias']['rps'] else 'does NOT outperform'} "
        f"the home-bias baseline (RPS: {avg_rps:.4f} vs {baselines['home_bias']['rps']:.4f})"
    )
    print("=" * W + "\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backtest Footbot's Poisson model and compare to baselines."
    )
    parser.add_argument(
        "--league",
        default=None,
        help="Evaluate only this league slug (e.g. premier_league). Default: all.",
    )
    parser.add_argument(
        "--export",
        default=None,
        metavar="FILE.csv",
        help="Save per-match prediction results to a CSV file.",
    )
    parser.add_argument(
        "--min-matches",
        type=int,
        default=5,
        help="Minimum prior matches required per team before predicting (default: 5).",
    )
    args = parser.parse_args()

    target_leagues = (
        {args.league: LEAGUES[args.league]}
        if args.league and args.league in LEAGUES
        else LEAGUES
    )

    print("\nFootbot Model Evaluation")
    print(f"Data directory: {DATA_DIR}\n")

    all_results: List[Dict] = []
    for slug, cfg in target_leagues.items():
        all_results.extend(
            evaluate_league(slug, cfg["name"], min_prior_matches=args.min_matches)
        )

    if not all_results:
        print("\nNo results generated. Make sure data exists:")
        print("  python -m pipeline update\n")
        sys.exit(1)

    baselines = baseline_metrics(all_results)
    print_report(all_results, baselines)

    if args.export:
        df = pd.DataFrame(all_results)
        df.to_csv(args.export, index=False)
        print(f"  Saved {len(df)} rows to {args.export}\n")


if __name__ == "__main__":
    main()
