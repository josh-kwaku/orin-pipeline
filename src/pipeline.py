"""
Main pipeline orchestrator.

Coordinates the full processing flow:
1. Extract tracks from LRCLib database
2. Parse LRC lyrics for timestamps
3. Download audio via yt-dlp
4. Validate version match (duration check)
5. Segment lyrics via LLM
6. Slice audio for each segment
7. Upload snippets to R2
8. Generate embeddings
9. Index to Qdrant

Entry point loads .env before importing this module.
"""

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from .audio import (
    check_version_match,
    cleanup_audio_file,
    download_audio,
    log_skipped_song,
    slice_audio,
)
from .config import (
    BATCH_SIZE_LLM,
    DURATION_TOLERANCE,
    ENABLE_BATCH_SEGMENTATION,
    LLM_PROVIDERS,
    OUTPUT_DIR,
    QDRANT_HOST,
    ensure_directories,
)
from .db import Track, get_track_by_id, get_tracks
from .curated import get_curated_tracks, get_curated_track_count, CURATED_DB_PATH
from .embedder import embed_text, get_device_info, unload_model
from .indexer import (
    SnippetPayload,
    generate_snippet_id,
    upsert_snippets,
)
from .lrc_parser import parse_lrc, validate_segment_lines
from .pipeline_status import mark_processed
from .segmenter import (
    BatchedSongResult,
    segment_lyrics,
    segment_lyrics_batch,
    validate_segments,
)
from .storage import is_r2_configured, upload_snippet
from . import logger


@dataclass
class ProcessingStats:
    """Statistics from pipeline run."""

    tracks_processed: int = 0
    tracks_skipped: int = 0
    segments_created: int = 0
    segments_indexed: int = 0
    errors: list[str] = field(default_factory=list)


def save_segmentation_results(
    results: list[dict[str, object]],
    output_path: Optional[Path] = None,
) -> Path:
    """
    Save segmentation results to a JSON file.

    Args:
        results: List of segmentation result dictionaries
        output_path: Optional custom output path

    Returns:
        Path to the saved file
    """
    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = OUTPUT_DIR / f"segmentation_results_{timestamp}.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    return output_path


async def process_track(
    track: Track,
    dry_run: bool = False,
    verbose: bool = True,
    segmentation_cache: Optional[dict[int, BatchedSongResult]] = None,
) -> tuple[int, list[str], Optional[dict]]:
    """
    Process a single track through the full pipeline.

    Args:
        track: Track from LRCLib database
        dry_run: If True, skip audio download and indexing
        verbose: If True, log detailed progress
        segmentation_cache: Pre-computed segmentation results by track_id (from batch)

    Returns:
        Tuple of (segments_indexed, error_messages, segmentation_data)
        segmentation_data is only populated during dry_run
    """
    errors = []

    # 1. Parse LRC lyrics
    if verbose:
        logger.print_step("Parsing lyrics", f"{track.duration:.0f}s duration")
    parsed_lrc = parse_lrc(track.synced_lyrics)
    if parsed_lrc.total_lines < 4:
        if verbose:
            logger.print_skip(f"Too few lines ({parsed_lrc.total_lines})")
        log_skipped_song(
            track_id=track.id,
            title=track.name,
            artist=track.artist_name,
            lrc_duration=track.duration,
            audio_duration=None,
            drift=None,
            reason="too_few_lines",
            error=f"Only {parsed_lrc.total_lines} lines",
        )
        return 0, [f"Track {track.id}: Too few lyrics lines"], None

    if verbose:
        logger.print_success(f"Parsed {parsed_lrc.total_lines} lines")

    # 2. Download audio
    if not dry_run:
        if verbose:
            logger.print_step("Downloading audio")
        download_result = download_audio(
            track.artist_name, track.name, track.duration
        )

        if not download_result.success:
            if verbose:
                logger.print_error(f"Download failed: {download_result.error}")
            log_skipped_song(
                track_id=track.id,
                title=track.name,
                artist=track.artist_name,
                lrc_duration=track.duration,
                audio_duration=None,
                drift=None,
                reason="download_failed",
                yt_url=download_result.yt_url,
                error=download_result.error,
            )
            return 0, [f"Track {track.id}: Download failed - {download_result.error}"], None

        if verbose:
            logger.print_success(f"Downloaded ({download_result.duration:.0f}s)")

        # 3. Check version match
        if download_result.duration:
            is_match, drift = check_version_match(
                track.duration,
                download_result.duration,
                DURATION_TOLERANCE,
            )

            if not is_match:
                if verbose:
                    logger.print_skip(f"Version mismatch (drift: {drift:.1f}s)")
                log_skipped_song(
                    track_id=track.id,
                    title=track.name,
                    artist=track.artist_name,
                    lrc_duration=track.duration,
                    audio_duration=download_result.duration,
                    drift=drift,
                    reason="version_mismatch",
                    yt_url=download_result.yt_url,
                )
                if download_result.file_path:
                    cleanup_audio_file(download_result.file_path)
                return 0, [f"Track {track.id}: Version mismatch (drift: {drift:.1f}s)"], None

        audio_file = download_result.file_path
        if audio_file is None:
            return 0, [f"Track {track.id}: Download succeeded but no file path"], None
    else:
        if verbose:
            logger.print_step("Skipping audio download", "dry run")
        audio_file = None

    # 4. Segment lyrics via LLM (use cache if available)
    cached_result = segmentation_cache.get(track.id) if segmentation_cache else None

    if cached_result is not None:
        # Use pre-computed batch segmentation
        if verbose:
            logger.print_step("Using cached segmentation", "from batch")

        if cached_result.error or not cached_result.segments:
            if verbose:
                logger.print_error(f"Segmentation failed: {cached_result.error or 'no segments'}")
            if audio_file:
                cleanup_audio_file(audio_file)
            log_skipped_song(
                track_id=track.id,
                title=track.name,
                artist=track.artist_name,
                lrc_duration=track.duration,
                audio_duration=None,
                drift=None,
                reason="segmentation_failed",
                error=cached_result.error or "no segments in batch result",
            )
            return 0, [f"Track {track.id}: Segmentation failed - {cached_result.error}"], None

        # Extract from cached result
        segments = cached_result.segments
        genre = cached_result.genre
        provider = "batch"

        if verbose:
            logger.print_success(
                f"Found {len(segments)} segments "
                f"via batch (genre: {genre})"
            )
    else:
        # No cache - call LLM directly
        if verbose:
            logger.print_step("Segmenting lyrics via LLM")
        segmentation_result = await segment_lyrics(
            lyrics=parsed_lrc.plain_lyrics,
            title=track.name,
            artist=track.artist_name,
        )

        if not segmentation_result.success:
            # Check for rate limiting
            if segmentation_result.retry_after_seconds is not None:
                retry_mins = int(segmentation_result.retry_after_seconds // 60)
                retry_secs = int(segmentation_result.retry_after_seconds % 60)
                if verbose:
                    logger.print_warning(
                        f"Rate limited by LLM provider. "
                        f"Please try again in {retry_mins}m {retry_secs}s"
                    )
                if audio_file:
                    cleanup_audio_file(audio_file)
                return 0, [f"Rate limited: retry in {retry_mins}m {retry_secs}s"], None

            if verbose:
                logger.print_error(f"Segmentation failed: {segmentation_result.error}")
            if audio_file:
                cleanup_audio_file(audio_file)
            log_skipped_song(
                track_id=track.id,
                title=track.name,
                artist=track.artist_name,
                lrc_duration=track.duration,
                audio_duration=None,
                drift=None,
                reason="segmentation_failed",
                error=segmentation_result.error,
            )
            return 0, [f"Track {track.id}: Segmentation failed - {segmentation_result.error}"], None

        # Extract from LLM result
        segments = segmentation_result.segments
        genre = segmentation_result.genre
        provider = segmentation_result.provider

        if verbose:
            logger.print_success(
                f"Found {len(segments)} segments "
                f"via {provider} "
                f"(genre: {genre})"
            )

    # 5. Validate segments
    valid_segments, validation_errors = validate_segments(
        segments,
        parsed_lrc.total_lines,
    )
    errors.extend(validation_errors)

    if not valid_segments:
        if verbose:
            logger.print_error("No valid segments after validation")
        if audio_file:
            cleanup_audio_file(audio_file)
        return 0, errors + [f"Track {track.id}: No valid segments"], None

    # 6. Process each segment
    if verbose:
        logger.print_step(f"Processing {len(valid_segments)} segments")

    vectors = []
    payloads = []

    for i, segment in enumerate(valid_segments, 1):
        if verbose:
            logger.print_segment_info(
                i,
                len(valid_segments),
                segment.primary_emotion,
                segment.energy,
                f"{segment.start_line}-{segment.end_line}",
            )
        # Validate line numbers against parsed LRC
        is_valid, error_msg = validate_segment_lines(
            parsed_lrc,
            segment.start_line,
            segment.end_line,
        )

        if not is_valid:
            errors.append(f"Segment validation: {error_msg}")
            continue

        # Get timestamps from LRC
        start_ts, end_ts = parsed_lrc.get_segment_timestamps(
            segment.start_line,
            segment.end_line,
        )

        if start_ts is None or end_ts is None:
            errors.append(f"Could not get timestamps for lines {segment.start_line}-{segment.end_line}")
            continue

        # Slice audio (if not dry run)
        snippet_id = generate_snippet_id()
        snippet_local_path = None

        if not dry_run and audio_file:
            slice_result = slice_audio(
                input_file=audio_file,
                start_time=start_ts,
                end_time=end_ts,
                output_name=snippet_id,
            )

            if not slice_result.success or slice_result.file_path is None:
                errors.append(f"Slice failed: {slice_result.error}")
                continue

            snippet_local_path = slice_result.file_path

            # Upload to R2 if configured
            if is_r2_configured():
                upload_result = await upload_snippet(
                    file_path=snippet_local_path,
                    snippet_id=snippet_id,
                )

                if not upload_result.success or upload_result.url is None:
                    errors.append(f"R2 upload failed: {upload_result.error}")
                    cleanup_audio_file(snippet_local_path)
                    continue

                snippet_url = upload_result.url

                # Clean up local snippet after successful upload
                cleanup_audio_file(snippet_local_path)
            else:
                # No R2 configured - keep local path
                snippet_url = str(snippet_local_path)
        else:
            snippet_url = f"dry-run://{snippet_id}"

        # Generate embedding
        embedding_result = embed_text(segment.ai_description)

        if not embedding_result.success or embedding_result.vector is None:
            errors.append(f"Embedding failed: {embedding_result.error}")
            continue

        # Build payload
        payload = SnippetPayload(
            snippet_id=snippet_id,
            song_title=track.name,
            artist=track.artist_name,
            album=track.album_name,
            lyrics=segment.lyrics,
            ai_description=segment.ai_description,
            snippet_url=snippet_url,
            start_time=start_ts,
            end_time=end_ts,
            primary_emotion=segment.primary_emotion,
            secondary_emotion=segment.secondary_emotion,
            energy=segment.energy,
            tone=segment.tone,
            genre=genre or "other",
            track_id=track.id,
        )

        vectors.append(embedding_result.vector.tolist())
        payloads.append(payload)

    # 7. Index to Qdrant
    indexed_count = 0

    if vectors and not dry_run:
        if verbose:
            logger.print_step("Indexing to Qdrant", f"{len(vectors)} vectors")
        index_result = await upsert_snippets(vectors, payloads)

        if index_result.success:
            indexed_count = index_result.indexed_count
            if verbose:
                logger.print_success(f"Indexed {indexed_count} segments")
        else:
            if verbose:
                logger.print_error(f"Indexing failed: {index_result.error}")
            errors.append(f"Indexing failed: {index_result.error}")

    elif vectors and dry_run:
        indexed_count = len(vectors)  # Would have indexed this many
        if verbose:
            logger.print_success(f"Would index {indexed_count} segments (dry run)")

    # Cleanup full audio file
    if audio_file:
        cleanup_audio_file(audio_file)

    # Build segmentation data for dry run output
    segmentation_data = None
    if dry_run and valid_segments:
        segmentation_data = {
            "track_id": track.id,
            "title": track.name,
            "artist": track.artist_name,
            "album": track.album_name,
            "duration": track.duration,
            "total_lines": parsed_lrc.total_lines,
            "genre": genre,
            "provider": provider,
            "segments": [
                {
                    "start_line": seg.start_line,
                    "end_line": seg.end_line,
                    "lyrics": seg.lyrics,
                    "ai_description": seg.ai_description,
                    "primary_emotion": seg.primary_emotion,
                    "secondary_emotion": seg.secondary_emotion,
                    "energy": seg.energy,
                    "tone": seg.tone,
                }
                for seg in valid_segments
            ],
        }

    return indexed_count, errors, segmentation_data


async def run_pipeline(
    limit: Optional[int] = None,
    track_id: Optional[int] = None,
    dry_run: bool = False,
    verbose: bool = True,
    source: str = "lrclib",
    genre: Optional[str] = None,
    reprocess: bool = False,
) -> ProcessingStats:
    """
    Run the full processing pipeline.

    Args:
        limit: Maximum number of tracks to process (None = all)
        track_id: Process a specific track by ID
        dry_run: If True, skip audio download and indexing
        verbose: If True, show detailed progress
        source: Data source - "lrclib" (default) or "curated"
        genre: Filter by genre (for curated source)
        reprocess: If True, include already-processed tracks

    Returns:
        ProcessingStats with counts and errors
    """
    ensure_directories()
    stats = ProcessingStats()

    # Print configuration summary
    if verbose:
        logger.print_header("Orin Pipeline")
        logger.print_config_summary(
            dry_run=dry_run,
            r2_configured=is_r2_configured(),
            qdrant_host=QDRANT_HOST,
            llm_providers=LLM_PROVIDERS,
        )

        # Show device info
        device_info = get_device_info()
        cuda_name = device_info.get("cuda_device_name")
        logger.print_device_info(
            str(device_info["device"]),
            str(cuda_name) if cuda_name else None,
        )

        # Show source info
        if source == "curated":
            logger.console.print(f"  Source: [cyan]curated[/cyan] (genre: {genre or 'all'})")

    # Get tracks
    if verbose:
        logger.print_step(f"Loading tracks from {'curated database' if source == 'curated' else 'LRCLib database'}")

    if source == "curated":
        # Load from curated database
        if not CURATED_DB_PATH.exists():
            stats.errors.append("Curated database not found. Import playlists first.")
            if verbose:
                logger.print_error("Curated database not found. Run: uv run python -m src.cli import-playlist --url ... --genre ...")
            return stats

        curated_data = list(get_curated_tracks(
            db_path=CURATED_DB_PATH,
            genre=genre,
            limit=limit,
            exclude_processed=not reprocess,
        ))

        # Convert to Track objects
        tracks = [
            Track(
                id=t["id"],
                name=t["name"],
                artist_name=t["artist_name"],
                album_name=t["album_name"],
                duration=t["duration"],
                synced_lyrics=t["synced_lyrics"],
            )
            for t in curated_data
        ]
    elif track_id:
        # Use efficient single-track lookup
        single_track = get_track_by_id(track_id)
        if single_track is None:
            stats.errors.append(f"Track {track_id} not found")
            if verbose:
                logger.print_error(f"Track {track_id} not found")
            return stats
        tracks = [single_track]
    else:
        tracks = list(get_tracks(limit=limit, exclude_processed=not reprocess))

    if verbose:
        logger.print_success(f"Found {len(tracks)} tracks to process")

    # Phase 1: Batch segmentation (if enabled)
    segmentation_cache: dict[int, BatchedSongResult] = {}

    if ENABLE_BATCH_SEGMENTATION and tracks:
        if verbose:
            logger.print_step("Phase 1: Batch segmentation", f"{len(tracks)} tracks in batches of {BATCH_SIZE_LLM}")

        total_batches = (len(tracks) + BATCH_SIZE_LLM - 1) // BATCH_SIZE_LLM

        for batch_num, batch_start in enumerate(range(0, len(tracks), BATCH_SIZE_LLM), 1):
            batch = tracks[batch_start:batch_start + BATCH_SIZE_LLM]

            if verbose:
                logger.print_step(f"Batch {batch_num}/{total_batches}", f"{len(batch)} tracks")

            # Pre-parse lyrics and filter valid tracks
            songs_for_llm: list[tuple[str, str, str, int]] = []
            for track in batch:
                parsed = parse_lrc(track.synced_lyrics)
                if parsed.total_lines >= 4:
                    songs_for_llm.append((
                        parsed.plain_lyrics,
                        track.name,
                        track.artist_name,
                        track.id,
                    ))

            if songs_for_llm:
                # Flush stdout to prevent Rich console buffering deadlock with async
                sys.stdout.flush()
                # Single LLM call for entire batch
                batch_result = await segment_lyrics_batch(songs_for_llm)

                # Check for rate limiting - stop gracefully if hit
                if batch_result.retry_after_seconds is not None:
                    retry_mins = int(batch_result.retry_after_seconds // 60)
                    retry_secs = int(batch_result.retry_after_seconds % 60)
                    if verbose:
                        logger.print_warning(
                            f"Rate limited by LLM provider. "
                            f"Please try again in {retry_mins}m {retry_secs}s"
                        )
                    stats.errors.append(
                        f"Rate limited: retry in {retry_mins}m {retry_secs}s"
                    )
                    # Return early - can't continue without segmentation
                    return stats

                # Cache results by track_id
                for song_result in batch_result.song_results:
                    segmentation_cache[song_result.track_id] = song_result

                if verbose:
                    success_count = sum(1 for r in batch_result.song_results if r.segments)
                    logger.print_success(f"Segmented {success_count}/{len(songs_for_llm)} tracks")

        if verbose:
            logger.print_success(f"Phase 1 complete: {len(segmentation_cache)} tracks in cache")

    # Collect segmentation results for dry run
    segmentation_results: list[dict[str, object]] = []

    # Phase 2: Process each track
    for i, track in enumerate(tracks, 1):
        try:
            if verbose:
                logger.print_track_header(i, len(tracks), track.artist_name, track.name)

            indexed, errors, seg_data = await process_track(
                track,
                dry_run=dry_run,
                verbose=verbose,
                segmentation_cache=segmentation_cache if ENABLE_BATCH_SEGMENTATION else None,
            )

            if indexed > 0:
                stats.tracks_processed += 1
                stats.segments_indexed += indexed
                # Mark as processed (skip on dry_run since nothing was indexed)
                if not dry_run:
                    mark_processed(source, track.id)
            else:
                stats.tracks_skipped += 1

            stats.errors.extend(errors)

            # Collect segmentation data for dry run output
            if seg_data is not None:
                segmentation_results.append(seg_data)

        except Exception as e:
            stats.tracks_skipped += 1
            stats.errors.append(f"Track {track.id} exception: {str(e)}")
            if verbose:
                logger.print_error(f"Exception: {str(e)}")

    # Unload embedding model to free GPU memory
    if verbose:
        logger.print_step("Unloading embedding model")
    unload_model()

    # Save segmentation results for dry run
    if dry_run and segmentation_results:
        output_file = save_segmentation_results(segmentation_results)
        if verbose:
            logger.print_success(f"Saved segmentation results to {output_file}")

    # Print final summary
    if verbose:
        logger.print_final_summary(
            stats.tracks_processed,
            stats.tracks_skipped,
            stats.segments_indexed,
            stats.errors,
        )

    return stats
