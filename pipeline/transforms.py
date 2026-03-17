"""
Data cleaning and normalisation for the pipeline.

Provides:
  clean_matches_df   – raw match list → typed, deduplicated DataFrame
  clean_standings_df – raw standings list → typed DataFrame
  build_team_aliases – team name list → [{canonical, aliases}] records
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List

import pandas as pd


# ---------------------------------------------------------------------------
# DataFrame cleaning
# ---------------------------------------------------------------------------

_MATCH_COLS = [
    "date",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "halftime_home_goals",
    "halftime_away_goals",
    "round",
]

_STANDINGS_COLS = ["team", "MP", "W", "D", "L", "GF", "GA", "GD", "points"]


def clean_matches_df(matches: List[Dict]) -> pd.DataFrame:
    """
    Convert raw match dicts into a clean, typed DataFrame.

    Schema (one row per completed match):
        date                  – datetime.date
        home_team             – str
        away_team             – str
        home_goals            – Int64 (nullable)
        away_goals            – Int64 (nullable)
        halftime_home_goals   – Int64 (nullable)
        halftime_away_goals   – Int64 (nullable)
        round                 – str or None

    Cleaning steps:
        1. Ensure all schema columns exist
        2. Parse dates
        3. Cast goals to nullable Int64
        4. Validate goals ≥ 0
        5. Deduplicate on (date, home_team, away_team)
        6. Sort newest-first
    """
    if not matches:
        return pd.DataFrame(columns=_MATCH_COLS)

    df = pd.DataFrame(matches)

    # Ensure all columns exist
    for col in _MATCH_COLS:
        if col not in df.columns:
            df[col] = None

    # Date
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date

    # String fields
    df["home_team"] = df["home_team"].astype(str).str.strip()
    df["away_team"] = df["away_team"].astype(str).str.strip()

    # Integer goals (nullable — matches not yet played stay null)
    for col in ("home_goals", "away_goals", "halftime_home_goals", "halftime_away_goals"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Validate: keep only rows with non-negative goals
    valid = (
        df["home_goals"].notna()
        & df["away_goals"].notna()
        & (df["home_goals"] >= 0)
        & (df["away_goals"] >= 0)
    )
    df = df[valid].copy()

    # Round: keep as nullable string
    df["round"] = df["round"].where(
        df["round"].notna() & (df["round"].astype(str).str.strip() != ""),
        other=None,
    )

    # Deduplicate
    df = df.drop_duplicates(subset=["date", "home_team", "away_team"])

    # Sort newest first
    df = df.sort_values("date", ascending=False).reset_index(drop=True)

    return df[_MATCH_COLS]


def clean_standings_df(standings: List[Dict]) -> pd.DataFrame:
    """
    Convert raw standings dicts into a clean, typed DataFrame.

    Schema: team, MP, W, D, L, GF, GA, GD, points  (all integers except team).
    """
    if not standings:
        return pd.DataFrame(columns=_STANDINGS_COLS)

    df = pd.DataFrame(standings)

    for col in _STANDINGS_COLS:
        if col not in df.columns:
            df[col] = 0 if col != "team" else ""

    for col in ("MP", "W", "D", "L", "GF", "GA", "GD", "points"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    df["team"] = df["team"].astype(str).str.strip()
    df = df[df["team"].str.len() > 0].drop_duplicates(subset=["team"])

    return df[_STANDINGS_COLS].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Team alias generation
# ---------------------------------------------------------------------------

_PREFIX_RE = re.compile(
    r"^(FC|AC|AS|SC|SS|US|CF|VfB|VfL|RB|TSG|OGC|BSC|RC|RSC|SV|SK|FK|AFC|FCD)\s+",
    re.IGNORECASE,
)
_SUFFIX_RE = re.compile(
    r"\s+(FC|CF|SC|AC|FK|SK|IF|AFC|SSC|Calcio|1899|1900|1904|1907|1908|1909|1910|1912)$",
    re.IGNORECASE,
)


def build_team_aliases(team_names: List[str]) -> List[Dict]:
    """
    Given a list of team names (as they appear in FBref data), return a list
    of records suitable for teams.json:

        [{"canonical": "Manchester City", "aliases": ["Man City", ...]}, ...]
    """
    return [
        {"canonical": name, "aliases": sorted(set(_generate_aliases(name)) - {name})}
        for name in sorted(set(team_names))
        if name.strip()
    ]


def _deaccent(s: str) -> str:
    """Strip diacritics: 'München' → 'Munchen'."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def _generate_aliases(name: str) -> List[str]:
    """Produce common shortened / deaccented variants of a team name."""
    variants: set = {name}

    # Deaccented original
    da = _deaccent(name)
    variants.add(da)

    # Strip common prefix  (e.g. "FC Bayern München" → "Bayern München")
    no_prefix = _PREFIX_RE.sub("", name).strip()
    if no_prefix != name:
        variants.add(no_prefix)
        variants.add(_deaccent(no_prefix))

    # Strip common suffix  (e.g. "Bayern München FC" → "Bayern München")
    no_suffix = _SUFFIX_RE.sub("", no_prefix).strip()
    if no_suffix != no_prefix:
        variants.add(no_suffix)
        variants.add(_deaccent(no_suffix))

    # Also strip suffix from original
    no_suffix2 = _SUFFIX_RE.sub("", name).strip()
    if no_suffix2 != name:
        variants.add(no_suffix2)
        variants.add(_deaccent(no_suffix2))

    return [v for v in variants if v]
