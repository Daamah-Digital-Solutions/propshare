/**
 * Certificate helpers shared by the Certificates tab and the Verification tab.
 *
 * The reference MUST match the one printed on the PDF by the backend
 * (backend/app/services/certificate_service.py: "CMX-" + property_id[:4] + user_id[:4],
 * upper-cased). It is stable and derived — never random — so an investor quoting it to
 * Capimax Trust or to support always quotes the same value the PDF shows.
 */
export const certificateRef = (propertyId: string, userId: string | null | undefined): string =>
  ("CMX-" + propertyId.slice(0, 4) + (userId ?? "0000").slice(0, 4)).toUpperCase();

/** Save a downloaded Blob under a filename (browser download). */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
