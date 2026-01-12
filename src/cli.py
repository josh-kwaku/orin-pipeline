"""
CLI entry point for Orin pipeline.

This is the ONLY place where .env is loaded.
All other modules access environment variables via os.environ.

Usage:
    # Process songs from LRCLib database
    uv run python -m src.cli --test 10
    uv run python -m src.cli --track-id 12345
    uv run python -m src.cli --all

    # Import curated playlists
    uv run python -m src.cli import-playlist --url "..." --genre "afro"
    uv run python -m src.cli list-playlists

    # Process curated tracks
    uv run python -m src.cli --source curated --genre afro --test 10
"""

import argparse
import asyncio
import sys

# Load .env BEFORE importing other modules
from dotenv import load_dotenv
load_dotenv()

import shutil

from .pipeline import run_pipeline
from .curated import (
    import_playlist,
    list_playlists,
    list_skipped,
    get_curated_track_count,
    CURATED_DB_PATH,
)
from .pipeline_status import clear_processed, get_processed_count, PIPELINE_STATUS_DB
from .indexer import clear_collection, get_collection_count
from .config import SNIPPETS_DIR
from . import logger


async def cmd_run(args):
    """Run the main pipeline."""
    limit = None
    track_id = None

    if args.test:
        limit = args.test
    elif args.track_id:
        track_id = args.track_id
    elif args.all:
        logger.console.print("[bold yellow]Warning:[/bold yellow] Processing ALL songs")
        confirm = input("Type 'yes' to confirm: ")
        if confirm.lower() != "yes":
            logger.console.print("[red]Aborted[/red]")
            sys.exit(1)

    # Run pipeline
    await run_pipeline(
        limit=limit,
        track_id=track_id,
        dry_run=args.dry_run,
        verbose=not args.quiet,
        source=args.source,
        genre=args.genre,
        reprocess=args.reprocess,
    )


def cmd_import_playlist(args):
    """Import a YouTube playlist."""
    logger.console.print(f"\n[bold]Importing playlist[/bold]")
    logger.console.print(f"URL: {args.url}")
    logger.console.print(f"Genre: {args.genre}")

    if args.dry_run:
        logger.console.print("[yellow]Dry run mode - no database writes[/yellow]\n")

    result = import_playlist(
        playlist_url=args.url,
        genre=args.genre,
        db_path=CURATED_DB_PATH,
        dry_run=args.dry_run,
        verbose=True,
    )

    logger.console.print(f"\n[bold]Import Complete[/bold]")
    logger.console.print(f"  Total videos: {result.total_videos}")
    logger.console.print(f"  [green]Imported: {result.imported}[/green]")
    logger.console.print(f"  [yellow]Skipped: {result.skipped}[/yellow]")

    if result.errors:
        logger.console.print(f"  [red]Errors: {len(result.errors)}[/red]")
        for err in result.errors[:5]:
            logger.console.print(f"    - {err}")


def cmd_list_playlists(args):
    """List imported playlists."""
    playlists = list_playlists(CURATED_DB_PATH)

    if not playlists:
        logger.console.print("[yellow]No playlists imported yet[/yellow]")
        return

    logger.console.print(f"\n[bold]Imported Playlists ({len(playlists)})[/bold]\n")

    for p in playlists:
        logger.console.print(f"[bold]{p['name'] or 'Unnamed'}[/bold]")
        logger.console.print(f"  Genre: {p['genre']}")
        logger.console.print(f"  Tracks: {p['track_count']}")
        logger.console.print(f"  URL: {p['youtube_url']}")
        logger.console.print(f"  Imported: {p['imported_at']}")
        logger.console.print()


def cmd_list_skipped(args):
    """List skipped tracks for review."""
    skipped = list_skipped(CURATED_DB_PATH, args.playlist_id)

    if not skipped:
        logger.console.print("[green]No skipped tracks[/green]")
        return

    logger.console.print(f"\n[bold]Skipped Tracks ({len(skipped)})[/bold]\n")

    for s in skipped[:50]:  # Limit output
        logger.console.print(f"[yellow]{s['youtube_title'][:60]}[/yellow]")
        logger.console.print(f"  Parsed: {s['parsed_artist']} - {s['parsed_title']}")
        logger.console.print(f"  Reason: {s['reason']}")
        logger.console.print()

    if len(skipped) > 50:
        logger.console.print(f"... and {len(skipped) - 50} more")


def cmd_curated_stats(args):
    """Show curated database statistics."""
    total = get_curated_track_count(CURATED_DB_PATH)
    playlists = list_playlists(CURATED_DB_PATH)

    logger.console.print(f"\n[bold]Curated Database Stats[/bold]")
    logger.console.print(f"  Total tracks: {total}")
    logger.console.print(f"  Playlists: {len(playlists)}")

    if playlists:
        logger.console.print(f"\n  By genre:")
        genres = {}
        for p in playlists:
            genre = p['genre']
            genres[genre] = genres.get(genre, 0) + p['track_count']
        for genre, count in sorted(genres.items()):
            logger.console.print(f"    {genre}: {count}")


async def cmd_clear_all(args):
    """Clear all processed data for a fresh start."""
    logger.console.print("\n[bold yellow]Clear All Data[/bold yellow]")

    # Show what will be cleared
    qdrant_count = await get_collection_count()
    status_count = get_processed_count()
    snippets_exist = SNIPPETS_DIR.exists() and any(SNIPPETS_DIR.iterdir()) if SNIPPETS_DIR.exists() else False

    logger.console.print("\nThis will clear:")
    logger.console.print(f"  - Qdrant vectors: {qdrant_count}")
    logger.console.print(f"  - Pipeline status records: {status_count}")
    logger.console.print(f"  - Audio snippets: {'yes' if snippets_exist else 'none'}")

    if args.include_curated:
        curated_count = get_curated_track_count(CURATED_DB_PATH)
        logger.console.print(f"  - [red]Curated tracks: {curated_count}[/red]")
    else:
        logger.console.print(f"  - Curated tracks: [green]preserved[/green]")

    # Confirm
    logger.console.print("")
    confirm = input("Type 'yes' to confirm: ")
    if confirm.lower() != "yes":
        logger.console.print("[red]Aborted[/red]")
        return

    # Clear Qdrant
    logger.console.print("\nClearing Qdrant collection...")
    await clear_collection()
    logger.console.print("  [green]Done[/green]")

    # Clear pipeline status
    logger.console.print("Clearing pipeline status...")
    cleared = clear_processed()
    logger.console.print(f"  [green]Cleared {cleared} records[/green]")

    # Clear audio snippets
    if SNIPPETS_DIR.exists():
        logger.console.print("Clearing audio snippets...")
        shutil.rmtree(SNIPPETS_DIR)
        SNIPPETS_DIR.mkdir(parents=True, exist_ok=True)
        logger.console.print("  [green]Done[/green]")

    # Clear curated if requested
    if args.include_curated and CURATED_DB_PATH.exists():
        logger.console.print("Clearing curated database...")
        CURATED_DB_PATH.unlink()
        logger.console.print("  [green]Done[/green]")

    logger.console.print("\n[bold green]All data cleared![/bold green]")


async def main():
    parser = argparse.ArgumentParser(
        description="Orin song processing pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Import playlist command
    import_parser = subparsers.add_parser(
        "import-playlist",
        help="Import a YouTube playlist",
    )
    import_parser.add_argument(
        "--url",
        required=True,
        help="YouTube playlist URL",
    )
    import_parser.add_argument(
        "--genre",
        required=True,
        help="Genre tag (e.g., afro, reggaeton, dancehall)",
    )
    import_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write to database",
    )

    # List playlists command
    subparsers.add_parser(
        "list-playlists",
        help="List imported playlists",
    )

    # List skipped command
    skipped_parser = subparsers.add_parser(
        "list-skipped",
        help="List skipped tracks for review",
    )
    skipped_parser.add_argument(
        "--playlist-id",
        type=int,
        help="Filter by playlist ID",
    )

    # Curated stats command
    subparsers.add_parser(
        "curated-stats",
        help="Show curated database statistics",
    )

    # Clear all command
    clear_parser = subparsers.add_parser(
        "clear-all",
        help="Clear all processed data for fresh start",
    )
    clear_parser.add_argument(
        "--include-curated",
        action="store_true",
        help="Also clear curated tracks database (default: preserved)",
    )

    # Default run command (backwards compatible)
    # These args are for the default pipeline run
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--test",
        type=int,
        metavar="N",
        help="Process N songs for testing",
    )
    group.add_argument(
        "--track-id",
        type=int,
        metavar="ID",
        help="Process a specific track by LRCLib ID",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Process all songs (use with caution)",
    )

    parser.add_argument(
        "--source",
        choices=["lrclib", "curated"],
        default="lrclib",
        help="Data source: lrclib (default) or curated",
    )

    parser.add_argument(
        "--genre",
        help="Filter by genre (for curated source)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip audio download and indexing",
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress detailed output",
    )

    parser.add_argument(
        "--reprocess",
        action="store_true",
        help="Include already-processed tracks (reprocess them)",
    )

    args = parser.parse_args()

    # Handle subcommands
    if args.command == "import-playlist":
        cmd_import_playlist(args)
    elif args.command == "list-playlists":
        cmd_list_playlists(args)
    elif args.command == "list-skipped":
        cmd_list_skipped(args)
    elif args.command == "curated-stats":
        cmd_curated_stats(args)
    elif args.command == "clear-all":
        await cmd_clear_all(args)
    elif args.test or args.track_id or args.all:
        # Run main pipeline
        await cmd_run(args)
    else:
        parser.print_help()


def run():
    """Synchronous entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
