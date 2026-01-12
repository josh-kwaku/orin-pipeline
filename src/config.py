"""
Configuration for the Orin pipeline.

NOTE: This module reads from environment variables.
      The .env file must be loaded by the entry point (run_pipeline.py)
      using python-dotenv BEFORE importing this module.

See RULES.md for security guidelines.
"""

import os
from pathlib import Path


# ===================
# Paths
# ===================
# Base directory (pipeline/)
BASE_DIR = Path(__file__).parent.parent

# LRCLib database path
LRCLIB_DB_PATH = Path(os.environ.get("LRCLIB_DB_PATH", BASE_DIR / "data" / "lrclib.sqlite3"))

# Output directories
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", BASE_DIR / "output"))
AUDIO_DIR = OUTPUT_DIR / "audio"
SNIPPETS_DIR = OUTPUT_DIR / "snippets"
LOGS_DIR = OUTPUT_DIR / "logs"

# Skipped songs log
SKIPPED_SONGS_LOG = OUTPUT_DIR / "skipped_songs.jsonl"


# ===================
# LRCLib Query Filters
# ===================
LRCLIB_FILTERS = {
    "has_synced_lyrics": True,
    "instrumental": False,
    "source": "lrclib",  # Official only
    "require_duration": True,
}


# ===================
# Audio Processing
# ===================
# Version matching tolerance (seconds)
DURATION_TOLERANCE = 2.0

# yt-dlp settings
YTDLP_FORMAT = "bestaudio/best"
SEARCH_RESULTS = 5  # Number of YouTube results to consider
YTDLP_SEARCH_PREFIX = f"ytsearch{SEARCH_RESULTS}:"

# Match scoring thresholds
MATCH_THRESHOLD = 50  # Minimum score to accept a match

# FFmpeg settings
AUDIO_CODEC = "libopus"
AUDIO_BITRATE = "96k"
SNIPPET_FORMAT = "opus"


# ===================
# LLM Settings
# ===================
# Segments per song (target)
TARGET_SEGMENTS_PER_SONG = 3
MIN_SEGMENT_DURATION = 10  # seconds
MAX_SEGMENT_DURATION = 20  # seconds

# Model preferences (tried in order)
LLM_PROVIDERS = ["groq"]
# LLM_PROVIDERS = ["groq", "together"]
LLM_MODEL_GROQ = "llama-3.3-70b-versatile"
LLM_MODEL_TOGETHER = "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"


# ===================
# Embedding Settings
# ===================
EMBEDDING_MODEL = "BAAI/bge-m3"
EMBEDDING_DIMENSION = 768  # Truncated from 1024


# ===================
# Qdrant Settings
# ===================
QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", 6333))
QDRANT_COLLECTION = "song_snippets"


# ===================
# Processing Settings
# ===================
# Batch sizes
BATCH_SIZE_LLM = 10  # Songs per LLM batch
BATCH_SIZE_EMBED = 50  # Embeddings per batch
BATCH_SIZE_INDEX = 100  # Qdrant upserts per batch

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 1.0  # seconds


# ===================
# Helper Functions
# ===================
def get_api_key(provider: str) -> str:
    """
    Get API key for a provider from environment variables.

    Args:
        provider: One of 'groq', 'together', 'r2'

    Returns:
        API key string

    Raises:
        ValueError: If API key not found in environment
    """
    key_map = {
        "groq": "GROQ_API_KEY",
        "together": "TOGETHER_API_KEY",
        "r2_access": "R2_ACCESS_KEY_ID",
        "r2_secret": "R2_SECRET_ACCESS_KEY",
        "qdrant": "QDRANT_API_KEY",
    }

    env_var = key_map.get(provider)
    if not env_var:
        raise ValueError(f"Unknown provider: {provider}")

    api_key = os.environ.get(env_var)
    if not api_key:
        raise ValueError(
            f"{env_var} environment variable not set. "
            f"Please add it to your .env file."
        )

    return api_key


def ensure_directories():
    """Create output directories if they don't exist."""
    for directory in [OUTPUT_DIR, AUDIO_DIR, SNIPPETS_DIR, LOGS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
