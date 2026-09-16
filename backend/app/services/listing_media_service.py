"""Property gallery images (go-live audit, Step 2).

Every image that reaches ``properties.images`` goes through here, whether it comes from the
owner API or the admin Listing Editor:

  * **validation** — the bytes must decode as a real JPEG / PNG / WebP (a ``.txt`` renamed to
    ``.png`` used to be accepted and rendered as a broken hero);
  * **normalisation** — EXIF-rotated, longest edge capped at ``MAX_EDGE`` px, re-encoded as
    progressive JPEG q82 (PNG only when the image has transparency). Metadata is dropped by
    the re-encode. A 2.3 MB phone photo becomes a few hundred KB, sharp at page width;
  * **ordering** — ``images[0]`` is the cover everywhere, so reorder / set-cover are explicit;
  * **deletion** — removes the row entry AND the storage object (no more orphans).

Each mutation writes an audit row.
"""

from __future__ import annotations

import io
import uuid

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import write_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.models import Property
from app.services.integrations import storage

MAX_EDGE = 2000
JPEG_QUALITY = 82
ALLOWED_FORMATS = ("JPEG", "PNG", "WEBP")


def process_image(data: bytes) -> tuple[bytes, str, str]:
    """Validate + normalise raw upload bytes. Returns (bytes, extension, content_type)."""
    if not data:
        raise AppError("EMPTY_FILE", "Uploaded file is empty.", status_code=422)
    if len(data) > get_settings().storage_max_upload_bytes:
        raise AppError(
            "FILE_TOO_LARGE",
            f"File exceeds the {get_settings().storage_max_upload_mb} MB limit.",
            status_code=413,
        )
    try:
        im = Image.open(io.BytesIO(data))
        fmt = im.format
        im.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise AppError(
            "INVALID_IMAGE", "Only JPEG, PNG or WebP images are accepted.", status_code=422
        ) from exc
    if fmt not in ALLOWED_FORMATS:
        raise AppError(
            "INVALID_IMAGE", "Only JPEG, PNG or WebP images are accepted.", status_code=422
        )
    im = ImageOps.exif_transpose(im) or im
    im.thumbnail((MAX_EDGE, MAX_EDGE))  # shrinks only, keeps aspect ratio
    has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    out = io.BytesIO()
    if has_alpha:
        im.convert("RGBA").save(out, format="PNG", optimize=True)
        return out.getvalue(), "png", "image/png"
    im.convert("RGB").save(
        out, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True
    )
    return out.getvalue(), "jpg", "image/jpeg"


def url_to_key(url: str) -> str | None:
    """Map a stored public URL back to its storage key (local route or S3 public base)."""
    local = "/api/v1/files/"
    if url.startswith(local):
        return url[len(local) :]
    base = get_settings().s3_public_base_url.rstrip("/")
    if base and url.startswith(base + "/"):
        return url[len(base) + 1 :]
    return None


async def _audit(session, prop: Property, action: str, actor_id, after: dict) -> None:
    await write_audit(
        session,
        action=action,
        entity_type="property",
        entity_id=str(prop.id),
        actor_id=actor_id,
        after=after,
    )


async def add_images(
    session: AsyncSession,
    *,
    prop: Property,
    files: list[tuple[str, bytes]],
    actor_id: uuid.UUID | None,
) -> list[str]:
    """Validate, normalise and append images; returns the new ordered URL list."""
    urls = list(prop.images or [])
    added: list[str] = []
    for _name, data in files:
        blob, ext, ctype = process_image(data)
        key = f"property-images/{prop.id}/{uuid.uuid4().hex}.{ext}"
        storage.save(key, blob, ctype)
        url = storage.public_url(key)
        urls.append(url)
        added.append(url)
    prop.images = urls
    await session.flush()
    await _audit(
        session, prop, "property.images.add", actor_id, {"added": added, "total": len(urls)}
    )
    return urls


async def remove_image(
    session: AsyncSession, *, prop: Property, url: str, actor_id: uuid.UUID | None
) -> list[str]:
    urls = list(prop.images or [])
    if url not in urls:
        raise AppError("NOT_FOUND", "Image not found on this property.", status_code=404)
    urls.remove(url)
    prop.images = urls
    await session.flush()
    key = url_to_key(url)
    if key:
        storage.delete(key)
    await _audit(session, prop, "property.images.remove", actor_id, {"removed": url})
    return urls


async def reorder_images(
    session: AsyncSession, *, prop: Property, order: list[str], actor_id: uuid.UUID | None
) -> list[str]:
    current = list(prop.images or [])
    if sorted(order) != sorted(current):
        raise AppError(
            "INVALID_ORDER", "Order must contain exactly the property's images.", status_code=422
        )
    prop.images = list(order)
    await session.flush()
    await _audit(session, prop, "property.images.reorder", actor_id, {"order": order})
    return list(order)


async def set_cover(
    session: AsyncSession, *, prop: Property, url: str, actor_id: uuid.UUID | None
) -> list[str]:
    urls = list(prop.images or [])
    if url not in urls:
        raise AppError("NOT_FOUND", "Image not found on this property.", status_code=404)
    urls.remove(url)
    return await reorder_images(session, prop=prop, order=[url, *urls], actor_id=actor_id)


def moved(urls: list[str], url: str, delta: int) -> list[str]:
    """Pure helper: the list with ``url`` shifted by ``delta`` positions (clamped)."""
    out = list(urls)
    if url not in out:
        return out
    i = out.index(url)
    j = max(0, min(len(out) - 1, i + delta))
    out.insert(j, out.pop(i))
    return out
