"""
FastAPI application factory and configuration.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables before importing config-dependent modules
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

from .routes import playlists, tracks, stats, pipeline, search


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    yield
    # Shutdown - cleanup if needed


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Orin Pipeline API",
        description="REST API for the Orin music recommendation pipeline",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS configuration for frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev server
            "http://localhost:3000",  # Alternative dev port
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(stats.router, prefix="/api/v1", tags=["stats"])
    app.include_router(playlists.router, prefix="/api/v1", tags=["playlists"])
    app.include_router(tracks.router, prefix="/api/v1", tags=["tracks"])
    app.include_router(pipeline.router, prefix="/api/v1", tags=["pipeline"])
    app.include_router(search.router, prefix="/api/v1", tags=["search"])

    @app.get("/api/v1/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "ok"}

    return app


# Create app instance for uvicorn
app = create_app()
