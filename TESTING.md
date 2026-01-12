# Testing Guide

Step-by-step guide to test the Orin pipeline.

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager
- FFmpeg installed (`sudo apt install ffmpeg` or `brew install ffmpeg`)
- Docker (for local Qdrant)
- GPU recommended for embeddings (CPU works but slower)

## 1. Clone and Install

```bash
cd /path/to/orin/pipeline

# Install dependencies
uv sync
```

## 2. Get the LRCLib Database

Download the LRCLib SQLite dump and place it in the data directory:

```bash
mkdir -p data

# Download from LRCLib (check their site for latest dump URL)
# Place the file at: data/lrclib.db
```

Verify the database:

```bash
sqlite3 data/lrclib.db "SELECT COUNT(*) FROM tracks WHERE has_synced_lyrics = 1 AND instrumental = 0;"
```

## 3. Set Up API Keys

### Groq (Primary LLM - Free Tier)

1. Go to [console.groq.com](https://console.groq.com)
2. Sign up or log in
3. Navigate to **API Keys** in the sidebar
4. Click **Create API Key**
5. Copy the key (starts with `gsk_`)

### Together.ai (Fallback LLM)

1. Go to [api.together.xyz](https://api.together.xyz)
2. Sign up or log in
3. Go to **Settings** → **API Keys**
4. Copy your API key

### Create .env File

```bash
cp .env.example .env
```

Edit `.env` and add your keys:

```env
GROQ_API_KEY=gsk_your_key_here
TOGETHER_API_KEY=your_together_key_here
```

## 4. Dry Run Test (No Audio, No Storage)

Dry run tests the LLM segmentation without downloading audio or setting up Qdrant/R2. This verifies your API keys work.

```bash
uv run python -m src --test 5 --dry-run
```

**Expected output:**
```
Test mode: Processing 5 songs
Dry run mode - skipping audio and indexing

[1] Processing: Artist Name - Song Title
[2] Processing: Artist Name - Song Title
...

Results:
  Tracks processed: 5
  Tracks skipped:   0
  Segments indexed: 15
```

If you see errors about API keys, double-check your `.env` file.

---

## 5. Full Test Setup

For a complete end-to-end test, you need Qdrant and optionally R2.

### 5a. Set Up Qdrant (Local with Docker)

```bash
# Pull and run Qdrant
docker run -d --name qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v qdrant_storage:/qdrant/storage \
  qdrant/qdrant
```

Verify it's running:

```bash
curl http://localhost:6333/collections
# Should return: {"result":{"collections":[]},"status":"ok","time":...}
```

Your `.env` should have (these are defaults, so optional):

```env
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

### 5b. Set Up Cloudflare R2 (Optional)

Skip this section if you want snippets stored locally instead of cloud.

1. Log in to [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Go to **R2 Object Storage** in the sidebar
3. Click **Create bucket**, name it (e.g., `orin-snippets`)
4. Go to **Manage R2 API Tokens** → **Create API Token**
5. Select permissions: **Object Read & Write**
6. Select the bucket you created
7. Copy the **Access Key ID** and **Secret Access Key**
8. Note the **Endpoint URL** (format: `https://<account_id>.r2.cloudflarestorage.com`)

Add to `.env`:

```env
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET_NAME=orin-snippets
R2_ENDPOINT=https://your_account_id.r2.cloudflarestorage.com
```

**Enable Public Access (for CDN URLs):**

1. In R2 bucket settings, go to **Settings** → **Public access**
2. Enable **R2.dev subdomain** or set up a custom domain

### 5c. BGE-M3 Embedding Model

The model downloads automatically on first run (~2GB). No setup needed.

First run will show:
```
Downloading BAAI/bge-m3...
```

Subsequent runs use the cached model.

**GPU Notes:**
- CUDA GPU: Embeddings are fast (~100ms per text)
- CPU only: Slower (~2-5s per text) but works
- The model uses ~2GB VRAM

---

## 6. Full Test with 10 Songs

With Qdrant running (and optionally R2 configured):

```bash
uv run python -m src --test 10
```

**Expected output:**
```
Test mode: Processing 10 songs

[1] Processing: Artist - Song Title
[2] Processing: Artist - Song Title
...

Results:
  Tracks processed: 8
  Tracks skipped:   2
  Segments indexed: 24
```

Some tracks may be skipped due to:
- Version mismatch (YouTube audio duration doesn't match LRC)
- Download failures
- Too few lyrics lines

Check `output/skipped_songs.jsonl` for details on skipped tracks.

### Verify Qdrant Data

```bash
curl http://localhost:6333/collections/song_snippets
```

Should show `vectors_count` matching your indexed segments.

### Check Output Files

```bash
# Snippets (if R2 not configured)
ls output/snippets/

# Skipped songs log
cat output/skipped_songs.jsonl | head -5
```

---

## 7. Troubleshooting

### "GROQ_API_KEY environment variable not set"

Your `.env` file isn't being loaded. Make sure:
- File is named exactly `.env` (not `.env.txt`)
- File is in the `pipeline/` directory
- No quotes around the key value

### "yt-dlp failed" or download errors

```bash
# Update yt-dlp
uv pip install -U yt-dlp

# Test manually
yt-dlp --version
yt-dlp "ytsearch1:Artist Song official audio" --dump-json
```

### "Connection refused" to Qdrant

```bash
# Check if container is running
docker ps | grep qdrant

# Restart if needed
docker restart qdrant

# Check logs
docker logs qdrant
```

### Embedding model download fails

```bash
# Clear cache and retry
rm -rf ~/.cache/huggingface/hub/models--BAAI--bge-m3

# Or download manually
uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')"
```

### R2 upload fails

Verify your credentials:

```bash
# Test with AWS CLI (R2 is S3-compatible)
aws s3 ls s3://your-bucket-name \
  --endpoint-url https://your_account_id.r2.cloudflarestorage.com
```

---

## 8. Quick Reference

| Test Type | Command | Requirements |
|-----------|---------|--------------|
| Dry run | `uv run python -m src --test 5 --dry-run` | Groq API key only |
| Full test | `uv run python -m src --test 10` | Groq + Qdrant + (optional R2) |
| Single track | `uv run python -m src --track-id 12345` | Same as full test |
| All songs | `uv run python -m src --all` | Same as full test |

---

## 9. What Each Component Does

| Component | Purpose | Required For |
|-----------|---------|--------------|
| **Groq** | LLM to analyze lyrics and identify segments | All tests |
| **Together.ai** | Fallback if Groq fails | Recommended |
| **Qdrant** | Vector database for semantic search | Full test |
| **R2** | Cloud storage for audio snippets | Production (optional for testing) |
| **BGE-M3** | Generate embeddings for AI descriptions | Full test |
| **FFmpeg** | Slice audio into snippets | Full test |
| **yt-dlp** | Download audio from YouTube | Full test |
