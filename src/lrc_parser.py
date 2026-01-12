"""
LRC (Lyric) format parser.

Parses synced lyrics in LRC format to extract timestamps for each line.
LRC format: [MM:SS.xx]Lyrics text here

Example:
    [00:17.87]Wettin you want
    [00:19.52]I go give you
"""

import re
from dataclasses import dataclass
from typing import Optional


# Regex to match LRC timestamp format: [MM:SS.xx] or [MM:SS]
LRC_TIMESTAMP_PATTERN = re.compile(r"\[(\d{2}):(\d{2})(?:\.(\d{2,3}))?\]")


@dataclass
class LyricLine:
    """A single line of lyrics with its timestamp."""

    line_number: int  # 1-indexed
    timestamp: float  # Seconds from start
    text: str

    @property
    def timestamp_str(self) -> str:
        """Format timestamp as MM:SS.xx"""
        minutes = int(self.timestamp // 60)
        seconds = self.timestamp % 60
        return f"{minutes:02d}:{seconds:05.2f}"


@dataclass
class ParsedLRC:
    """Parsed LRC data with all lines and helper methods."""

    lines: list[LyricLine]
    raw_text: str

    def get_timestamp(self, line_number: int) -> Optional[float]:
        """
        Get timestamp for a specific line number (1-indexed).

        Args:
            line_number: Line number (1-indexed)

        Returns:
            Timestamp in seconds, or None if line not found
        """
        for line in self.lines:
            if line.line_number == line_number:
                return line.timestamp
        return None

    def get_line(self, line_number: int) -> Optional[LyricLine]:
        """Get a specific line by number (1-indexed)."""
        for line in self.lines:
            if line.line_number == line_number:
                return line
        return None

    def get_segment_timestamps(
        self,
        start_line: int,
        end_line: int,
    ) -> tuple[Optional[float], Optional[float]]:
        """
        Get start and end timestamps for a segment.

        Args:
            start_line: Starting line number (1-indexed, inclusive)
            end_line: Ending line number (1-indexed, inclusive)

        Returns:
            Tuple of (start_timestamp, end_timestamp) in seconds.
            End timestamp is the start of the NEXT line after end_line,
            or end of the last line's estimated duration if it's the last line.
        """
        start_ts = self.get_timestamp(start_line)

        # For end timestamp, we want the START of the line AFTER end_line
        # This ensures we capture the full audio of the last line
        next_line = self.get_line(end_line + 1)

        if next_line:
            end_ts = next_line.timestamp
        else:
            # end_line is the last line - estimate duration
            # Add a buffer (e.g., 3 seconds) for the last line
            last_line_ts = self.get_timestamp(end_line)
            if last_line_ts is not None:
                end_ts = last_line_ts + 3.0  # 3 second buffer for last line
            else:
                end_ts = None

        return start_ts, end_ts

    def get_lyrics_text(self, start_line: int, end_line: int) -> str:
        """
        Get combined lyrics text for a range of lines.

        Args:
            start_line: Starting line number (1-indexed, inclusive)
            end_line: Ending line number (1-indexed, inclusive)

        Returns:
            Combined lyrics text with newlines
        """
        lyrics = []
        for line in self.lines:
            if start_line <= line.line_number <= end_line:
                lyrics.append(line.text)
        return "\n".join(lyrics)

    @property
    def total_lines(self) -> int:
        """Total number of lyric lines."""
        return len(self.lines)

    @property
    def duration(self) -> float:
        """Estimated duration based on last timestamp."""
        if not self.lines:
            return 0.0
        return self.lines[-1].timestamp + 3.0  # Add buffer for last line

    @property
    def plain_lyrics(self) -> str:
        """Get all lyrics as plain text without timestamps."""
        return "\n".join(line.text for line in self.lines)


def parse_timestamp(match: re.Match) -> float:
    """
    Convert regex match to timestamp in seconds.

    Args:
        match: Regex match with groups (minutes, seconds, centiseconds)

    Returns:
        Timestamp in seconds as float
    """
    minutes = int(match.group(1))
    seconds = int(match.group(2))
    centiseconds = match.group(3)

    if centiseconds:
        # Handle both .xx and .xxx formats
        if len(centiseconds) == 2:
            cs = int(centiseconds) / 100
        else:
            cs = int(centiseconds) / 1000
    else:
        cs = 0

    return minutes * 60 + seconds + cs


def parse_lrc(synced_lyrics: str) -> ParsedLRC:
    """
    Parse LRC format lyrics into structured data.

    Args:
        synced_lyrics: Raw LRC format string from database

    Returns:
        ParsedLRC object with all lines and timestamps

    Example:
        >>> lrc = parse_lrc("[00:17.87]Hello\\n[00:19.52]World")
        >>> lrc.lines[0].timestamp
        17.87
        >>> lrc.lines[0].text
        'Hello'
    """
    lines = []
    line_number = 0

    for raw_line in synced_lyrics.split("\n"):
        raw_line = raw_line.strip()

        if not raw_line:
            continue

        # Find all timestamps in the line (some lines have multiple)
        matches = list(LRC_TIMESTAMP_PATTERN.finditer(raw_line))

        if not matches:
            # Line without timestamp - skip or handle as metadata
            continue

        # Get the text after the last timestamp
        last_match = matches[-1]
        text = raw_line[last_match.end():].strip()

        # Skip empty lines or metadata lines
        if not text or text.startswith("["):
            continue

        # Use the first timestamp for this line
        timestamp = parse_timestamp(matches[0])
        line_number += 1

        lines.append(LyricLine(
            line_number=line_number,
            timestamp=timestamp,
            text=text,
        ))

    # Sort by timestamp (should already be sorted, but just in case)
    lines.sort(key=lambda x: x.timestamp)

    # Re-number after sorting
    for i, line in enumerate(lines):
        line.line_number = i + 1

    return ParsedLRC(lines=lines, raw_text=synced_lyrics)


def validate_segment_lines(
    parsed_lrc: ParsedLRC,
    start_line: int,
    end_line: int,
) -> tuple[bool, str]:
    """
    Validate that segment line numbers are valid.

    Args:
        parsed_lrc: Parsed LRC data
        start_line: Starting line number
        end_line: Ending line number

    Returns:
        Tuple of (is_valid, error_message)
    """
    if start_line < 1:
        return False, f"start_line must be >= 1, got {start_line}"

    if end_line < start_line:
        return False, f"end_line ({end_line}) must be >= start_line ({start_line})"

    if start_line > parsed_lrc.total_lines:
        return False, f"start_line ({start_line}) exceeds total lines ({parsed_lrc.total_lines})"

    if end_line > parsed_lrc.total_lines:
        return False, f"end_line ({end_line}) exceeds total lines ({parsed_lrc.total_lines})"

    return True, ""
