# Technical Decisions

---

## 2026-01-12: LRCLib Title Variation Matching

**Context:** Playlist import failing to find lyrics for songs with featuring artists
**Decision:** Generate multiple title format variations before searching LRCLib API
**Files:** `src/lrclib_api.py`

**Problem:**
- YouTube titles: "Bad Vibes ft. Seyi Vibez"
- LRCLib storage: "Bad Vibes (feat. Seyi Vibez)"
- Exact match searches were failing

**Implementation:**
- Added `_generate_title_variations()` function
- Tries 5+ variations per search:
  - Original format
  - "(feat. Artist)"
  - "feat. Artist"
  - "ft. Artist"
  - "(ft. Artist)"
  - Base title without featuring artist
- Applied to both exact match (with/without duration) and fuzzy search

**Impact:**
- Kwesi Arthur - Baajo: Found (was failing before)
- Ayra Starr - Bad Vibes: Found (was failing before)
- Import success rate significantly improved

---

## 2026-01-12: Genre Detection via LLM

**Context:** LRCLib database is Western-heavy, need genre diversity
**Decision:** LLM determines genre for ALL tracks during segmentation
**Files:** `src/segmenter.py`, `src/indexer.py`, `src/pipeline.py`

**Rationale:**
- Ensures consistent genre tagging across curated + LRCLib sources
- LLM already sees artist name + lyrics context
- Enables genre filtering at query time (Qdrant)
- Added genre normalization with common aliases

**Alternatives Considered:**
- Manual genre from curated playlists: Inconsistent with LRCLib tracks
- Post-processing genre classifier: Extra model, more complexity

**Implementation:**
- Added `genre` field to segmentation prompt
- Normalize to valid genres with alias mapping
- Store as required field in Qdrant payload

---

## 2026-01-12: Curated Playlists Import

**Context:** LRCLib database lacks Afro, Reggaeton, Dancehall representation
**Decision:** Separate SQLite DB for curated tracks from YouTube playlists
**Files:** `src/curated.py`, `src/lrclib_api.py`, `src/cli.py`

**Rationale:**
- Don't pollute main LRCLib database
- Track which tracks came from curated sources
- Can re-import playlists if needed
- Separate skip tracking for manual review

**Implementation:**
- `data/curated_tracks.sqlite` with playlists/tracks/skipped_tracks tables
- YouTube playlist URL + genre label → yt-dlp metadata
- Parse artist/title from video titles
- LRCLib API for synced lyrics
- Run through same pipeline as LRCLib tracks

---

## 2026-01-12: Cover Version Detection

**Context:** Home Free's cover returned instead of The Longest Johns original
**Decision:** Penalize candidates where title matches but artist doesn't
**Files:** `src/audio.py` (score_candidate function)

**Rationale:**
- Covers often have similar duration, pass duration check
- Title match alone is insufficient
- Need artist match for authenticity

**Implementation:**
- Added -30 penalty when title_matched && !artist_matched
- Forces candidates to match both title AND artist/uploader
- Prevents covers from winning over originals

---

## 2026-01-12: Multi-Result YouTube Search

**Context:** `ytsearch1:` returned Wellerman instead of Blow The Man Down
**Decision:** Fetch 5 candidates, score, pick best match
**Files:** `src/audio.py`, `src/config.py`

**Rationale:**
- YouTube ranks by popularity/engagement, not query accuracy
- Popular songs dominate search results for artists with breakout hits
- Single-result approach fails for less popular tracks

**Implementation:**
- Changed to `ytsearch5:`
- Score candidates by title match (+50), artist match (+30), duration (+20)
- Fuzzy string matching for typo tolerance
- Minimum threshold of 50 points to accept
- Log alternatives for debugging

**Metrics:**
- Title match: +50 (most important)
- Artist in title: +40, in uploader: +30
- Duration within 1s: +20, 2s: +10, 5s: +5, beyond: -20
- Official channel: +10

---

## 2026-01-11: Embedding Model Choice

**Decision:** BGE-M3 for text embeddings
**Files:** `src/embedder.py`

**Rationale:**
- Strong multilingual support (English + Afro/Latin languages)
- 768-dimensional embeddings (good expressiveness)
- Good performance on emotional/semantic content
- Works on-device and server-side

**Alternatives Considered:**
- MiniLM: Smaller (384D) but less expressive
- OpenAI embeddings: API costs, not self-hosted

---

## 2026-01-11: LLM Provider Strategy

**Decision:** Groq primary, Together.ai fallback
**Files:** `src/segmenter.py`, `src/config.py`

**Rationale:**
- Groq has free tier (save costs during development)
- Groq is rate-limited (need fallback)
- Together.ai has Llama 3 70B at ~$0.60/1M tokens
- Retry logic with exponential backoff

**Cost Estimate:**
- 245k songs × 3 segments = ~735k LLM calls
- Groq free tier covers ~50-100k calls
- Together.ai for remaining: $37-60 total
