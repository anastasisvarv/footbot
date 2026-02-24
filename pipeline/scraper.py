"""
FBref scraper — uses undetected-chromedriver to bypass Cloudflare.

FBref is behind Cloudflare's interactive JS challenge, which blocks plain
requests and headless browsers.  undetected-chromedriver launches a real
(headed) Chrome instance that Cloudflare cannot distinguish from a human.

FBref quirk: many stat tables are embedded inside HTML comments to defer
rendering.  _all_tables() extracts tables from both the live DOM and any
HTML comment blocks.

Rate-limiting: a fixed REQUEST_DELAY is enforced between every page load.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Dict, List, Optional

import undetected_chromedriver as uc
from bs4 import BeautifulSoup, Comment

from .config import FBREF_BASE, SEASONS_TO_FETCH

logger = logging.getLogger(__name__)

REQUEST_DELAY   = 1.0   # seconds between page loads (mandatory)
CF_WAIT_TIMEOUT = 20.0  # seconds to wait for Cloudflare challenge to clear
CF_POLL         = 0.5   # polling interval while waiting

# Cloudflare challenge page titles (may be localised)
_CF_TITLES = {"just a moment...", "περιμένετε...", "einen moment..."}


class FBrefScraper:
    """
    Scrapes FBref competition pages for standings and match fixtures.

    Uses a persistent Chrome browser for the whole session — initialised once
    on first use, closed when the scraper is used as a context manager or
    when close() is called explicitly.

    Usage:
        with FBrefScraper() as scraper:
            seasons = scraper.get_seasons(9, "Premier-League")
    """

    def __init__(self) -> None:
        self._driver: Optional[uc.Chrome] = None

    # ------------------------------------------------------------------
    # Context manager / lifecycle
    # ------------------------------------------------------------------

    def __enter__(self) -> "FBrefScraper":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self) -> None:
        if self._driver is not None:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    # ------------------------------------------------------------------
    # Browser management
    # ------------------------------------------------------------------

    def _ensure_driver(self) -> uc.Chrome:
        if self._driver is None:
            logger.info("Launching Chrome (undetected-chromedriver)…")
            opts = uc.ChromeOptions()
            opts.add_argument("--no-sandbox")
            opts.add_argument("--disable-dev-shm-usage")
            self._driver = uc.Chrome(options=opts, headless=False, version_main=None)
        return self._driver

    # ------------------------------------------------------------------
    # HTTP (via real browser)
    # ------------------------------------------------------------------

    def _get(self, url: str) -> str:
        """
        Navigate to *url*, wait for any Cloudflare challenge to resolve,
        then return the page HTML.  Enforces REQUEST_DELAY after every load.
        """
        driver = self._ensure_driver()
        logger.debug("Navigating to %s", url)
        driver.get(url)

        # Wait for Cloudflare challenge page to clear
        waited = 0.0
        while waited < CF_WAIT_TIMEOUT:
            title = driver.title.strip().lower()
            if title not in _CF_TITLES:
                break
            time.sleep(CF_POLL)
            waited += CF_POLL

        if driver.title.strip().lower() in _CF_TITLES:
            raise RuntimeError(
                f"Cloudflare challenge did not resolve after {CF_WAIT_TIMEOUT}s for {url}"
            )

        time.sleep(REQUEST_DELAY)   # mandatory delay after every successful load
        return driver.page_source

    # ------------------------------------------------------------------
    # HTML helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _soup(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "lxml")

    @staticmethod
    def _all_tables(soup: BeautifulSoup) -> List[BeautifulSoup]:
        """
        Return every <table> from the page, including those inside HTML
        comments.  FBref hides many stat tables inside <!-- ... --> blocks.
        """
        tables: List[BeautifulSoup] = list(soup.find_all("table"))
        for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
            inner = BeautifulSoup(comment, "lxml")
            tables.extend(inner.find_all("table"))
        return tables

    # ------------------------------------------------------------------
    # Season discovery
    # ------------------------------------------------------------------

    def get_seasons(
        self,
        league_id: int,
        league_slug: str,
        n: int = SEASONS_TO_FETCH,
    ) -> List[Dict]:
        """
        Fetch the competition's main page and return info dicts for the *n*
        most-recent seasons (current first, then previous).

        Each dict:
            season       – e.g. "2025-2026" or "current"
            stats_url    – standings/stats page URL
            fixtures_url – Scores & Fixtures page URL
        """
        base_url = f"{FBREF_BASE}/en/comps/{league_id}/{league_slug}-Stats"
        html = self._get(base_url)
        soup = self._soup(html)

        seasons: List[Dict] = []

        # Current season lives at the base URL
        current = self._detect_season(soup)
        seasons.append({
            "season": current,
            "stats_url": base_url,
            "fixtures_url": (
                f"{FBREF_BASE}/en/comps/{league_id}/schedule"
                f"/{league_slug}-Scores-and-Fixtures"
            ),
        })

        # Previous seasons: href pattern /en/comps/{id}/YYYY-YYYY/YYYY-YYYY-{slug}-Stats
        pat = re.compile(
            rf"/en/comps/{league_id}/(\d{{4}}-\d{{4}})/\1-{re.escape(league_slug)}-Stats"
        )
        seen: set = set()
        for a_tag in soup.find_all("a", href=pat):
            m = pat.search(a_tag["href"])
            if not m:
                continue
            season_slug = m.group(1)
            if season_slug == current or season_slug in seen:
                continue
            seen.add(season_slug)
            seasons.append({
                "season": season_slug,
                "stats_url": (
                    f"{FBREF_BASE}/en/comps/{league_id}/{season_slug}"
                    f"/{season_slug}-{league_slug}-Stats"
                ),
                "fixtures_url": (
                    f"{FBREF_BASE}/en/comps/{league_id}/{season_slug}/schedule"
                    f"/{season_slug}-{league_slug}-Scores-and-Fixtures"
                ),
            })
            if len(seasons) >= n:
                break

        return seasons[:n]

    @staticmethod
    def _detect_season(soup: BeautifulSoup) -> str:
        """Extract season string (e.g. '2025-2026') from page title or h1."""
        for tag in ("title", "h1"):
            el = soup.find(tag)
            if el:
                m = re.search(r"(\d{4}-\d{4})", el.get_text())
                if m:
                    return m.group(1)
        return "current"

    # ------------------------------------------------------------------
    # Standings
    # ------------------------------------------------------------------

    def get_standings(self, stats_url: str) -> List[Dict]:
        """
        Scrape the standings table from a competition stats page.

        Returns a list of dicts: {team, MP, W, D, L, GF, GA, GD, points}
        """
        html = self._get(stats_url)
        soup = self._soup(html)

        for table in self._all_tables(soup):
            rows = self._parse_standings(table)
            if rows:
                return rows

        logger.warning("No standings table found at %s", stats_url)
        return []

    @staticmethod
    def _parse_standings(table: BeautifulSoup) -> List[Dict]:
        thead = table.find("thead")
        if not thead:
            return []
        header_stats = {th.get("data-stat", "") for th in thead.find_all("th")}

        # FBref standings use "team" (not "squad") and "ties" (not "draws")
        has_team_col = bool({"team", "squad"} & header_stats)
        has_wdl_cols = bool(
            {"wins", "ties", "losses"} <= header_stats       # FBref standard
            or {"wins", "draws", "losses"} <= header_stats   # alternate
            or {"games", "goals_for"} <= header_stats        # minimal fallback
        )
        if not (has_team_col and has_wdl_cols):
            return []

        tbody = table.find("tbody")
        if not tbody:
            return []

        rows: List[Dict] = []
        for tr in tbody.find_all("tr"):
            classes = tr.get("class", [])
            if any(c in classes for c in ("thead", "spacer", "partial_table")):
                continue

            data: Dict[str, str] = {}
            for cell in tr.find_all(["td", "th"]):
                stat = cell.get("data-stat", "")
                if stat:
                    data[stat] = cell.get_text(strip=True)

            # "team" on standings pages; "squad" on some squad-level pages
            team = data.get("team", data.get("squad", "")).strip()
            if not team:
                continue

            def _int(key: str, alt: str = "") -> int:
                val = data.get(key, data.get(alt, "0")).strip() or "0"
                try:
                    return int(val)
                except ValueError:
                    return 0

            rows.append({
                "team":   team,
                "MP":     _int("games", "mp"),
                "W":      _int("wins"),
                "D":      _int("ties", "draws"),    # FBref uses "ties" for draws
                "L":      _int("losses"),
                "GF":     _int("goals_for"),
                "GA":     _int("goals_against"),
                "GD":     _int("goal_diff"),
                "points": _int("points"),
            })

        return rows

    # ------------------------------------------------------------------
    # Fixtures / Schedule
    # ------------------------------------------------------------------

    def get_matches(self, fixtures_url: str) -> List[Dict]:
        """
        Scrape completed matches from a Scores & Fixtures page.

        Returns a list of dicts:
            {date, home_team, away_team, home_goals, away_goals,
             halftime_home_goals, halftime_away_goals, round}
        """
        html = self._get(fixtures_url)
        soup = self._soup(html)

        for table in self._all_tables(soup):
            rows = self._parse_fixtures(table)
            if rows:
                return rows

        logger.warning("No fixtures table found at %s", fixtures_url)
        return []

    @staticmethod
    def _parse_fixtures(table: BeautifulSoup) -> List[Dict]:
        thead = table.find("thead")
        if not thead:
            return []
        header_stats = {th.get("data-stat", "") for th in thead.find_all("th")}

        has_fixture_cols = (
            {"score", "home_team", "away_team"} <= header_stats
            or {"score", "squad_a", "squad_b"} <= header_stats
        )
        if not has_fixture_cols:
            return []

        tbody = table.find("tbody")
        if not tbody:
            return []

        matches: List[Dict] = []
        for tr in tbody.find_all("tr"):
            classes = tr.get("class", [])
            if any(c in classes for c in ("thead", "spacer", "partial_table")):
                continue

            data: Dict[str, str] = {}
            for cell in tr.find_all(["td", "th"]):
                stat = cell.get("data-stat", "")
                if stat:
                    data[stat] = cell.get_text(strip=True)

            # Score — FBref uses en-dash (–); also accept hyphen or colon
            score_raw = data.get("score", "").strip()
            if not score_raw:
                continue
            sm = re.match(r"(\d+)\s*[–\-:]\s*(\d+)", score_raw)
            if not sm:
                continue   # unplayed / postponed

            home_goals = int(sm.group(1))
            away_goals = int(sm.group(2))
            if home_goals < 0 or away_goals < 0:
                continue

            date_str  = data.get("date", "").strip()
            home_team = data.get("home_team", data.get("squad_a", "")).strip()
            away_team = data.get("away_team", data.get("squad_b", "")).strip()
            round_str = data.get("gameweek", data.get("round", "")).strip()

            if not date_str or not home_team or not away_team:
                continue

            matches.append({
                "date":                date_str,
                "home_team":           home_team,
                "away_team":           away_team,
                "home_goals":          home_goals,
                "away_goals":          away_goals,
                "halftime_home_goals": None,
                "halftime_away_goals": None,
                "round":               round_str or None,
            })

        return matches
