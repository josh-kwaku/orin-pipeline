# Known Issues

Last Updated: 2026-01-13

## Active Bugs 🐛

### Dashboard: Indexed card shows zero
The "Indexed" stats card on the dashboard always shows 0 even when segments have been indexed. Need to investigate the API response and dashboard component.

## Gotchas & Quirks ⚠️

### yt-dlp Rate Limiting
YouTube may rate limit after many downloads. Add delays if needed.

### LRCLib API Rate Limits
0.5s delay between requests (hardcoded). Respect the free service.

### Embedding Model GPU Memory
BGE-M3 uses ~2GB VRAM. Unload after batch processing.

---

## Resolved ✓

### Dashboard: Pipeline UX loading state (2026-01-13)
Fixed by adding proper state machine with explicit states (idle → connecting → starting → running → completed) and event-driven transitions via `pipeline_started` SSE event.

### Dashboard: Import progress not visible (2026-01-13)
Fixed by creating `ImportRunner` service with SSE events. Import now shows real-time progress with event log.
