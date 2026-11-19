/**
 * A certificate says whether its units are fully paid (client, 2026-11-18, every Capimax
 * platform); certificates issued before the label existed show nothing.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CertificatePaymentBadge } from "./CertificatePaymentBadge";

describe("CertificatePaymentBadge", () => {
  it("final and provisional", () => {
    const { rerender } = render(<CertificatePaymentBadge status="final" />);
    expect(screen.getByTestId("certificate-payment")).toHaveTextContent("FINAL · FULLY PAID");
    rerender(<CertificatePaymentBadge status="provisional" />);
    expect(screen.getByTestId("certificate-payment")).toHaveTextContent(
      "PROVISIONAL · INSTALLMENTS OUTSTANDING",
    );
  });

  it("nothing for a certificate issued before the label", () => {
    const { container } = render(<CertificatePaymentBadge status={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
