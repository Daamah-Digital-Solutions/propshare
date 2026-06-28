"""Object storage seam (documents / certificates / images).

Provider chosen by ``STORAGE_PROVIDER`` — mirrors the email provider pattern:
  * "local" (default, dev) — writes REAL files under ``storage_dir`` and serves them
    through the app (``/api/v1/files/...`` for public assets, ``/documents/{id}/download``
    for documents). Not a fake — actual bytes on disk.
  * "s3" (prod) — boto3 is imported LAZILY (absent locally is fine); objects are put to
    the bucket and read back / presigned for GET.

Keys are app-controlled (never user-supplied) and validated against traversal.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import get_settings

# Keys are built by the app (prefix/uuid/filename); validate defensively anyway.
_SAFE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/\-]*$")
# Prefixes whose objects are public assets (served inline without auth).
PUBLIC_PREFIXES = ("property-images/", "avatars/")


class StorageKeyError(ValueError):
    """Raised for a malformed/unsafe storage key."""


class StorageNotFound(Exception):
    """Raised when an object does not exist."""


def _check_key(key: str) -> str:
    if ".." in key or not _SAFE_KEY.match(key):
        raise StorageKeyError(f"unsafe storage key: {key!r}")
    return key


def _provider() -> str:
    return get_settings().storage_provider.lower()


def _local_path(key: str) -> Path:
    return Path(get_settings().storage_dir) / key


def save(key: str, data: bytes, content_type: str | None = None) -> None:
    _check_key(key)
    if _provider() == "s3":
        _s3_client().put_object(
            Bucket=get_settings().s3_bucket,
            Key=key,
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )
        return
    p = _local_path(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def load(key: str) -> bytes:
    _check_key(key)
    if _provider() == "s3":
        try:
            obj = _s3_client().get_object(Bucket=get_settings().s3_bucket, Key=key)
        except Exception as exc:  # noqa: BLE001 — normalize any boto error to not-found
            raise StorageNotFound(key) from exc
        return obj["Body"].read()
    p = _local_path(key)
    if not p.is_file():
        raise StorageNotFound(key)
    return p.read_bytes()


def delete(key: str) -> None:
    _check_key(key)
    if _provider() == "s3":
        try:
            _s3_client().delete_object(Bucket=get_settings().s3_bucket, Key=key)
        except Exception:  # noqa: BLE001 — best-effort
            pass
        return
    p = _local_path(key)
    if p.is_file():
        p.unlink()


def public_url(key: str) -> str:
    """Stable URL for a PUBLIC asset (images/avatars). local => app file route;
    s3 => CDN base or presigned GET."""
    _check_key(key)
    if _provider() == "s3":
        base = get_settings().s3_public_base_url.rstrip("/")
        if base:
            return f"{base}/{key}"
        return _s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": get_settings().s3_bucket, "Key": key},
            ExpiresIn=3600,
        )
    return f"/api/v1/files/{key}"


def _s3_client():  # pragma: no cover - prod-only path, boto3 not installed locally
    import boto3  # lazy: absent locally is fine

    s = get_settings()
    return boto3.client(
        "s3",
        region_name=s.s3_region or None,
        endpoint_url=s.s3_endpoint_url or None,
    )
