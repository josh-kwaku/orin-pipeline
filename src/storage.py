"""
Cloudflare R2 storage module.

Handles uploading audio snippets to R2 (S3-compatible).
All operations are async for efficient network IO.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import aioboto3


@dataclass
class UploadResult:
    """Result of upload operation."""

    success: bool
    url: Optional[str]  # Public URL to access the file
    error: Optional[str] = None


def _get_r2_config() -> dict[str, Any]:
    """
    Get R2 configuration from environment variables.

    Returns:
        Dictionary with endpoint_url, aws_access_key_id, aws_secret_access_key, bucket_name

    Raises:
        ValueError: If required environment variables are not set
    """
    required = {
        "R2_ENDPOINT": os.environ.get("R2_ENDPOINT"),
        "R2_ACCESS_KEY_ID": os.environ.get("R2_ACCESS_KEY_ID"),
        "R2_SECRET_ACCESS_KEY": os.environ.get("R2_SECRET_ACCESS_KEY"),
        "R2_BUCKET_NAME": os.environ.get("R2_BUCKET_NAME"),
    }

    missing = [k for k, v in required.items() if not v]
    if missing:
        raise ValueError(
            f"Missing R2 environment variables: {', '.join(missing)}. "
            "Please add them to your .env file."
        )

    return {
        "endpoint_url": required["R2_ENDPOINT"],
        "aws_access_key_id": required["R2_ACCESS_KEY_ID"],
        "aws_secret_access_key": required["R2_SECRET_ACCESS_KEY"],
        "bucket_name": required["R2_BUCKET_NAME"],
    }


def _get_public_url(bucket_name: str, key: str) -> str:
    """
    Build public URL for an R2 object.

    Note: Requires R2 bucket to have public access enabled,
    or a custom domain configured.

    Args:
        bucket_name: R2 bucket name
        key: Object key (path in bucket)

    Returns:
        Public URL string
    """
    # R2 public URL format (when public access is enabled)
    # You may need to adjust this based on your R2 configuration
    # Option 1: R2.dev subdomain (if enabled)
    # Option 2: Custom domain
    public_domain = os.environ.get("R2_PUBLIC_DOMAIN")

    if public_domain:
        return f"https://{public_domain}/{key}"

    # Fallback: Use bucket subdomain (requires public access)
    return f"https://{bucket_name}.r2.dev/{key}"


async def upload_snippet(
    file_path: Path,
    snippet_id: str,
    content_type: str = "audio/opus",
) -> UploadResult:
    """
    Upload an audio snippet to R2.

    Args:
        file_path: Local path to the audio file
        snippet_id: Unique snippet ID (used as object key)
        content_type: MIME type of the file

    Returns:
        UploadResult with public URL on success
    """
    try:
        config = _get_r2_config()
    except ValueError as e:
        return UploadResult(success=False, url=None, error=str(e))

    # Object key in R2 (organized by extension)
    extension = file_path.suffix or ".opus"
    key = f"snippets/{snippet_id}{extension}"

    try:
        session = aioboto3.Session()

        # aioboto3 returns async context manager (Pylance lacks type stubs)
        async with session.client(  # type: ignore[reportGeneralTypeIssues]
            "s3",
            endpoint_url=config["endpoint_url"],
            aws_access_key_id=config["aws_access_key_id"],
            aws_secret_access_key=config["aws_secret_access_key"],
        ) as s3:
            # Upload file
            with open(file_path, "rb") as f:
                await s3.put_object(
                    Bucket=config["bucket_name"],
                    Key=key,
                    Body=f.read(),
                    ContentType=content_type,
                )

        # Build public URL
        public_url = _get_public_url(config["bucket_name"], key)

        return UploadResult(
            success=True,
            url=public_url,
        )

    except FileNotFoundError:
        return UploadResult(
            success=False,
            url=None,
            error=f"File not found: {file_path}",
        )
    except Exception as e:
        return UploadResult(
            success=False,
            url=None,
            error=str(e),
        )


async def delete_snippet(snippet_id: str, extension: str = ".opus") -> bool:
    """
    Delete a snippet from R2.

    Args:
        snippet_id: Unique snippet ID
        extension: File extension

    Returns:
        True if deleted successfully
    """
    try:
        config = _get_r2_config()
    except ValueError:
        return False

    key = f"snippets/{snippet_id}{extension}"

    try:
        session = aioboto3.Session()

        async with session.client(  # type: ignore[reportGeneralTypeIssues]
            "s3",
            endpoint_url=config["endpoint_url"],
            aws_access_key_id=config["aws_access_key_id"],
            aws_secret_access_key=config["aws_secret_access_key"],
        ) as s3:
            await s3.delete_object(
                Bucket=config["bucket_name"],
                Key=key,
            )
            return True

    except Exception:
        return False


def is_r2_configured() -> bool:
    """
    Check if R2 credentials are configured.

    Returns:
        True if all required R2 environment variables are set
    """
    required = [
        "R2_ENDPOINT",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "R2_BUCKET_NAME",
    ]
    return all(os.environ.get(var) for var in required)
