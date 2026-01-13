# Current Session: Pipeline & Import Loading UX Fix

Last Updated: 2026-01-13

## Active Work
- Fixed pipeline page loading/progress UX
- Added real-time progress tracking for playlist import

## Files Modified

### Backend
- `api/services/pipeline_runner.py` - Added `pipeline_started` event emission
- `api/services/import_runner.py` - **NEW** - Async import with SSE events
- `api/routes/pipeline.py` - Updated SSE endpoint docs for import events
- `api/routes/playlists.py` - Changed to async import with background task
- `api/schemas/playlist.py` - Updated response types for async import

### Frontend (orin-dashboard/)
- `src/api/types.ts` - Added import event types, `StartPipelineResponse`, `ImportPlaylistResponse`
- `src/api/client.ts` - Updated return types, added `stopImport`
- `src/pages/Pipeline.tsx` - Rewrote with proper state machine
- `src/pages/Playlists.tsx` - Added SSE progress tracking with event log

## Recent Changes

### Pipeline Page
- Added `pipeline_started` SSE event from backend (emitted before processing starts)
- Replaced multiple boolean states with single `PipelineState` enum
- State flow: idle → connecting → starting → running → completed/stopped/error
- Event-driven transitions instead of polling

### Playlist Import
- Created `ImportRunner` service (similar to `PipelineRunner`)
- Import now runs in background task, returns immediately
- SSE events: `import_fetching`, `import_started`, `import_track_processing`, `import_track_imported`, `import_track_skipped`, `import_complete`, `import_stopped`, `import_error`
- Frontend shows real-time progress: current track, imported/skipped counts
- Import log shows each track as it's processed
- Stop button to cancel mid-import

## Next Steps
- Test both pipeline and import with live servers
- Verify events flow correctly through shared SSE endpoint

## Context Notes
- Both pipeline and import use the same `event_manager` for SSE
- Single SSE endpoint `/pipeline/events` handles both event types
- Frontend filters events by type prefix (`import_*` vs `track_*`/`pipeline_*`)
