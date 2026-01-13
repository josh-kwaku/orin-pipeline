"""
Playlist import runner service with event emission.

Wraps the curated import to emit SSE events during processing.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .event_manager import EventManager, event_manager


@dataclass
class ImportProgress:
    """Current import progress."""
    total_videos: int = 0
    processed: int = 0
    imported: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class ImportRunner:
    """
    Runs playlist import with event emission for real-time updates.
    """

    def __init__(self, event_mgr: EventManager = event_manager):
        self.event_manager = event_mgr
        self.running = False
        self.task_id: Optional[str] = None
        self.playlist_name: Optional[str] = None
        self.current_track: Optional[dict] = None
        self.progress = ImportProgress()
        self._stop_requested = False
        self._task: Optional[asyncio.Task] = None

    async def start(
        self,
        playlist_url: str,
        genre: str,
        db_path: Path,
        dry_run: bool = False,
    ) -> tuple[str, int]:
        """
        Start playlist import.

        Args:
            playlist_url: YouTube playlist URL
            genre: Genre tag for tracks
            db_path: Path to curated database
            dry_run: If True, don't write to database

        Returns:
            Tuple of (task_id, total_videos)
        """
        if self.running:
            raise RuntimeError("Import is already running")

        self.task_id = str(uuid.uuid4())
        self.running = True
        self._stop_requested = False
        self.progress = ImportProgress()
        self.current_track = None
        self.playlist_name = None

        # Start import in background
        self._task = asyncio.create_task(
            self._run(
                playlist_url=playlist_url,
                genre=genre,
                db_path=db_path,
                dry_run=dry_run,
            )
        )

        # Return immediately - total_videos will be sent via SSE
        return self.task_id, 0

    async def stop(self) -> bool:
        """Request import to stop."""
        if not self.running:
            return False
        self._stop_requested = True
        return True

    def get_status(self) -> dict:
        """Get current import status."""
        return {
            "running": self.running,
            "task_id": self.task_id,
            "playlist_name": self.playlist_name,
            "current_track": self.current_track,
            "progress": {
                "total_videos": self.progress.total_videos,
                "processed": self.progress.processed,
                "imported": self.progress.imported,
                "skipped": self.progress.skipped,
            },
            "errors": self.progress.errors[-10:],
        }

    async def _run(
        self,
        playlist_url: str,
        genre: str,
        db_path: Path,
        dry_run: bool,
    ) -> None:
        """Internal method to run the import."""
        # Import here to avoid circular imports
        from src.curated import (
            init_database,
            extract_playlist_videos,
            get_playlist_title,
            parse_video_title,
            _insert_track,
            _insert_skipped,
            DuplicateVideoError,
            DuplicateSongError,
        )
        from src.lrclib_api import search_lyrics
        import sqlite3

        try:
            # Initialize database
            if not dry_run:
                init_database(db_path)

            # Emit fetching event
            await self.event_manager.emit("import_fetching", {
                "task_id": self.task_id,
                "playlist_url": playlist_url,
            })

            # Get playlist info (this can take a few seconds)
            playlist_title = await asyncio.to_thread(get_playlist_title, playlist_url)
            videos = await asyncio.to_thread(extract_playlist_videos, playlist_url)

            self.playlist_name = playlist_title or "Unknown Playlist"
            self.progress.total_videos = len(videos)

            # Emit started event with total
            await self.event_manager.emit("import_started", {
                "task_id": self.task_id,
                "playlist_name": self.playlist_name,
                "total_videos": len(videos),
                "genre": genre,
            })

            # Insert playlist record
            playlist_id = 0
            if not dry_run:
                conn = sqlite3.connect(db_path)
                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO playlists (youtube_url, genre, name)
                        VALUES (?, ?, ?)
                        """,
                        (playlist_url, genre, playlist_title),
                    )
                    conn.commit()
                    cursor = conn.execute(
                        "SELECT id FROM playlists WHERE youtube_url = ?",
                        (playlist_url,),
                    )
                    playlist_id = cursor.fetchone()[0]
                finally:
                    conn.close()

            # Process each video
            for i, video in enumerate(videos, 1):
                if self._stop_requested:
                    await self.event_manager.emit("import_stopped", {
                        "task_id": self.task_id,
                        "reason": "user_requested",
                    })
                    break

                self.current_track = {
                    "index": i,
                    "total": len(videos),
                    "video_title": video.title[:80],
                    "video_id": video.video_id,
                }

                # Emit track processing event
                await self.event_manager.emit("import_track_processing", {
                    "task_id": self.task_id,
                    "index": i,
                    "total": len(videos),
                    "video_title": video.title[:80],
                    "stage": "parsing",
                })

                # Parse artist and title
                artist, song_name = parse_video_title(video.title)

                if not artist and song_name:
                    artist = video.uploader or ""
                    if artist.endswith(" - Topic"):
                        artist = artist[:-8]

                if not artist or not song_name:
                    self.progress.skipped += 1
                    self.progress.processed += 1
                    if not dry_run:
                        await asyncio.to_thread(
                            _insert_skipped, db_path, playlist_id, video, artist, song_name, "parse_failed"
                        )
                    await self.event_manager.emit("import_track_skipped", {
                        "task_id": self.task_id,
                        "index": i,
                        "video_title": video.title[:80],
                        "reason": "Could not parse artist/title",
                    })
                    continue

                # Update stage to searching lyrics
                await self.event_manager.emit("import_track_processing", {
                    "task_id": self.task_id,
                    "index": i,
                    "total": len(videos),
                    "video_title": video.title[:80],
                    "artist": artist,
                    "song_name": song_name,
                    "stage": "searching_lyrics",
                })

                # Search LRCLib for synced lyrics (run in thread to not block)
                result = await asyncio.to_thread(search_lyrics, artist, song_name, video.duration)

                if not result:
                    self.progress.skipped += 1
                    self.progress.processed += 1
                    if not dry_run:
                        await asyncio.to_thread(
                            _insert_skipped, db_path, playlist_id, video, artist, song_name, "no_lyrics"
                        )
                    await self.event_manager.emit("import_track_skipped", {
                        "task_id": self.task_id,
                        "index": i,
                        "video_title": video.title[:80],
                        "artist": artist,
                        "song_name": song_name,
                        "reason": "No synced lyrics found",
                    })
                    continue

                # Insert track
                if not dry_run:
                    try:
                        await asyncio.to_thread(
                            _insert_track, db_path, playlist_id, video, result, genre
                        )
                        self.progress.imported += 1
                        await self.event_manager.emit("import_track_imported", {
                            "task_id": self.task_id,
                            "index": i,
                            "artist": result.artist_name,
                            "title": result.track_name,
                            "video_title": video.title[:80],
                        })
                    except DuplicateVideoError:
                        self.progress.skipped += 1
                        await self.event_manager.emit("import_track_skipped", {
                            "task_id": self.task_id,
                            "index": i,
                            "video_title": video.title[:80],
                            "reason": "Already imported (same video)",
                        })
                    except DuplicateSongError:
                        self.progress.skipped += 1
                        await self.event_manager.emit("import_track_skipped", {
                            "task_id": self.task_id,
                            "index": i,
                            "video_title": video.title[:80],
                            "reason": "Already curated (different video)",
                        })
                else:
                    self.progress.imported += 1
                    await self.event_manager.emit("import_track_imported", {
                        "task_id": self.task_id,
                        "index": i,
                        "artist": result.artist_name,
                        "title": result.track_name,
                        "video_title": video.title[:80],
                        "dry_run": True,
                    })

                self.progress.processed += 1

            # Import complete
            await self.event_manager.emit("import_complete", {
                "task_id": self.task_id,
                "playlist_name": self.playlist_name,
                "playlist_id": playlist_id,
                "total_videos": self.progress.total_videos,
                "imported": self.progress.imported,
                "skipped": self.progress.skipped,
            })

        except Exception as e:
            error_msg = str(e)
            self.progress.errors.append(error_msg)
            await self.event_manager.emit("import_error", {
                "task_id": self.task_id,
                "error": error_msg,
            })

        finally:
            self.running = False
            self.current_track = None


# Global import runner instance
import_runner = ImportRunner()
