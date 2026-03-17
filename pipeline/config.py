"""League configuration and shared constants for the FBref pipeline."""
from pathlib import Path

# Ρίζα project = γονικός φάκελος του φακέλου αυτού του αρχείου
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

FBREF_BASE = "https://fbref.com"

# Πόσες σεζόν να κρατούμε ανά πρωτάθλημα (τρέχουσα + N-1 προηγούμενες)
SEASONS_TO_FETCH = 3

# Ρύθμιση ανά πρωτάθλημα: fbref_id και fbref_slug πρέπει να ταιριάζουν με το FBref URL pattern:
#   /en/comps/{fbref_id}/{fbref_slug}-Stats   (τρέχουσα σεζόν)
#   /en/comps/{fbref_id}/{season}/{season}-{fbref_slug}-Stats  (προηγούμενη)
LEAGUES: dict = {
    "premier_league": {
        "name": "Premier League",
        "country": "England",
        "fbref_id": 9,
        "fbref_slug": "Premier-League",
    },
    "la_liga": {
        "name": "La Liga",
        "country": "Spain",
        "fbref_id": 12,
        "fbref_slug": "La-Liga",
    },
    "serie_a": {
        "name": "Serie A",
        "country": "Italy",
        "fbref_id": 11,
        "fbref_slug": "Serie-A",
    },
    "bundesliga": {
        "name": "Bundesliga",
        "country": "Germany",
        "fbref_id": 20,
        "fbref_slug": "Bundesliga",
    },
    "ligue_1": {
        "name": "Ligue 1",
        "country": "France",
        "fbref_id": 13,
        "fbref_slug": "Ligue-1",
    },
    "super_league_greece": {
        "name": "Super League Greece",
        "country": "Greece",
        "fbref_id": 27,
        "fbref_slug": "Super-League-Greece",
    },
}
