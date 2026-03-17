"""
Footbot data pipeline CLI.

Commands:
    python -m pipeline update                 # scrape all 6 leagues, 3 seasons each
    python -m pipeline update --league <slug> # scrape one league only
    python -m pipeline validate               # validate all stored data

League slugs: premier_league, la_liga, serie_a, bundesliga, ligue_1,
              super_league_greece
"""
from __future__ import annotations

import argparse
import logging
import sys

from .config import LEAGUES, SEASONS_TO_FETCH
from .scraper import FBrefScraper
from .transforms import build_team_aliases, clean_matches_df, clean_standings_df
from . import storage
from .validator import validate_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# update (ενημέρωση)
# ---------------------------------------------------------------------------

def cmd_update(league_filter: str | None) -> int:
    leagues = (
        {k: v for k, v in LEAGUES.items() if k == league_filter}
        if league_filter
        else LEAGUES
    )
    if not leagues:
        logger.error(
            "Unknown league slug '%s'. Valid slugs: %s",
            league_filter,
            list(LEAGUES),
        )
        return 1

    error_count = 0

    with FBrefScraper() as scraper:
        for slug, cfg in leagues.items():
            logger.info("=== %s (%s) ===", cfg["name"], slug)

            # --- Ανακάλυψη σεζόν ---
            try:
                seasons = scraper.get_seasons(
                    cfg["fbref_id"], cfg["fbref_slug"], SEASONS_TO_FETCH
                )
                logger.info(
                    "  Found %d season(s): %s",
                    len(seasons),
                    [s["season"] for s in seasons],
                )
            except Exception as exc:
                logger.error("  Season discovery failed for %s: %s", slug, exc)
                error_count += 1
                continue

            # --- Scraping κάθε σεζόν ---
            for info in seasons:
                season = info["season"]
                logger.info("  Scraping %s %s …", cfg["name"], season)
                try:
                    # Βαθμολογία
                    raw_standings = scraper.get_standings(info["stats_url"])
                    standings_df = clean_standings_df(raw_standings)
                    storage.save_standings(standings_df, slug, season)

                    # Αγώνες
                    raw_matches = scraper.get_matches(info["fixtures_url"])
                    matches_df = clean_matches_df(raw_matches)
                    storage.save_matches(matches_df, slug, season)

                    # Ομάδες — ένωση ονομάτων από βαθμολογία + αγώνες
                    team_names = list({
                        *standings_df["team"].tolist(),
                        *matches_df["home_team"].tolist(),
                        *matches_df["away_team"].tolist(),
                    })
                    teams = build_team_aliases(team_names)
                    storage.save_teams(teams, slug, season)

                    # Μεταδεδομένα
                    storage.save_metadata(
                        slug,
                        season,
                        league_name=cfg["name"],
                        competition_id=cfg["fbref_id"],
                        match_count=len(matches_df),
                        standing_count=len(standings_df),
                    )

                    logger.info(
                        "  Done  %s %s — %d matches, %d teams in standings",
                        cfg["name"],
                        season,
                        len(matches_df),
                        len(standings_df),
                    )
                except Exception as exc:
                    logger.error(
                        "  Failed %s %s: %s", slug, season, exc, exc_info=True
                    )
                    error_count += 1

    if error_count:
        logger.warning("%d error(s) occurred during update.", error_count)
        return 1
    logger.info("Update complete — all leagues and seasons saved.")
    return 0


# ---------------------------------------------------------------------------
# validate (επικύρωση)
# ---------------------------------------------------------------------------

def cmd_validate() -> int:
    ok = validate_all()
    if ok:
        logger.info("Validation passed.")
    else:
        logger.error("Validation failed — see errors above.")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# Σημείο εισόδου
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline",
        description="Footbot FBref data pipeline",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_update = sub.add_parser("update", help="Scrape and store data from FBref")
    p_update.add_argument(
        "--league",
        choices=list(LEAGUES.keys()),
        metavar="SLUG",
        help="Scrape only this league (default: all)",
    )

    sub.add_parser("validate", help="Validate locally stored data")

    args = parser.parse_args()

    if args.command == "update":
        sys.exit(cmd_update(getattr(args, "league", None)))
    elif args.command == "validate":
        sys.exit(cmd_validate())


if __name__ == "__main__":
    main()
