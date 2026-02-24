# CLEANUP.md

Files and dependencies identified as unused / superseded after the
FBref-pipeline refactor.  Review before deleting.

---

## Files to Delete

### `rasa/actions/football_data.py`
- **Why obsolete:** All data fetching previously delegated to the
  football-data.org API and worldfootball.net scraper.  Replaced entirely by
  `rasa/actions/data_repository.py`, which loads data from local parquet files
  produced by the pipeline.
- **Current state:** Replaced with a stub that raises `ImportError` on import
  to prevent accidental use.
- **Safe to delete when:** `python -m pipeline validate` passes and all Rasa
  actions have been confirmed to work against local data.

### `scraper/fetch_data.py`
- **Why obsolete:** Was a one-shot cache pre-population script that called
  `football_data.get_standings()` / `get_team_stats()` and wrote a JSON cache.
  Replaced by `python -m pipeline update`.
- **Safe to delete when:** The pipeline CLI has been used successfully at
  least once.

### `scraper/` (directory)
- Contains only `fetch_data.py` (see above).  The directory itself becomes
  empty and can be removed alongside the file.

---

## Dependencies to Remove

### `python-dotenv==1.0.0`
- **Why unused:** Was loaded in `football_data.py` to read `FOOTBALL_DATA_API_KEY`
  from `.env`.  No API keys are needed in the new pipeline.
- **Remove from:** `requirements.txt`

---

## Files to Update / Clean

### `.env` and `.env.example`
- `FOOTBALL_DATA_API_KEY` is no longer used by any code path.
- `.env` can be emptied or deleted (it is already git-ignored).
- `.env.example` should be updated to remove the API key reference.

### `CLAUDE.md`
- References to football-data.org API, `scraper/fetch_data.py`, and
  `data/football_cache.json` should be updated to reflect the new pipeline.

---

## How to Perform the Cleanup

```bash
# Remove deprecated files
rm rasa/actions/football_data.py
rm -rf scraper/

# Remove python-dotenv from requirements.txt (edit the file)
# Then reinstall:
pip install -r requirements.txt

# Optionally clear .env
echo "" > .env
```
