# Current Session: Fix test_search.py and Artist Name Parsing

Last Updated: 2026-01-12

## Active Work
- Fixed test_search.py KeyError for missing genre field
- Fixed artist name parsing issue in curated import
- Cleared all data for fresh start

## Files Modified
- `test_search.py` - Fixed KeyError by using `.get('genre', 'unknown')`
- `src/curated.py` - Added patterns for (Performance Video), (Live), (Acoustic) to `clean_title()`

## Recent Changes
- **Fix: test_search.py genre KeyError**
  - Older indexed tracks lacked `genre` field
  - Changed `payload['genre']` to `payload.get('genre', 'unknown')`

- **Fix: Artist name parsing in curated import**
  - Root cause: `clean_title()` didn't strip `(Performance Video)` suffix
  - YouTube title "Ayra Starr - Bloody Samaritan (Performance Video)" wasn't cleaned
  - LRCLib search then matched bad entry with YouTube title as track name
  - Added patterns: `(Performance Video)`, `(Live ...)`, `(Acoustic ...)`
  - Verified fix: now correctly parses to artist="Ayra Starr", song="Bloody Samaritan"

- **Data Reset**
  - Ran `clear-all --include-curated` to start fresh
  - Cleared: 41 Qdrant vectors, 4 pipeline status records, 4 curated tracks, audio snippets

## Next Steps
1. Re-import afrobeats playlist (user has URL)
2. Process tracks through pipeline
3. Re-run test_search.py to validate

## Context Notes
- LRCLib has some bad data (YouTube titles stored as track names)
- The `clean_title()` fix prevents matching bad LRCLib entries
- LRCLib database (sqlite dump) was preserved - only curated/processed data cleared
