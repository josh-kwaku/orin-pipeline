"""
Dependency injection for FastAPI routes.
"""

from pathlib import Path
from typing import Annotated

from fastapi import Depends

# Database paths
BASE_DIR = Path(__file__).parent.parent
CURATED_DB_PATH = BASE_DIR / "data" / "curated_tracks.sqlite"
PIPELINE_STATUS_DB = BASE_DIR / "data" / "pipeline_status.sqlite"


def get_curated_db_path() -> Path:
    """Get path to curated tracks database."""
    return CURATED_DB_PATH


def get_status_db_path() -> Path:
    """Get path to pipeline status database."""
    return PIPELINE_STATUS_DB


# Type aliases for dependency injection
CuratedDbPath = Annotated[Path, Depends(get_curated_db_path)]
StatusDbPath = Annotated[Path, Depends(get_status_db_path)]
