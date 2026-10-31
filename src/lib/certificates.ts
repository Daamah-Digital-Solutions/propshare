/**
 * Certificate helpers shared by the Certificates tab and the Verification tab. A certificate's
 * number and verification code come from the server (certificateApi.mine), as printed on it.
 */

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
