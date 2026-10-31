/**
 * Where each kind of Capimax record is verified (client text, 2026-10-01), shown on the
 * Verification Center page and in the dashboard's Verification tab. The first is PropShare's
 * own (client, 2026-10-28, as on Capimax BRX): an investment certificate's QR code opens its
 * verification page here, /verify/{code}; it is no longer checked at CIM Global Financial. The
 * other four are partners' sites.
 *
 * The backend keeps the same five for the assistant, which may link exactly the partners' URLs
 * (backend/app/services/verification_partners.py); test_verification_services.py keeps the
 * two lists in step. The blockchain wording of the fifth entry is about the ecosystem's
 * blockchain-enabled platforms (Capimax BRX, Capimax RT), never about PropShare units.
 */

export interface VerificationPartner {
  key: string;
  title: string;
  provider: string;
  /** The provider line exactly as the client wrote it ("Powered by …" for the first). */
  providerLine: string;
  description: string;
  howTo: string;
  action: string;
  linkLabel: string;
  url: string;
  /** Checked on PropShare itself (url is a page of the site, not a partner's link). */
  internal?: boolean;
}

export const VERIFY_INTRO = {
  title: "Verify Your Documents",
  text:
    "Independently verify the authenticity, validity and current status of documents, " +
    "certificates and records associated with the Capimax Ecosystem through our designated " +
    "verification partners.",
};

export const INDEPENDENT_VERIFICATION = {
  title: "Independent Verification",
  text:
    "Capimax provides direct access to designated third-party verification systems so " +
    "investors, asset owners, developers and partners can independently authenticate relevant " +
    "records and review their verification status directly from the corresponding provider.",
};

export const VERIFICATION_PARTNERS: VerificationPartner[] = [
  {
    key: "capimax_certificates",
    title: "Capimax PropShare Investment Certificates",
    provider: "Capimax PropShare",
    providerLine: "Verified on Capimax PropShare by QR code",
    description:
      "Every investment certificate issued on Capimax PropShare carries its own QR code. " +
      "Scanning it opens the certificate's verification page here on the platform, showing " +
      "whether it is authentic and its current status.",
    howTo:
      "Scan the QR code printed on the certificate with your phone's camera. Can't scan it? " +
      "Enter the verification code shown beside the QR code below.",
    action: "Verify Certificate",
    linkLabel: "Verify a certificate",
    url: "/verification-center",
    internal: true,
  },
  {
    key: "valuation_financial",
    title: "Valuation & Financial Document Verification",
    provider: "CIM Global Financial",
    providerLine: "CIM Global Financial",
    description:
      "Verify property and unit valuation reports, investment studies, financial analyses, " +
      "accounting records, financial reports, due diligence reports and other financial " +
      "documents associated with Capimax assets and projects.",
    howTo:
      "Enter the Document Number or Verification ID to authenticate the record and access " +
      "available verified documentation.",
    action: "Verify Valuation / Financial Report",
    linkLabel: "Verify with CIM Global Financial",
    url: "https://www.cimglobalfinancial.com/capimax-verify",
  },
  {
    key: "insurance",
    title: "Insurance Certificate Verification",
    provider: "CoverTech Insurance",
    providerLine: "CoverTech Insurance",
    description:
      "Verify insurance certificates and insurance-related documents issued for Capimax assets, " +
      "investments, platforms and associated risks.",
    howTo:
      "Use the verification service to confirm the authenticity, coverage information and " +
      "current status of the relevant insurance certificate or document.",
    action: "Verify Insurance Certificate",
    linkLabel: "Verify with CoverTech Insurance",
    url: "https://www.covertechinsurance.com/capimax-ecosystem",
  },
  {
    key: "legal",
    title: "Legal Document & Agreement Verification",
    provider: "LexCrest Global",
    providerLine: "LexCrest Global",
    description:
      "Verify legal documents, agreements, due diligence documents and other legal records " +
      "associated with Capimax assets, transactions and platforms.",
    howTo:
      "Enter the unique Document Number shown on the document to confirm its authenticity. " +
      "Where permitted, public documents may also be previewed or downloaded.",
    action: "Verify Legal Document",
    linkLabel: "Open LexCrest Document Center",
    url: "https://lexcrestlegal.xyz/document-center",
  },
  {
    key: "blockchain",
    title: "Blockchain, Smart Contract & Digital Asset Verification",
    provider: "Proof Anchor",
    providerLine: "Proof Anchor",
    description:
      "Verify blockchain records, smart contracts, tokenized assets, tokens, audit reports and " +
      "digital certificates associated with Capimax blockchain-enabled platforms.",
    howTo:
      "Search using a Certificate Number, Verification Number, Contract Address, Token Address, " +
      "Asset ID, or Project Name to access the corresponding verification record.",
    action: "Verify Blockchain Record",
    linkLabel: "Verify with Proof Anchor",
    url: "https://www.proofanchor.io/verify",
  },
];

/** How an investment certificate PropShare issues is verified: its QR code, here
 * (the backend's verification_partners.CERTIFICATES). */
export const CERTIFICATE_PARTNER = VERIFICATION_PARTNERS[0];

/** "www.example.com/path" for showing where a link goes. */
export function displayUrl(url: string): string {
  return url.replace(/^https?:\/\//, "").replace(/^www\./, "").replace(/\/$/, "");
}
