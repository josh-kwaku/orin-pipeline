# Known Issues

Last Updated: 2026-01-13

## Active Bugs 🐛

### Dashboard: Indexed card shows zero
The "Indexed" stats card on the dashboard always shows 0 even when segments have been indexed. Need to investigate the API response and dashboard component.

### Dashboard: Pipeline UX loading state
The pipeline page loading/progress UX is still not working properly. The session-based approach was implemented but needs further debugging to ensure smooth transitions between Starting → Running → Completed states.

---

## Gotchas & Quirks ⚠️

### yt-dlp Rate Limiting
YouTube may rate limit after many downloads. Add delays if needed.

### LRCLib API Rate Limits
0.5s delay between requests (hardcoded). Respect the free service.

### Embedding Model GPU Memory
BGE-M3 uses ~2GB VRAM. Unload after batch processing.

---

## Resolved ✓

(None yet)
