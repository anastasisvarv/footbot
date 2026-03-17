"""
Data quality validation for the pipeline.

Usage:
    from pipeline.validator import validate_all
    ok = validate_all()           # returns True if everything passes
"""
from __future__ import annotations

import logging
from typing import List

import pandas as pd

from . import storage
from .config import LEAGUES

logger = logging.getLogger(__name__)


def validate_all() -> bool:
    """Validate every league / season in the data directory. Returns True iff all pass."""
    overall_ok = True
    for slug in LEAGUES:
        seasons = storage.list_seasons(slug)
        if not seasons:
            logger.warning(
                "MISSING  %-28s  — no seasons found (run: python -m pipeline update)",
                slug,
            )
            overall_ok = False
            continue
        for season in seasons:
            if not validate_season(slug, season):
                overall_ok = False
    return overall_ok


def validate_season(league_slug: str, season: str) -> bool:
    """Validate a single league/season directory. Returns True iff all checks pass."""
    errors: List[str] = []

    # --- αγώνες ---
    matches = storage.load_matches(league_slug, season)
    if matches is None:
        errors.append("matches.parquet missing")
    else:
        errors.extend(_check_matches(matches))

    # --- βαθμολογία ---
    standings = storage.load_standings(league_slug, season)
    if standings is None:
        errors.append("standings.parquet missing")
    else:
        errors.extend(_check_standings(standings))

    # --- ομάδες ---
    if storage.load_teams(league_slug, season) is None:
        errors.append("teams.json missing")

    label = f"{league_slug}/{season}"
    if errors:
        for err in errors:
            logger.error("FAIL  %-35s  %s", label, err)
        return False

    m_count = len(matches) if matches is not None else 0
    s_count = len(standings) if standings is not None else 0
    logger.info("OK    %-35s  matches=%d  standings=%d", label, m_count, s_count)
    return True


def _check_matches(df: pd.DataFrame) -> List[str]:
    errors: List[str] = []
    required = ["date", "home_team", "away_team", "home_goals", "away_goals"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return [f"missing columns: {missing}"]

    if df["home_goals"].dropna().lt(0).any() or df["away_goals"].dropna().lt(0).any():
        errors.append("negative goal values found")

    null_key = df[["home_team", "away_team", "date"]].isnull().any()
    if null_key.any():
        errors.append(f"nulls in key columns: {list(null_key[null_key].index)}")

    dup_count = df.duplicated(subset=["date", "home_team", "away_team"]).sum()
    if dup_count > 0:
        errors.append(f"{dup_count} duplicate match rows")

    return errors


def _check_standings(df: pd.DataFrame) -> List[str]:
    errors: List[str] = []
    required = ["team", "MP", "W", "D", "L", "GF", "GA", "GD", "points"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return [f"missing columns: {missing}"]

    if df["team"].isnull().any() or (df["team"] == "").any():
        errors.append("empty team names in standings")

    return errors
