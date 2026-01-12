"""
Logging and progress display for the pipeline.

Uses rich for styled terminal output.
"""

from contextlib import contextmanager
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table


console = Console()


# Progress bar for overall track processing
def create_progress() -> Progress:
    """Create a progress bar for track processing."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )


def print_header(title: str) -> None:
    """Print a styled header."""
    console.print()
    console.print(Panel(title, style="bold magenta"))
    console.print()


def print_step(step: str, detail: str = "") -> None:
    """Print a pipeline step."""
    if detail:
        console.print(f"  [cyan]→[/cyan] {step}: [dim]{detail}[/dim]")
    else:
        console.print(f"  [cyan]→[/cyan] {step}")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"  [green]✓[/green] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"  [yellow]![/yellow] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"  [red]✗[/red] {message}")


def print_skip(message: str) -> None:
    """Print a skip message."""
    console.print(f"  [dim]↷ {message}[/dim]")


def print_track_header(index: int, total: int, artist: str, title: str) -> None:
    """Print header for a track being processed."""
    console.print()
    console.print(
        f"[bold][{index}/{total}][/bold] "
        f"[white]{artist}[/white] - [cyan]{title}[/cyan]"
    )


def print_segment_info(
    segment_num: int,
    total_segments: int,
    emotion: str,
    energy: str,
    lines: str,
) -> None:
    """Print info about a segment being processed."""
    console.print(
        f"    [dim]Segment {segment_num}/{total_segments}:[/dim] "
        f"{emotion} ({energy}) - lines {lines}"
    )


def print_device_info(device: str, device_name: Optional[str] = None) -> None:
    """Print embedding device info."""
    if device_name:
        console.print(f"  [dim]Embeddings:[/dim] {device} ({device_name})")
    else:
        console.print(f"  [dim]Embeddings:[/dim] {device}")


def print_config_summary(
    dry_run: bool,
    r2_configured: bool,
    qdrant_host: str,
    llm_providers: list[str],
) -> None:
    """Print configuration summary at startup."""
    table = Table(title="Configuration", show_header=False, box=None)
    table.add_column("Setting", style="dim")
    table.add_column("Value")

    table.add_row("Mode", "[yellow]Dry Run[/yellow]" if dry_run else "[green]Full Run[/green]")
    table.add_row("R2 Storage", "[green]Configured[/green]" if r2_configured else "[dim]Not configured (local)[/dim]")
    table.add_row("Qdrant", qdrant_host)
    table.add_row("LLM Providers", ", ".join(llm_providers))

    console.print(table)
    console.print()


def print_final_summary(
    tracks_processed: int,
    tracks_skipped: int,
    segments_indexed: int,
    errors: list[str],
) -> None:
    """Print final summary after pipeline completes."""
    console.print()

    table = Table(title="Results", show_header=False)
    table.add_column("Metric", style="dim")
    table.add_column("Value", justify="right")

    table.add_row("Tracks Processed", f"[green]{tracks_processed}[/green]")
    table.add_row("Tracks Skipped", f"[yellow]{tracks_skipped}[/yellow]")
    table.add_row("Segments Indexed", f"[blue]{segments_indexed}[/blue]")
    table.add_row("Errors", f"[red]{len(errors)}[/red]" if errors else "[dim]0[/dim]")

    console.print(table)

    if errors:
        console.print()
        console.print("[bold red]Errors:[/bold red]")
        for error in errors[:10]:
            console.print(f"  [dim]{error}[/dim]")
        if len(errors) > 10:
            console.print(f"  [dim]... and {len(errors) - 10} more[/dim]")


@contextmanager
def status(message: str):
    """Context manager for showing a spinner during an operation."""
    with console.status(message, spinner="dots"):
        yield
