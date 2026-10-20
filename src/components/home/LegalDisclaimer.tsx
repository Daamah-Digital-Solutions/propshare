import { Link } from "react-router-dom";

/**
 * The legal disclaimer at the very bottom of the home page, in small print as on other
 * investment platforms. Text supplied by the client (2026-10-20,
 * "Capimax_PropShare_Homepage_Legal_Disclosures_EN.docx"); keep it word for word.
 */
const LegalDisclaimer = () => (
  <section
    aria-labelledby="legal-disclaimer-title"
    data-testid="home-legal-disclaimer"
    className="border-t border-border bg-muted/30"
  >
    {/* pb-24 below md: the phone's bottom navigation bar sits over the page's last lines */}
    <div className="container mx-auto px-4 pt-8 pb-24 md:pb-8 max-w-5xl space-y-3 text-xs leading-relaxed text-muted-foreground">
      <h2 id="legal-disclaimer-title" className="text-xs font-semibold uppercase tracking-wide text-foreground/80">
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
        <Link to="/terms" className="underline underline-offset-2 hover:text-foreground">
          User Agreement
        </Link>{" "}
        and{" "}
        <Link to="/privacy" className="underline underline-offset-2 hover:text-foreground">
          Privacy Policy
        </Link>
        . Nothing in this disclaimer excludes liability that cannot lawfully be excluded.
      </p>
      <p className="pt-1">Copyright © 2026 Capimax Real Estate Technologies LLC. All rights reserved.</p>
    </div>
  </section>
);

export default LegalDisclaimer;
