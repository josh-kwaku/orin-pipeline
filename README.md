# Orin Pipeline

Song processing pipeline for the Orin music communication app.

## Setup

### Prerequisites
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (fast Python package manager)
- FFmpeg (for audio processing)
- LRCLib SQLite database dump

### Installation

```bash
# Clone and navigate to pipeline directory
cd orin/pipeline

# Install dependencies with uv
uv sync

# Copy environment template and add your API keys
cp .env.example .env
# Edit .env with your API keys
```

### Environment Variables

See `.env.example` for required variables:
- `GROQ_API_KEY` - For LLM segmentation (free tier available)
- `TOGETHER_API_KEY` - Fallback LLM provider
- `LRCLIB_DB_PATH` - Path to LRCLib SQLite database

## Usage

```bash
# Run with uv
uv run python -m src.cli

# Or activate venv first
source .venv/bin/activate
python -m src.cli
```

### Commands

```bash
# Test with 10 songs
uv run python -m src.cli --test 10

# Process all songs
uv run python -m src.cli --all

# Process specific track by ID
uv run python -m src.cli --track-id 12345
```

## Project Structure

```
pipeline/
├── src/
│   ├── __init__.py
│   ├── config.py        # Configuration & settings
│   ├── db.py            # LRCLib database extraction
│   ├── lrc_parser.py    # Parse LRC format timestamps
│   ├── audio.py         # yt-dlp, ffprobe, ffmpeg
│   ├── segmenter.py     # LLM lyrics segmentation
│   ├── embedder.py      # BGE-M3 embeddings
│   ├── indexer.py       # Qdrant operations
│   └── pipeline.py      # Main orchestrator
├── data/
│   └── skipped_songs.jsonl
├── output/
│   ├── audio/           # Downloaded audio (temp)
│   ├── snippets/        # Processed .opus files
│   └── logs/
├── pyproject.toml
├── .env.example
├── .gitignore
└── RULES.md             # Security guidelines
```

## Working with Claude

This project uses a context management system for efficient collaboration across sessions.

**Starting a new session:**
```
"Hey Claude, read CLAUDE_START.md and let's continue"
```

Claude will read the context files (PROGRESS.md, DECISIONS.md, ISSUES.md) to understand the current state, then ask what you want to work on.

**Context files:**
- `CLAUDE_START.md` - Instructions for Claude (read this first)
- `PROGRESS.md` - Project status and completed features
- `DECISIONS.md` - Technical decisions with rationale
- `ISSUES.md` - Known bugs and gotchas
- `SESSION.md` - Current work focus (updated during session)
- `sessions/` - Archived session notes

## Security

See [RULES.md](RULES.md) for security guidelines.

**Important:**
- Never commit `.env` files
- Never hardcode API keys
- Always use `os.environ` for secrets
