import { Link } from "react-router-dom";
import { Mail, MapPin, Phone } from "lucide-react";

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
      <div className="container mx-auto px-4 py-16">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-8 lg:gap-12">
          {/* Brand Column */}
          <div className="lg:col-span-2">
            <Link to="/" className="flex items-center gap-2 mb-6">
              <div className="w-10 h-10 bg-primary rounded-xl flex items-center justify-center">
                <span className="text-primary-foreground font-bold text-lg">C</span>
              </div>
              <span className="text-xl font-bold">
                Capimax<span className="text-primary">PropShare</span>
              </span>
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

        {/* Bottom Bar */}
        <div className="border-t border-primary-foreground/10 mt-12 pt-8 flex flex-col md:flex-row justify-between items-center gap-4">
          <p className="text-sm text-primary-foreground/60">
            © 2024 Capimax PropShare. All rights reserved.
          </p>
          <div className="flex items-center gap-6">
            <span className="text-xs text-primary-foreground/40">
              Regulated by Financial Services Authority
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
