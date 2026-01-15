# Current Session: Batch Segmentation for Groq Rate Limiting

Last Updated: 2026-01-15

## What Was Done

### Implemented Batch Segmentation
Reduced Groq API calls by 10x by batching multiple songs per LLM call.

**Impact:**
- 100 songs now requires 10 Groq calls instead of 100
- ~26% token savings from shared prompt overhead
- No dashboard changes needed (SSE events unchanged)

**Files Modified:**

`src/segmenter.py`:
- Added `BatchedSongResult` and `BatchSegmentationResult` dataclasses
- Added `BATCHED_SEGMENTATION_PROMPT` template for multi-song format
- Added `_build_batched_prompt()` function
- Added `_parse_batched_response()` function with per-song error isolation
- Added `segment_lyrics_batch()` async function
- Updated `_call_groq()` and `_call_together()` to accept `max_tokens` parameter

`src/config.py`:
- Added `ENABLE_BATCH_SEGMENTATION = True` toggle

`src/pipeline.py`:
- Added Phase 1: Batch segmentation before track loop
- Modified `process_track()` to accept optional `segmentation_cache` parameter
- Updated `run_pipeline()` for two-phase processing

## Architecture

```
Phase 1 - Batch Segmentation:
  For each batch of 10 tracks:
    1. Parse LRC for all tracks
    2. Filter valid tracks (≥4 lines)
    3. ONE Groq call → segments for all 10
    4. Cache results by track_id

Phase 2 - Per-Track Processing:
  For each track:
    1. Get cached segmentation (or call LLM if not batched)
    2. Download audio
    3. Check version match
    4. Slice → Upload → Embed segments
    5. Index to Qdrant
    → SSE events unchanged
```

### Graceful Rate Limit Handling
When Groq returns a 429 rate limit error:
- Returns immediately (doesn't block waiting)
- Shows friendly message: "Rate limited by LLM provider. Please try again in Xm Ys"
- Exits cleanly so user knows when to retry

**Implementation:**
- Added `retry_after_seconds` field to `SegmentationResult` and `BatchSegmentationResult`
- Catches `GroqRateLimitError` and extracts `retry-after` header
- Pipeline checks for rate limit and stops gracefully with the retry time

## Next Steps
- Test with `python -m src.cli --test 10` when rate limit resets (~16 minutes)
- Can add Together.ai as backup provider in `LLM_PROVIDERS` config

## Context Notes
- Batch size: 10 songs (configurable via `BATCH_SIZE_LLM`)
- Can disable batching via `ENABLE_BATCH_SEGMENTATION = False`
- Fallback: if no cache hit, calls `segment_lyrics()` directly
