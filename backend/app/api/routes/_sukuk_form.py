"""Form fields of a Nova Sukuk certificate upload, shared by the purchase and installment
routes (0032)."""

from __future__ import annotations

import datetime as dt
import decimal

from fastapi import UploadFile

from app.core.errors import AppError
from app.services import sukuk_service


def _text(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


async def certificate_upload(
    file: UploadFile,
    certificate_no: str | None,
    issuer: str | None,
    certificate_value: str | None,
    valid_until: str | None,
) -> sukuk_service.CertificateUpload:
    """Read the file (at most one byte past the limit) and parse the optional details: an
    empty field means "not given", a malformed one is a clear 422."""
    value = None
    if _text(certificate_value):
        try:
            value = decimal.Decimal(_text(certificate_value).replace(",", ""))
            if not value.is_finite() or abs(value) >= decimal.Decimal("1e13"):
                raise decimal.InvalidOperation
            value = value.quantize(decimal.Decimal("0.01"))
        except decimal.InvalidOperation:
            raise AppError(
                "INVALID_VALUE", "The certificate value must be a number.", status_code=422
            ) from None
    until = None
    if _text(valid_until):
        try:
            until = dt.date.fromisoformat(_text(valid_until))
        except ValueError:
            raise AppError(
                "INVALID_DATE", "The validity date must be a date (YYYY-MM-DD).", status_code=422
            ) from None
    data = await file.read(sukuk_service.MAX_CERTIFICATE_BYTES + 1)
    return sukuk_service.CertificateUpload(
        filename=file.filename or "certificate.pdf",
        data=data,
        certificate_no=_text(certificate_no),
        issuer=_text(issuer),
        certificate_value=value,
        valid_until=until,
    )
