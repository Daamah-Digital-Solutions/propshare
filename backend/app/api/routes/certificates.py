"""Public certificate verification (client, 2026-10-28, as on Capimax BRX).

- GET /certificates/verify/{code}   what a certificate states and whether it is still valid,
                                    for anyone holding the paper: its QR code opens the site's
                                    /verify/{code} page, which reads this. No account needed;
                                    rate-limited per IP (the code is 22 random characters).
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import SessionDep
from app.core.ratelimit import CERTIFICATE_VERIFY_LIMIT, limiter
from app.schemas.certificates import CertificateVerificationOut
from app.services import certificate_service

router = APIRouter(prefix="/api/v1/certificates", tags=["certificates"])


@router.get("/verify/{code}", response_model=CertificateVerificationOut)
@limiter.limit(CERTIFICATE_VERIFY_LIMIT)
async def verify_certificate(request: Request, code: str, session: SessionDep):
    return CertificateVerificationOut(**await certificate_service.verify(session, code))
