"""
Local file I/O for the pipeline.

Directory layout:
    data/
        <league_slug>/
            <season>/
                matches.parquet
                standings.parquet
                teams.json
                metadata.json
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .config import DATA_DIR

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Βοηθητικές συναρτήσεις μονοπατιών
# ---------------------------------------------------------------------------

def _league_dir(league_slug: str) -> Path:
    return DATA_DIR / league_slug


def _season_dir(league_slug: str, season: str) -> Path:
    return _league_dir(league_slug) / season


# ---------------------------------------------------------------------------
# Αποθήκευση
# ---------------------------------------------------------------------------

def save_matches(df: pd.DataFrame, league_slug: str, season: str) -> None:
    d = _season_dir(league_slug, season)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "matches.parquet"
    df.to_parquet(path, index=False)
    logger.info("Saved %d matches → %s", len(df), path)


def save_standings(df: pd.DataFrame, league_slug: str, season: str) -> None:
    d = _season_dir(league_slug, season)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "standings.parquet"
    df.to_parquet(path, index=False)
    logger.info("Saved %d standings rows → %s", len(df), path)


def save_teams(teams: List[Dict], league_slug: str, season: str) -> None:
    d = _season_dir(league_slug, season)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "teams.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"teams": teams}, f, indent=2, ensure_ascii=False)
    logger.info("Saved %d teams → %s", len(teams), path)


def save_metadata(
    league_slug: str,
    season: str,
    *,
    league_name: str,
    competition_id: int,
    match_count: int,
    standing_count: int,
) -> None:
    d = _season_dir(league_slug, season)
    d.mkdir(parents=True, exist_ok=True)
    meta = {
        "source": "fbref",
        "league": league_name,
        "season": season,
        "competition_id": competition_id,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "row_counts": {
            "matches": match_count,
            "standings": standing_count,
        },
    }
    with open(d / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


# ---------------------------------------------------------------------------
# Φόρτωση
# ---------------------------------------------------------------------------

def load_matches(league_slug: str, season: str) -> Optional[pd.DataFrame]:
    path = _season_dir(league_slug, season) / "matches.parquet"
    return pd.read_parquet(path) if path.exists() else None


def load_standings(league_slug: str, season: str) -> Optional[pd.DataFrame]:
    path = _season_dir(league_slug, season) / "standings.parquet"
    return pd.read_parquet(path) if path.exists() else None


def load_teams(league_slug: str, season: str) -> Optional[Dict]:
    path = _season_dir(league_slug, season) / "teams.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_seasons(league_slug: str) -> List[str]:
    """Return season directory names, sorted newest-first."""
    d = _league_dir(league_slug)
    if not d.exists():
        return []
    return sorted([p.name for p in d.iterdir() if p.is_dir()], reverse=True)
