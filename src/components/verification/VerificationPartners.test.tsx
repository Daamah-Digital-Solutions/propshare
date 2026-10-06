/**
 * "Verify Your Documents" (client text, 2026-10-01): the five designated partners, each with
 * what it verifies, what to enter, and a link that opens the partner's own site in a new tab.
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { VerificationPartners } from "./VerificationPartners";
import { CERTIFICATE_PARTNER } from "@/lib/verificationPartners";

const PARTNERS: [string, string, string, string][] = [
  ["capimax_documents", "Powered by CIM Global Financial", "Verify Document / Certificate", "https://www.cimglobalfinancial.com/capimax-verify"],
  ["valuation_financial", "CIM Global Financial", "Verify Valuation / Financial Report", "https://www.cimglobalfinancial.com/capimax-verify"],
  ["insurance", "CoverTech Insurance", "Verify Insurance Certificate", "https://www.covertechinsurance.com/capimax-ecosystem"],
  ["legal", "LexCrest Global", "Verify Legal Document", "https://lexcrestlegal.xyz/document-center"],
  ["blockchain", "Proof Anchor", "Verify Blockchain Record", "https://www.proofanchor.io/verify"],
];

describe("VerificationPartners", () => {
  it("lists the five partners, in order, each linking to its own site in a new tab", () => {
    render(<VerificationPartners />);
    expect(screen.getByRole("heading", { name: "Verify Your Documents" })).toBeInTheDocument();
    const items = within(screen.getByTestId("verification-partners")).getAllByRole("listitem");
    expect(items).toHaveLength(5);
    PARTNERS.forEach(([key, provider, action, url], i) => {
      const card = screen.getByTestId(`verification-partner-${key}`);
      expect(items[i]).toBe(card);
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

  it("says what to enter at each partner and shows where the link goes", () => {
    render(<VerificationPartners />);
    const certificates = screen.getByTestId("verification-partner-capimax_documents");
    expect(certificates).toHaveTextContent("Capimax Documents & Investment Certificates");
    expect(certificates).toHaveTextContent(/Certificate Number, or scan the QR Code/);
    expect(certificates).toHaveTextContent("Open Capimax Verify — CIM Global Financial");
    expect(certificates).toHaveTextContent("cimglobalfinancial.com/capimax-verify");
    expect(screen.getByTestId("verification-partner-legal")).toHaveTextContent(
      /unique Document Number shown on the document/,
    );
    expect(screen.getByRole("heading", { name: "Independent Verification" })).toBeInTheDocument();
  });

  it("names the partner a certificate's own link goes to", () => {
    // the link under each certificate reference (dashboard tabs) and on the PDF
    expect(CERTIFICATE_PARTNER.key).toBe("capimax_documents");
    expect(CERTIFICATE_PARTNER.url).toBe("https://www.cimglobalfinancial.com/capimax-verify");
  });
});
