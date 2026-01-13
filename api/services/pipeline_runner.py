"""
Pipeline runner service with event emission.

Wraps the core pipeline to emit SSE events during processing.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Optional

from .event_manager import EventManager, event_manager
from src.pipeline_status import mark_processed


@dataclass
class PipelineProgress:
    """Current pipeline progress."""
    processed: int = 0
    skipped: int = 0
    total: int = 0
    segments_indexed: int = 0
    errors: list[str] = field(default_factory=list)


class PipelineRunner:
    """
    Runs the pipeline with event emission for real-time updates.
    """

    def __init__(self, event_mgr: EventManager = event_manager):
        self.event_manager = event_mgr
        self.running = False
        self.task_id: Optional[str] = None
        self.current_track: Optional[dict] = None
        self.progress = PipelineProgress()
        self._stop_requested = False
        self._task: Optional[asyncio.Task] = None

    async def start(
        self,
        source: str = "curated",
        genre: Optional[str] = None,
        limit: Optional[int] = None,
        dry_run: bool = False,
        reprocess: bool = False,
    ) -> tuple[str, int]:
        """
        Start pipeline processing.

        Args:
            source: "lrclib" or "curated"
            genre: Filter by genre (curated only)
            limit: Maximum tracks to process
            dry_run: Skip actual processing
            reprocess: Include already-processed tracks

        Returns:
            Tuple of (task_id, total_tracks)
        """
        if self.running:
            raise RuntimeError("Pipeline is already running")

        # Import here to avoid circular imports and ensure env is loaded
        from src.curated import get_curated_tracks, get_curated_track_count, CURATED_DB_PATH
        from src.db import get_tracks as get_lrclib_tracks, get_track_count as get_lrclib_count

        self.task_id = str(uuid.uuid4())
        self.running = True
        self._stop_requested = False
        self.progress = PipelineProgress()

        # Get track count
        if source == "curated":
            total = get_curated_track_count(db_path=CURATED_DB_PATH, genre=genre)
        else:
            total = get_lrclib_count()

        if limit:
            total = min(total, limit)

        self.progress.total = total

        # Start processing in background
        self._task = asyncio.create_task(
            self._run(
                source=source,
                genre=genre,
                limit=limit,
                dry_run=dry_run,
                reprocess=reprocess,
            )
        )

        return self.task_id, total

    async def stop(self) -> bool:
        """
        Request pipeline to stop.

        Returns:
            True if stop was requested
        """
        if not self.running:
            return False

        self._stop_requested = True
        return True

    def get_status(self) -> dict:
        """Get current pipeline status."""
        return {
            "running": self.running,
            "task_id": self.task_id,
            "current_track": self.current_track,
            "progress": {
                "processed": self.progress.processed,
                "skipped": self.progress.skipped,
                "total": self.progress.total,
                "segments_indexed": self.progress.segments_indexed,
            },
            "errors": self.progress.errors[-10:],  # Last 10 errors
        }

    async def _run(
        self,
        source: str,
        genre: Optional[str],
        limit: Optional[int],
        dry_run: bool,
        reprocess: bool,
    ) -> None:
        """Internal method to run the pipeline."""
        from src.curated import get_curated_tracks, CURATED_DB_PATH
        from src.pipeline import process_track
        from src.db import Track

        try:
            # Get tracks
            if source == "curated":
                tracks_gen = get_curated_tracks(
                    db_path=CURATED_DB_PATH,
                    genre=genre,
                    limit=limit,
                    exclude_processed=not reprocess,
                )
                # Convert generator to list for counting
                tracks = list(tracks_gen)
            else:
                # TODO: Implement LRCLib source
                tracks = []

            self.progress.total = len(tracks)

            for i, track_data in enumerate(tracks):
                if self._stop_requested:
                    await self.event_manager.emit("pipeline_stopped", {
                        "task_id": self.task_id,
                        "reason": "user_requested",
                    })
                    break

                # Create Track object for curated source
                track = Track(
                    id=track_data["id"],
                    name=track_data["name"],
                    artist_name=track_data["artist_name"],
                    album_name=track_data.get("album_name"),
                    duration=track_data["duration"],
                    synced_lyrics=track_data["synced_lyrics"],
                )

                self.current_track = {
                    "id": track.id,
                    "title": track.name,
                    "artist": track.artist_name,
                    "index": i + 1,
                    "total": self.progress.total,
                }

                # Emit track start event
                await self.event_manager.emit("track_start", self.current_track)

                try:
                    # Process the track
                    if not dry_run:
                        indexed, errors, _ = await process_track(
                            track=track,
                            dry_run=dry_run,
                            verbose=False,
                        )

                        self.progress.segments_indexed += indexed

                        if errors:
                            self.progress.skipped += 1
                            self.progress.errors.extend(errors)
                            await self.event_manager.emit("track_error", {
                                "track_id": track.id,
                                "errors": errors,
                            })
                        else:
                            # Mark as processed
                            mark_processed(source, track.id)
                            self.progress.processed += 1
                            await self.event_manager.emit("track_complete", {
                                "track_id": track.id,
                                "segments_indexed": indexed,
                            })
                    else:
                        self.progress.processed += 1
                        await self.event_manager.emit("track_complete", {
                            "track_id": track.id,
                            "segments_indexed": 0,
                            "dry_run": True,
                        })

                except Exception as e:
                    self.progress.skipped += 1
                    self.progress.errors.append(f"{track.name}: {str(e)}")
                    await self.event_manager.emit("track_error", {
                        "track_id": track.id,
                        "error": str(e),
                    })

            # Pipeline complete
            await self.event_manager.emit("pipeline_complete", {
                "task_id": self.task_id,
                "processed": self.progress.processed,
                "skipped": self.progress.skipped,
                "segments_indexed": self.progress.segments_indexed,
            })

        except Exception as e:
            await self.event_manager.emit("pipeline_error", {
                "task_id": self.task_id,
                "error": str(e),
            })

        finally:
            self.running = False
            self.current_track = None


# Global pipeline runner instance
pipeline_runner = PipelineRunner()
