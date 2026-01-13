# Orin Pipeline API & Dashboard Plan

> This plan documents the API and frontend dashboard for the Orin music pipeline.
> Read this file when resuming work on the API or dashboard.

## Overview

Build a web dashboard to orchestrate the Orin music pipeline, replacing CLI usage with a visual interface for playlist import, track processing, and recommendation testing.

## Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| API | FastAPI | Native async, matches existing pipeline |
| Frontend | React + Vite + Tailwind | Separate repo: `orin-dashboard/` |
| Real-time | Server-Sent Events (SSE) | Simpler than WebSockets for one-way updates |
| State | TanStack Query | Handles caching, loading states |
| UI Components | shadcn/ui | Polished components, minimal effort |

## Features (Priority Order)

### P0 - Core
1. **Dashboard** - Stats overview (tracks, segments, by genre)
2. **Playlist Import** - Add YouTube playlists with genre label
3. **Pipeline Control** - Start/stop processing with live progress
4. **Track Status View** - Filter by pending/processing/complete/failed

### P1 - Important
5. **Skipped Track Review** - See why tracks failed, retry
6. **Recommendation Playground** - Query vectors, preview audio

### P2 - Nice to Have
7. **Cost tracking** - LLM token usage estimates
8. **Duplicate detection** - Flag same song across playlists

---

## API Design

Base: `/api/v1`

### Playlists
```
POST   /playlists/import     { url, genre }  -> { task_id }
GET    /playlists            -> [{ id, name, genre, track_count }]
GET    /playlists/{id}       -> { playlist with tracks }
```

### Tracks
```
GET    /tracks               ?status=&genre=&limit=&offset=
GET    /tracks/skipped       ?playlist_id=
POST   /tracks/{id}/retry    -> { task_id }
```

### Pipeline
```
POST   /pipeline/start       { source, genre, limit, dry_run }
POST   /pipeline/stop
GET    /pipeline/status      -> { running, progress, current_track }
GET    /pipeline/events      SSE stream
```

### Search
```
POST   /search               { query, limit, filters }
GET    /stats                -> { totals, by_genre, by_status }
```

---

## File Structure

```
pipeline/                   # This repo
├── src/                    # Existing modules (unchanged)
├── api/                    # FastAPI app
│   ├── __init__.py
│   ├── main.py             # FastAPI app factory, CORS config
│   ├── deps.py             # Dependency injection
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── playlists.py
│   │   ├── tracks.py
│   │   ├── pipeline.py     # Includes SSE endpoint
│   │   ├── search.py
│   │   └── stats.py
│   ├── schemas/            # Pydantic models
│   │   ├── __init__.py
│   │   ├── playlist.py
│   │   ├── track.py
│   │   ├── pipeline.py
│   │   └── search.py
│   └── services/
│       ├── __init__.py
│       ├── pipeline_runner.py  # Wraps run_pipeline() with events
│       └── event_manager.py    # SSE broadcast manager
└── pyproject.toml          # Add: fastapi, uvicorn, sse-starlette

orin-dashboard/             # SEPARATE REPO
├── src/
│   ├── pages/
│   ├── components/
│   ├── hooks/
│   └── api/
├── package.json
└── vite.config.ts
```

---

## Implementation Phases

### Phase 1: API Foundation
- Create `api/` directory with FastAPI app
- Implement `/health`, `/stats`, `/playlists`, `/tracks` endpoints
- Wire up to existing `src/curated.py` and `src/db.py` functions
- Add dependencies to `pyproject.toml`
- Configure CORS for future frontend

**Files to create:**
- `api/__init__.py`
- `api/main.py` - FastAPI app with CORS
- `api/deps.py` - dependency injection
- `api/routes/__init__.py`
- `api/routes/playlists.py`
- `api/routes/tracks.py`
- `api/routes/stats.py`
- `api/schemas/*.py` - Pydantic models

**Files to modify:**
- `pyproject.toml` - add fastapi, uvicorn, sse-starlette

### Phase 2: Real-time Pipeline
- Create `EventManager` for SSE broadcasting
- Create `PipelineRunner` wrapper around `run_pipeline()`
- Add optional event callbacks to `process_track()` in `src/pipeline.py`
- Implement `/pipeline/start`, `/pipeline/stop`, `/pipeline/events`
- Implement `/search` endpoint

**Files to create:**
- `api/services/__init__.py`
- `api/services/event_manager.py`
- `api/services/pipeline_runner.py`
- `api/routes/pipeline.py`
- `api/routes/search.py`
- `api/schemas/pipeline.py`
- `api/schemas/search.py`

**Files to modify:**
- `src/pipeline.py` - add optional `on_event` callback parameter

### Phase 3: Frontend Setup (separate repo)
- Initialize Vite + React + TypeScript
- Configure Tailwind CSS and shadcn/ui
- Create layout (Sidebar, Header)
- Set up React Router and TanStack Query

### Phase 4: Core Pages
- Dashboard with stats cards
- Playlist list + import form
- Track table with status filters
- Pipeline control with live progress bar

### Phase 5: Advanced Features
- Skipped track review and retry
- Search playground with audio preview
- Polish (loading states, error handling)

---

## Key Implementation Details

### Adding Events to Pipeline

Modify `process_track()` to accept optional callback:

```python
# src/pipeline.py
async def process_track(
    track: Track,
    dry_run: bool = False,
    verbose: bool = True,
    on_event: Callable[[str, dict], Awaitable[None]] = None,  # NEW
) -> tuple[int, list[str], dict]:
    if on_event:
        await on_event("stage", {"stage": "downloading"})
    # ... existing code ...
```

### SSE Event Stream

```python
# api/routes/pipeline.py
@router.get("/events")
async def pipeline_events(request: Request):
    async def generator():
        queue = event_manager.subscribe()
        try:
            while not await request.is_disconnected():
                event = await queue.get()
                yield {"event": event["type"], "data": json.dumps(event["data"])}
        finally:
            event_manager.unsubscribe(queue)
    return EventSourceResponse(generator())
```

---

## Verification

```bash
# Start API server
uv run uvicorn api.main:app --reload --port 8000
```

### Phase 1 Tests
```bash
# Health check
curl http://localhost:8000/api/v1/health

# Get stats
curl http://localhost:8000/api/v1/stats

# List playlists
curl http://localhost:8000/api/v1/playlists

# Get tracks (with filters)
curl "http://localhost:8000/api/v1/tracks?status=pending&limit=10"

# Import playlist
curl -X POST http://localhost:8000/api/v1/playlists/import \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtube.com/playlist?list=XXX", "genre": "afrobeats"}'
```

### Phase 2 Tests
```bash
# Start pipeline (returns task_id)
curl -X POST http://localhost:8000/api/v1/pipeline/start \
  -H "Content-Type: application/json" \
  -d '{"source": "curated", "limit": 5}'

# Check pipeline status
curl http://localhost:8000/api/v1/pipeline/status

# SSE events (in separate terminal)
curl -N http://localhost:8000/api/v1/pipeline/events

# Stop pipeline
curl -X POST http://localhost:8000/api/v1/pipeline/stop

# Search
curl -X POST http://localhost:8000/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query": "sad love song", "limit": 5}'
```
