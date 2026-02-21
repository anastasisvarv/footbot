#!/usr/bin/env python3
"""
Standalone cache refresh script.
Run this to pre-populate data/football_cache.json before starting Rasa.

Usage:
    python3 scraper/fetch_data.py

Requires FOOTBALL_DATA_API_KEY in .env (or set as environment variable).
"""

import sys
import os
import logging

# Allow imports from rasa/actions/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rasa.actions import football_data as fd

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def main():
    logger.info("=== Footbot cache refresh ===")

    # Standings for all API-supported leagues
    leagues = ["Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1", "Super League"]
    for league in leagues:
        logger.info("Fetching standings: %s", league)
        rows = fd.get_standings(league)
        if rows:
            logger.info("  ✅ %d rows cached", len(rows))
        else:
            logger.warning("  ⚠️  No data returned")

    # Recent matches for popular teams
    teams = [
        "Liverpool", "Arsenal", "Manchester City", "Chelsea",
        "Real Madrid", "Barcelona", "Bayern Munich",
        "Inter", "Juventus", "PSG",
    ]
    for team in teams:
        logger.info("Fetching stats: %s", team)
        stats = fd.get_team_stats(team)
        if stats and not stats.get("_fallback"):
            logger.info("  ✅ %d matches, avg scored: %s", stats["played"], stats["avg_goals_scored"])
        elif stats:
            logger.warning("  ⚠️  Using fallback data (API key missing or rate limited)")
        else:
            logger.warning("  ❌  Failed")

    logger.info("=== Cache refresh complete ===")
    logger.info("Cache file: %s", fd.CACHE_FILE)


if __name__ == "__main__":
    main()
