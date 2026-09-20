/**
 * assistantApi — the SSE reader turns the backend's event stream into typed events (chunk
 * boundaries anywhere), raises the error envelope on a non-2xx, and identifies a visitor
 * with a stable X-Visitor-Key while a signed-in user sends the bearer token instead.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { parseSseBlock, sendMessage, visitorKey } from "./assistantApi";
import { setAccessToken } from "./api";

function streamOf(chunks: string[]) {
  const enc = new TextEncoder();
  let i = 0;
  return {
    getReader: () => ({
      read: async () =>
        i < chunks.length ? { value: enc.encode(chunks[i++]), done: false } : { value: undefined, done: true },
    }),
  };
}

describe("assistantApi", () => {
  beforeEach(() => {
    localStorage.clear();
    setAccessToken(null);
  });
  afterEach(() => vi.restoreAllMocks());

  it("parses one SSE block and ignores garbage", () => {
    expect(parseSseBlock('event: delta\ndata: {"text":"hi"}')).toEqual({ event: "delta", data: { text: "hi" } });
    expect(parseSseBlock("data: {}")).toBeNull();
    expect(parseSseBlock("event: x\ndata: not-json")).toBeNull();
  });

  it("yields events across arbitrary chunk boundaries and sends the visitor key", async () => {
    const body =
      'event: started\ndata: {"conversation_id":"c","user_message_id":"u"}\n\n' +
      'event: delta\ndata: {"text":"Hel"}\n\nevent: delta\ndata: {"text":"lo"}\n\n' +
      'event: card\ndata: {"kind":"link","path":"/wallet","label":"Open your wallet"}\n\n' +
      'event: done\ndata: {"message_id":"m","confidence":"normal","flags":[],"usage":{},"latency_ms":5,"first_token_ms":1,"safe_mode":null}\n\n';
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      body: streamOf([body.slice(0, 37), body.slice(37, 120), body.slice(120)]),
    });
    vi.stubGlobal("fetch", fetchMock);
    const events = [];
    for await (const ev of sendMessage("c", "hi", "en")) events.push(ev);
    expect(events.map((e) => e.event)).toEqual(["started", "delta", "delta", "card", "done"]);
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toContain("/api/v1/assistant/conversations/c/messages");
    expect(opts.headers["X-Visitor-Key"]).toBe(visitorKey());
    expect(opts.headers["Authorization"]).toBeUndefined();
    expect(JSON.parse(opts.body)).toEqual({ text: "hi", lang: "en" });
  });

  it("raises the backend envelope on a gate error and uses the bearer when signed in", async () => {
    setAccessToken("tok");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 428,
      json: async () => ({ error: { code: "CONSENT_REQUIRED", message: "Please accept", details: {} } }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const it = sendMessage("c", "hi", "en");
    await expect(it.next()).rejects.toMatchObject({ code: "CONSENT_REQUIRED", status: 428 });
    expect(fetchMock.mock.calls[0][1].headers["Authorization"]).toBe("Bearer tok");
    expect(fetchMock.mock.calls[0][1].headers["X-Visitor-Key"]).toBeUndefined();
  });

  it("keeps one visitor key per browser", () => {
    const a = visitorKey();
    expect(a).toMatch(/^[A-Za-z0-9_-]{16,128}$/);
    expect(visitorKey()).toBe(a);
  });
});
