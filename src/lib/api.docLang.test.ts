/**
 * A document the platform generates comes in the language the person has the site in: every
 * download goes through fetchBlob, which says so. English sends nothing, as before.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fetchBlob } from "./api";

describe("fetchBlob document language", () => {
  const fetchMock = vi.fn();
  const asked = () => String(fetchMock.mock.calls[0][0]);

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(new Response("pdf", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    localStorage.removeItem("language");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.removeItem("language");
  });

  it("asks for nothing special in English", async () => {
    await fetchBlob("/api/v1/investments/certificates.zip");
    expect(asked().endsWith("/api/v1/investments/certificates.zip")).toBe(true);
  });

  it("asks for the site's language", async () => {
    localStorage.setItem("language", "ar");
    await fetchBlob("/api/v1/investments/certificates.zip");
    expect(asked().endsWith("/api/v1/investments/certificates.zip?lang=ar")).toBe(true);
  });

  it("keeps the query a download already has", async () => {
    localStorage.setItem("language", "fr");
    await fetchBlob("/api/v1/wallet/statement?start=2026-01-01&end=2026-02-01&format=pdf");
    expect(asked().endsWith("?start=2026-01-01&end=2026-02-01&format=pdf&lang=fr")).toBe(true);
  });

  it("does not add it twice when a download is retried after a refresh", async () => {
    localStorage.setItem("language", "ar");
    fetchMock.mockReset();
    fetchMock
      .mockResolvedValueOnce(new Response("", { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ access_token: "t" }), { status: 200 }))
      .mockResolvedValue(new Response("pdf", { status: 200 }));
    await fetchBlob("/api/v1/investments/certificates.zip");
    const last = String(fetchMock.mock.calls.at(-1)?.[0]);
    expect(last.match(/lang=/g)).toHaveLength(1);
  });
});
