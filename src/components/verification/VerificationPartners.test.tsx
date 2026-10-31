/**
 * "Verify Your Documents" (client text, 2026-10-01; certificates 2026-10-28): investment
 * certificates are verified on PropShare itself, by their QR code or the code printed beside
 * it (as on Capimax BRX); the other four kinds of record link to their partner's own site in
 * a new tab.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { VerificationPartners } from "./VerificationPartners";
import { CERTIFICATE_PARTNER } from "@/lib/verificationPartners";

const PARTNERS: [string, string, string, string][] = [
  ["valuation_financial", "CIM Global Financial", "Verify Valuation / Financial Report", "https://www.cimglobalfinancial.com/capimax-verify"],
  ["insurance", "CoverTech Insurance", "Verify Insurance Certificate", "https://www.covertechinsurance.com/capimax-ecosystem"],
  ["legal", "LexCrest Global", "Verify Legal Document", "https://lexcrestlegal.xyz/document-center"],
  ["blockchain", "Proof Anchor", "Verify Blockchain Record", "https://www.proofanchor.io/verify"],
];

function VerifyPage() {
  const { code } = useParams();
  return <p data-testid="verify-page">{code}</p>;
}

function mount() {
  return render(
    <MemoryRouter initialEntries={["/verification-center"]}>
      <Routes>
        <Route path="/verification-center" element={<VerificationPartners />} />
        <Route path="/verify/:code" element={<VerifyPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("VerificationPartners", () => {
  it("lists the five services in order; the four partners link to their own site in a new tab", () => {
    mount();
    expect(screen.getByRole("heading", { name: "Verify Your Documents" })).toBeInTheDocument();
    const items = within(screen.getByTestId("verification-partners")).getAllByRole("listitem");
    expect(items).toHaveLength(5);
    expect(items[0]).toBe(screen.getByTestId("verification-partner-capimax_certificates"));
    PARTNERS.forEach(([key, provider, action, url], i) => {
      const card = screen.getByTestId(`verification-partner-${key}`);
      expect(items[i + 1]).toBe(card);
      expect(card).toHaveTextContent(provider);
      const button = within(card).getByRole("link", { name: new RegExp(action.replace("/", "\\/")) });
      expect(button).toHaveAttribute("href", url);
      for (const link of within(card).getAllByRole("link")) {
        expect(link).toHaveAttribute("href", url);
        expect(link).toHaveAttribute("target", "_blank");
        expect(link).toHaveAttribute("rel", "noopener noreferrer");
      }
    });
  });

  it("certificates are verified here by QR code, no longer at CIM Global Financial", () => {
    mount();
    const card = screen.getByTestId("verification-partner-capimax_certificates");
    expect(card).toHaveTextContent("Capimax PropShare Investment Certificates");
    expect(card).toHaveTextContent("Verified on Capimax PropShare by QR code");
    expect(card).toHaveTextContent(/Scan the QR code printed on the certificate/);
    expect(card).not.toHaveTextContent(/CIM Global Financial|cimglobalfinancial/);
    expect(within(card).queryAllByRole("link")).toHaveLength(0); // no partner to send it to
    expect(screen.getByTestId("verification-partner-legal")).toHaveTextContent(
      /unique Document Number shown on the document/,
    );
    expect(screen.getByRole("heading", { name: "Independent Verification" })).toBeInTheDocument();
  });

  it("the code printed beside the QR code opens the certificate's verification page", () => {
    mount();
    const form = screen.getByTestId("certificate-check");
    const submit = within(form).getByRole("button", { name: /verify certificate/i });
    expect(submit).toBeDisabled(); // nothing to check yet
    fireEvent.change(within(form).getByLabelText("Verification code on the certificate"), {
      target: { value: "  Xq3vN8bKp2LmR5tY7wZa1c " },
    });
    fireEvent.click(submit);
    expect(screen.getByTestId("verify-page")).toHaveTextContent("Xq3vN8bKp2LmR5tY7wZa1c");
  });

  it("a code that is not URL-safe is escaped, never read as a path", () => {
    mount();
    fireEvent.change(screen.getByLabelText("Verification code on the certificate"), {
      target: { value: "../admin?x=1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /verify certificate/i }));
    expect(screen.getByTestId("verify-page")).toHaveTextContent("../admin?x=1");
  });

  it("names how a certificate is verified", () => {
    expect(CERTIFICATE_PARTNER.key).toBe("capimax_certificates");
    expect(CERTIFICATE_PARTNER.internal).toBe(true);
    expect(CERTIFICATE_PARTNER.url).toBe("/verification-center");
  });
});
