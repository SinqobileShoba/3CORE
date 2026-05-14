import os
import re
import uuid
from typing import Optional

from fastapi import HTTPException, UploadFile

from .config import settings

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def sanitize_filename(filename: Optional[str]) -> str:
    """Strip directory parts and replace unsafe chars. Always returns a safe basename."""
    if not filename:
        return f"unnamed-{uuid.uuid4().hex[:8]}"
    base = os.path.basename(filename).strip()
    base = base.lstrip(".")
    base = _UNSAFE_FILENAME_CHARS.sub("_", base)
    if not base:
        base = f"unnamed-{uuid.uuid4().hex[:8]}"
    return base[:200]


def assert_allowed_extension(filename: str) -> None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '.{ext}' is not allowed",
        )


async def read_validated_upload(file: UploadFile) -> tuple[bytes, str]:
    """Read an UploadFile, enforce size + extension. Returns (content, safe_filename)."""
    safe_name = sanitize_filename(file.filename)
    assert_allowed_extension(safe_name)

    content = await file.read()
    if len(content) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed size ({settings.MAX_UPLOAD_BYTES} bytes)",
        )
    return content, safe_name
