/**
 * A copy of an identity document, or a document sent with a claim: a photo or a PDF, up to
 * 10 MB. The server checks the same things again, by the file's first bytes
 * (backend/app/services/estate_service.py: checked_upload); this is the answer a person gets
 * before anything is uploaded.
 */
export const PHOTO_OR_PDF_ACCEPT =
  ".jpg,.jpeg,.png,.webp,.pdf,image/jpeg,image/png,image/webp,application/pdf";
export const PHOTO_OR_PDF_MAX_BYTES = 10 * 1024 * 1024;
/** The files of one claim together: what the API takes in one request (its
 *  storage_max_upload_mb), which is under what the web server lets through. */
export const CLAIM_MAX_TOTAL_BYTES = 25 * 1024 * 1024;

const NAME = /\.(jpe?g|png|webp|pdf)$/i;

/** Why a chosen file cannot be uploaded, or null when it can. */
export function photoOrPdfProblem(file: File): string | null {
  if (!NAME.test(file.name)) return `${file.name}: choose a photo (JPG, PNG, WebP) or a PDF.`;
  if (file.size > PHOTO_OR_PDF_MAX_BYTES) return `${file.name} is larger than 10 MB.`;
  if (file.size === 0) return `${file.name} is empty.`;
  return null;
}
