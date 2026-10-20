import { Link } from "react-router-dom";
import { Mail, MapPin, Phone } from "lucide-react";
import LegalDisclaimer, { LEGAL_COPYRIGHT } from "@/components/home/LegalDisclaimer";

const Footer = () => {
  // Every href below resolves to a real route in App.tsx (no 404s). Links that had no
  // destination (Careers / Press / a separate "About Us") were removed per the cleanup
  // pass; the rest are repointed to the real equivalent page.
  const footerLinks = {
    invest: [
      { label: "Browse Properties", href: "/marketplace" },
      { label: "How It Works", href: "/how-it-works" },
      { label: "Secondary Market", href: "/secondary-market" },
      { label: "Fees", href: "/fees" },
    ],
    company: [
      { label: "About Capimax PropShare", href: "/about-capimax-propshare" },
      { label: "Verification Center", href: "/verification-center" },
      { label: "Partners", href: "/partners" },
      { label: "Platform Rules", href: "/platform-rules" },
    ],
    legal: [
      { label: "Terms & Conditions", href: "/terms" },
      { label: "Privacy Policy", href: "/privacy" },
      { label: "Risk Disclosure", href: "/risk-disclosure" },
      { label: "Compliance", href: "/legal" },
    ],
    support: [
      { label: "Help Center", href: "/support" },
      { label: "FAQ", href: "/faq" },
      { label: "Contact Us", href: "/support" },
      { label: "Disclaimer", href: "/disclaimer" },
    ],
  };

  return (
    <footer className="bg-foreground text-primary-foreground">
      {/* pb-24 below md: the phone's bottom navigation bar sits over the page's last lines */}
      <div className="container mx-auto px-4 pt-16 pb-24 md:pb-16">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-8 lg:gap-12">
          {/* Brand Column */}
          <div className="lg:col-span-2">
            <Link to="/" className="flex items-center mb-6">
              <img src="/capimax-logo-white.png" alt="Capimax PropShare" className="h-9 w-auto" />
            </Link>
            <p className="text-primary-foreground/70 mb-6 max-w-xs">
              Democratizing real estate investment through fractional ownership. Build wealth with as little as $100.
            </p>
            <div className="flex flex-col gap-3 text-sm text-primary-foreground/70">
              <div className="flex items-center gap-2">
                <Mail size={16} />
                <span>support@capimaxpropshare.com</span>
              </div>
              <div className="flex items-start gap-2">
                <Phone size={16} className="mt-0.5 shrink-0" />
                <div className="flex flex-col">
                  <span>USA: +1 205 350 8771</span>
                  <span>USA: +1 205 350 8864</span>
                  <span>UK: +44 7577 370309</span>
                </div>
              </div>
              <div className="flex items-start gap-2">
                <MapPin size={16} className="mt-0.5 shrink-0" />
                <div className="flex flex-col">
                  <span>8 The Green, Ste R</span>
                  <span>Dover, Kent, DE 19901</span>
                  <span>United States</span>
                </div>
              </div>
            </div>
          </div>

          {/* Invest Links */}
          <div>
            <h4 className="font-semibold mb-4">Invest</h4>
            <ul className="space-y-3">
              {footerLinks.invest.map((link) => (
                <li key={link.label}>
                  <Link
                    to={link.href}
                    className="text-primary-foreground/70 hover:text-primary transition-colors text-sm"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Company Links */}
          <div>
            <h4 className="font-semibold mb-4">Company</h4>
            <ul className="space-y-3">
              {footerLinks.company.map((link) => (
                <li key={link.label}>
                  <Link
                    to={link.href}
                    className="text-primary-foreground/70 hover:text-primary transition-colors text-sm"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Legal Links */}
          <div>
            <h4 className="font-semibold mb-4">Legal</h4>
            <ul className="space-y-3">
              {footerLinks.legal.map((link) => (
                <li key={link.label}>
                  <Link
                    to={link.href}
                    className="text-primary-foreground/70 hover:text-primary transition-colors text-sm"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Support Links */}
          <div>
            <h4 className="font-semibold mb-4">Support</h4>
            <ul className="space-y-3">
              {footerLinks.support.map((link) => (
                <li key={link.label}>
                  <Link
                    to={link.href}
                    className="text-primary-foreground/70 hover:text-primary transition-colors text-sm"
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* The client's legal disclaimer, in small print (2026-10-20) */}
        <LegalDisclaimer className="border-t border-primary-foreground/10 mt-12 pt-8 text-primary-foreground/60" />

        {/* Bottom Bar. No regulator line: the disclaimer above states Capimax is not a registered
            broker-dealer or investment adviser. */}
        <div className="border-t border-primary-foreground/10 mt-8 pt-8 flex flex-col md:flex-row justify-between items-center gap-4">
          <p className="text-sm text-primary-foreground/60">{LEGAL_COPYRIGHT}</p>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
