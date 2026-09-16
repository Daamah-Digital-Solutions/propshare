/**
 * Stored listing media is saved as a backend-relative URL (`/api/v1/files/...`). The SPA
 * must resolve it against the API origin, otherwise every gallery photo, cover and developer
 * logo is a broken image whenever the app and the API are not on the same origin (local dev,
 * or a future CDN/host split). Absolute and data URLs must pass through untouched.
 */
import { describe, it, expect } from "vitest";
import { assetUrl } from "@/lib/api";

const base = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

describe("assetUrl", () => {
  it("prefixes backend-relative file URLs with the API base", () => {
    expect(assetUrl("/api/v1/files/property-images/p1/a.jpg")).toBe(
      `${base}/api/v1/files/property-images/p1/a.jpg`,
    );
  });
  it("leaves absolute, data and empty URLs alone", () => {
    expect(assetUrl("https://cdn.example.com/x.jpg")).toBe("https://cdn.example.com/x.jpg");
    expect(assetUrl("data:image/png;base64,AAAA")).toBe("data:image/png;base64,AAAA");
    expect(assetUrl("")).toBe("");
  });
});
