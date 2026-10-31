/**
 * The page an investment certificate's QR code opens (client, 2026-10-28, as on Capimax BRX):
 * anyone, without an account, sees whether it is authentic and current and what it states.
 */
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { verify } = vi.hoisted(() => ({ verify: vi.fn() }));

vi.mock("@/lib/api", () => ({
  certificateApi: { verify: (code: string) => verify(code) },
  ApiError: class ApiError extends Error {
    status: number;
    code: string;
    constructor(code: string, message: string, status: number) {
      super(message);
      this.status = status;
      this.code = code;
    }
  },
}));

import VerifyCertificate from "./VerifyCertificate";
import { ApiError } from "@/lib/api";

const RESULT = {
  number: "PSC-2026-K7M2Q9XA",
  verification_code: "Xq3vN8bKp2LmR5tY7wZa1c",
  status: "valid",
  issuer: "Capimax PropShare",
  holder_name: "Layla Hassan",
  holder_ref: "****A1B2C3",
  property_title: "Marina Loft",
  location: "Dubai Marina",
  spv_name: "Marina Loft Holdings Ltd",
  jurisdiction: "UAE",
  units: 1250,
  ownership: "2.5%",
  unit_price: "100.00",
  value: "125000.00",
  signature: "a".repeat(64),
  issued_at: "2026-10-20T09:00:00Z",
  superseded_at: null,
  revoked_at: null,
  revocation_reason: null,
  verified_at: "2026-10-28T12:00:00Z",
};

function mount(code = "Xq3vN8bKp2LmR5tY7wZa1c") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/verify/${code}`]}>
        <Routes>
          <Route path="/verify/:code" element={<VerifyCertificate />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("VerifyCertificate", () => {
  beforeEach(() => {
    verify.mockReset();
  });

  it("checks the code from the QR link and shows a valid certificate and what it states", async () => {
    verify.mockResolvedValue(RESULT);
    mount();
    expect(screen.getByTestId("verify-loading")).toHaveTextContent("Verifying certificate…");
    const page = await screen.findByTestId("verify-result");
    expect(verify).toHaveBeenCalledWith("Xq3vN8bKp2LmR5tY7wZa1c");
    expect(screen.getByTestId("verify-status")).toHaveTextContent("Valid — Verified");
    expect(page).toHaveTextContent("authentic and current");
    expect(page).toHaveTextContent("Certificate numberPSC-2026-K7M2Q9XA");
    expect(page).toHaveTextContent("Issue dateOctober 20, 2026");
    expect(page).toHaveTextContent("Registered holderLayla Hassan");
    expect(page).toHaveTextContent("Investor ID****A1B2C3");
    expect(page).toHaveTextContent("Issuing SPVMarina Loft Holdings Ltd");
    expect(page).toHaveTextContent("JurisdictionUAE");
    expect(page).toHaveTextContent("Units1,250");
    expect(page).toHaveTextContent("Share of the property2.5%");
    expect(page).toHaveTextContent("Recorded value on the issue date$125,000.00");
  });

  it("a superseded certificate says a newer one replaces it", async () => {
    verify.mockResolvedValue({ ...RESULT, status: "superseded", superseded_at: "2026-10-25T08:00:00Z" });
    mount();
    expect(await screen.findByTestId("verify-status")).toHaveTextContent("Superseded");
    expect(screen.getByTestId("verify-result")).toHaveTextContent(
      "no longer states the holder's current units (since October 25, 2026). A newer certificate replaces it.",
    );
    expect(screen.queryByText("Valid — Verified")).toBeNull();
  });

  it("a revoked certificate says when and why", async () => {
    verify.mockResolvedValue({
      ...RESULT,
      status: "revoked",
      revoked_at: "2026-10-26T08:00:00Z",
      revocation_reason: "Issued in error",
    });
    mount();
    expect(await screen.findByTestId("verify-status")).toHaveTextContent("Revoked");
    expect(screen.getByTestId("verify-result")).toHaveTextContent(
      "revoked by Capimax PropShare on October 26, 2026. Reason: Issued in error.",
    );
  });

  it("an unknown code is not found, with the way to enter another", async () => {
    verify.mockRejectedValue(new ApiError("CERTIFICATE_NOT_FOUND", "x", 404));
    mount("not-a-real-code");
    const page = await screen.findByTestId("verify-not-found");
    expect(page).toHaveTextContent("Certificate Not Found");
    expect(page).toHaveTextContent("not-a-real-code");
    expect(screen.getByRole("link", { name: "Enter another code" })).toHaveAttribute("href", "/verification-center");
  });

  it("too many checks says to wait, not that the certificate is fake", async () => {
    verify.mockRejectedValue(new ApiError("RATE_LIMITED", "x", 429));
    mount();
    const page = await screen.findByTestId("verify-not-found");
    expect(page).toHaveTextContent("Too many checks");
    expect(page).not.toHaveTextContent("Certificate Not Found");
  });
});

describe("VerifyCertificate when the service fails", () => {
  it("never tells a third party a genuine certificate does not exist", async () => {
    verify.mockReset();
    verify.mockRejectedValue(new ApiError("INTERNAL", "boom", 500));
    mount();
    const page = await screen.findByTestId("verify-not-found");
    expect(page).toHaveTextContent("Could not verify right now");
    expect(page).not.toHaveTextContent("Certificate Not Found");
    expect(page).toHaveTextContent("This says nothing about the certificate");
  });
});
