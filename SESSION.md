# Current Session: Batch Segmentation & Rate Limit Handling

Last Updated: 2026-01-15

## What Was Done

### 1. Batch Segmentation (10x fewer API calls)
Reduced Groq API calls by batching multiple songs per LLM request.

**How it works:**
- Phase 1: Batch all tracks into groups of 10, segment via single LLM call each
- Phase 2: Process each track using cached segmentation results

**Files Modified:**
- `src/segmenter.py` - Added `segment_lyrics_batch()`, batch prompt, parsing
- `src/pipeline.py` - Two-phase processing with segmentation cache
- `src/config.py` - Added `ENABLE_BATCH_SEGMENTATION = True`

### 2. Graceful Rate Limit Handling
Instead of blocking for 5+ minutes on 429 errors, pipeline now exits immediately with retry info.

**How it works:**
- Catches `GroqRateLimitError` and extracts `retry-after` header
- Returns immediately with `retry_after_seconds` in result
- Pipeline/API emits friendly message with exact retry time

**Files Modified:**
- `src/segmenter.py` - Added `retry_after_seconds` to result dataclasses
- `src/pipeline.py` - Check for rate limit and exit gracefully
- `api/services/pipeline_runner.py` - Emit `rate_limited` SSE event

### 3. API Batch Segmentation
Updated the API pipeline runner to use batch segmentation like the CLI.

**New SSE Events:**
- `batch_segmentation_started` - Phase 1 begins
- `batch_segmentation_progress` - Batch X/Y complete
- `batch_segmentation_complete` - All segmentation cached
- `rate_limited` - Hit API limit (includes `retry_after_seconds`)

**Files Modified:**
- `api/services/pipeline_runner.py` - Full batch segmentation support
- `api/routes/pipeline.py` - Updated SSE event documentation

### 4. Dashboard Updates (orin-dashboard repo)
Frontend now handles all new events with proper UI.

**Features:**
- "Segmenting..." state during batch segmentation
- "Rate Limited" state with yellow warning box
- Live countdown timer showing time until retry
- "Ready to retry!" message when countdown reaches zero

**Files Modified:**
- `src/pages/Pipeline.tsx` - New states, event handlers, countdown UI
- `src/api/types.ts` - Updated PipelineEvent type

## Architecture

```
Phase 1 - Batch Segmentation:
  For each batch of 10 tracks:
    1. Parse LRC for all tracks
    2. Filter valid tracks (≥4 lines)
    3. ONE Groq call → segments for all 10
    4. Cache results by track_id
    → SSE: batch_segmentation_progress

Phase 2 - Per-Track Processing:
  For each track:
    1. Get cached segmentation (skip LLM call)
    2. Download audio
    3. Check version match
    4. Slice → Upload → Embed segments
    5. Index to Qdrant
    → SSE: track_start, track_complete

Rate Limit Hit:
  → SSE: rate_limited (with retry_after_seconds)
  → Pipeline stops gracefully
  → Dashboard shows countdown timer
```

## Testing

Once Groq rate limit resets, test with:
```bash
# CLI
python -m src.cli --test 10

# API (start server first)
uvicorn api.main:app --reload
# Then trigger from dashboard
```

## Context Notes
- Batch size: 10 songs (configurable via `BATCH_SIZE_LLM`)
- Can disable batching: `ENABLE_BATCH_SEGMENTATION = False`
- Groq free tier: 100k tokens/day limit
