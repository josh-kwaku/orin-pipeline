"""
LRCLib API client for fetching synced lyrics.

API Documentation: https://lrclib.net/docs
"""

import httpx
from dataclasses import dataclass
from typing import Optional
import time

LRCLIB_API_BASE = "https://lrclib.net/api"

# Rate limiting - be respectful to the API
REQUEST_DELAY = 0.5  # seconds between requests


@dataclass
class LRCLibResult:
    """Result from LRCLib API."""

    id: int
    track_name: str
    artist_name: str
    album_name: Optional[str]
    duration: float
    synced_lyrics: str


def search_lyrics(
    artist: str,
    title: str,
    duration: Optional[float] = None,
) -> Optional[LRCLibResult]:
    """
    Search LRCLib API for synced lyrics.

    Tries multiple strategies:
    1. /api/get with exact match (artist, title variations, duration)
    2. /api/get without duration (title variations)
    3. /api/search with fuzzy query

    Args:
        artist: Artist name
        title: Song title
        duration: Song duration in seconds (optional, improves matching)

    Returns:
        LRCLibResult if synced lyrics found, None otherwise
    """
    # Generate title variations to handle different featuring artist formats
    # e.g., "Bad Vibes ft. X" -> ["Bad Vibes ft. X", "Bad Vibes (feat. X)", "Bad Vibes feat. X", "Bad Vibes"]
    title_variations = _generate_title_variations(title)

    # Strategy 1: Exact match with duration
    if duration:
        for variant in title_variations:
            result = _get_exact(artist, variant, int(duration))
            if result:
                return result

    # Strategy 2: Exact match without duration
    for variant in title_variations:
        result = _get_exact(artist, variant)
        if result:
            return result

    # Strategy 3: Fuzzy search
    result = _search_fuzzy(artist, title, duration)
    if result:
        return result

    return None


def _generate_title_variations(title: str) -> list[str]:
    """
    Generate title variations to handle different featuring artist formats.

    Examples:
        "Bad Vibes ft. Artist" -> [
            "Bad Vibes ft. Artist",
            "Bad Vibes (feat. Artist)",
            "Bad Vibes feat. Artist",
            "Bad Vibes (ft. Artist)",
            "Bad Vibes",
        ]

    Args:
        title: Original title

    Returns:
        List of title variations to try
    """
    import re

    variations = [title]  # Always try the original first

    # Check if title has featuring artist in various formats
    # Patterns: "ft.", "feat.", "featuring", with/without parentheses
    patterns = [
        (r'\s+ft\.\s+(.+)$', 'ft.'),
        (r'\s+feat\.\s+(.+)$', 'feat.'),
        (r'\s+featuring\s+(.+)$', 'featuring'),
        (r'\s*\(ft\.\s+(.+)\)$', 'ft.'),
        (r'\s*\(feat\.\s+(.+)\)$', 'feat.'),
        (r'\s*\(featuring\s+(.+)\)$', 'featuring'),
    ]

    for pattern, _ in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            featured_artist = match.group(1)
            base_title = title[:match.start()].strip()

            # Generate variations
            variations.extend([
                f"{base_title} (feat. {featured_artist})",
                f"{base_title} feat. {featured_artist}",
                f"{base_title} ft. {featured_artist}",
                f"{base_title} (ft. {featured_artist})",
                base_title,  # Try without featuring artist
            ])
            break

    # Remove duplicates while preserving order
    seen = set()
    unique_variations = []
    for v in variations:
        if v not in seen:
            seen.add(v)
            unique_variations.append(v)

    return unique_variations


def _get_exact(
    artist: str,
    title: str,
    duration: Optional[int] = None,
) -> Optional[LRCLibResult]:
    """
    Try exact match via /api/get endpoint.

    Args:
        artist: Artist name
        title: Track name
        duration: Duration in seconds (optional)

    Returns:
        LRCLibResult if found with synced lyrics, None otherwise
    """
    params = {
        "artist_name": artist,
        "track_name": title,
    }
    if duration:
        params["duration"] = duration

    try:
        time.sleep(REQUEST_DELAY)
        response = httpx.get(
            f"{LRCLIB_API_BASE}/get",
            params=params,
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()
            synced = data.get("syncedLyrics")
            if synced:
                return LRCLibResult(
                    id=data["id"],
                    track_name=data["trackName"],
                    artist_name=data["artistName"],
                    album_name=data.get("albumName"),
                    duration=data["duration"],
                    synced_lyrics=synced,
                )
    except httpx.RequestError:
        pass

    return None


def _search_fuzzy(
    artist: str,
    title: str,
    expected_duration: Optional[float] = None,
) -> Optional[LRCLibResult]:
    """
    Fuzzy search via /api/search endpoint.

    Args:
        artist: Artist name
        title: Track name
        expected_duration: Expected duration for filtering results

    Returns:
        Best matching LRCLibResult with synced lyrics, None if not found
    """
    query = f"{artist} {title}"

    try:
        time.sleep(REQUEST_DELAY)
        response = httpx.get(
            f"{LRCLIB_API_BASE}/search",
            params={"q": query},
            timeout=10,
        )

        if response.status_code != 200:
            return None

        results = response.json()
        if not results:
            return None

        # Filter to only results with synced lyrics
        synced_results = [r for r in results if r.get("syncedLyrics")]
        if not synced_results:
            return None

        # If we have expected duration, prefer closest match
        if expected_duration:
            synced_results.sort(
                key=lambda r: abs(r.get("duration", 0) - expected_duration)
            )

        # Return first (best) match
        best = synced_results[0]
        return LRCLibResult(
            id=best["id"],
            track_name=best["trackName"],
            artist_name=best["artistName"],
            album_name=best.get("albumName"),
            duration=best["duration"],
            synced_lyrics=best["syncedLyrics"],
        )

    except httpx.RequestError:
        return None


def get_lyrics_by_id(lrclib_id: int) -> Optional[LRCLibResult]:
    """
    Get lyrics by LRCLib ID.

    Args:
        lrclib_id: LRCLib track ID

    Returns:
        LRCLibResult if found, None otherwise
    """
    try:
        time.sleep(REQUEST_DELAY)
        response = httpx.get(
            f"{LRCLIB_API_BASE}/get/{lrclib_id}",
            timeout=10,
        )

        if response.status_code == 200:
            data = response.json()
            synced = data.get("syncedLyrics")
            if synced:
                return LRCLibResult(
                    id=data["id"],
                    track_name=data["trackName"],
                    artist_name=data["artistName"],
                    album_name=data.get("albumName"),
                    duration=data["duration"],
                    synced_lyrics=synced,
                )
    except httpx.RequestError:
        pass

    return None
