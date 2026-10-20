import { Link } from "react-router-dom";

/**
 * The legal disclaimer, in small print as on other investment platforms, shown inside the
 * site footer (above its copyright line). Text supplied by the client (2026-10-20,
 * "Capimax_PropShare_Homepage_Legal_Disclosures_EN.docx"); keep it word for word. Its
 * copyright sentence is the footer's last line.
 */
const LegalDisclaimer = ({ className = "" }: { className?: string }) => (
  <section
    aria-labelledby="legal-disclaimer-title"
    data-testid="home-legal-disclaimer"
    className={`space-y-3 text-xs leading-relaxed ${className}`}
  >
    <h2 id="legal-disclaimer-title" className="text-xs font-semibold uppercase tracking-wide">
      Capimax PropShare Legal Disclaimer
    </h2>
    <p>
      This website is operated by Capimax Real Estate Technologies LLC (“Capimax”). Capimax
      PropShare is a technology platform and digital ecosystem connecting investors, property
      owners, developers, brokers and liquidity providers.
    </p>
    <p>
      Capimax is not a registered broker-dealer or investment adviser and does not provide
      financial advisory services, personalised investment advice, or recommendations to buy,
      hold or sell any investment. Listings and website content are provided for information and
      do not constitute an endorsement or assurance of suitability.
    </p>
    <p>
      All investments involve risk, including the possible loss of some or all invested capital.
      Capimax does not guarantee returns, income, capital appreciation, liquidity or repayment of
      capital. Past performance is not a reliable indicator of future results.
    </p>
    <p>
      You are responsible for assessing whether an investment is appropriate for your financial
      circumstances, objectives and risk tolerance. Review the applicable documents and seek
      independent advice from qualified legal, tax and investment professionals before investing.
    </p>
    <p>
      Use of this website is subject to our{" "}
      <Link to="/terms" className="underline underline-offset-2 hover:opacity-80">
        User Agreement
      </Link>{" "}
      and{" "}
      <Link to="/privacy" className="underline underline-offset-2 hover:opacity-80">
        Privacy Policy
      </Link>
      . Nothing in this disclaimer excludes liability that cannot lawfully be excluded.
    </p>
  </section>
);

export const LEGAL_COPYRIGHT =
  "Copyright © 2026 Capimax Real Estate Technologies LLC. All rights reserved.";

export default LegalDisclaimer;
