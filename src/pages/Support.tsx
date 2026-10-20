import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/contexts/AuthContext";
import { Link } from "react-router-dom";
import { ApiError } from "@/lib/api";
import { ASSISTANT_V2_FLAG, TICKET_CATEGORIES, ticketsApi } from "@/lib/assistantApi";
import { openAssistant } from "@/lib/assistantEvents";
import {
  MessageCircle,
  Phone,
  Mail,
  Send,
  Clock,
  CheckCircle,
  HeadphonesIcon,
  ScrollText,
  Sparkles,
} from "lucide-react";

// WhatsApp icon component
const WhatsAppIcon = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
  </svg>
);

const Support = () => {
  const { toast } = useToast();
  const { isAuthenticated } = useAuth();
  
  // Contact Form State
  const [contactForm, setContactForm] = useState({
    name: "",
    email: "",
    subject: "",
    message: "",
  });
  const [contactCategory, setContactCategory] = useState<string>("other");

  // Support Contact Info
  const whatsappNumber = "+12053508771";
  const supportEmail = "support@capimaxpropshare.com";
  const supportPhone = "+1 205 350 8771";
  const supportPhones = ["+1 205 350 8771", "+1 205 350 8864", "+44 7577 370309"];
  const officeAddress = "8 The Green, Ste R, Dover, Kent, DE 19901, United States";
  const businessHours = "Mon - Fri: 9:00 AM - 6:00 PM (EST)";

  // Handle contact form submission. There is no server-side ticketing backend yet, so
  // we perform a REAL action — compose an email to support via the user's mail client —
  // instead of faking a "message sent" + a non-existent confirmation email.
  const handleContactSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (ASSISTANT_V2_FLAG) {
      // Assistant v2: a real ticket in the platform (staff reply from the admin panel; the
      // member follows it under /support/tickets). Visitors identify by email.
      try {
        const ticket = await ticketsApi.create({
          category: contactCategory,
          subject: contactForm.subject || "Support request",
          body: `Name: ${contactForm.name}\n\n${contactForm.message}`,
          contact_email: isAuthenticated ? undefined : contactForm.email,
        });
        setContactForm({ name: "", email: "", subject: "", message: "" });
        toast({
          title: `Ticket ${ticket.ticket_no} opened`,
          description: isAuthenticated
            ? "We will reply here and notify you. You can follow it under My tickets."
            : `We will reply by email to ${contactForm.email}.`,
        });
      } catch (err) {
        toast({
          title: "Could not send",
          description: err instanceof ApiError ? err.message : "Please try again or email us directly.",
          variant: "destructive",
        });
      }
      return;
    }
    const subject = encodeURIComponent(contactForm.subject || "Support request");
    const body = encodeURIComponent(
      `Name: ${contactForm.name}\nEmail: ${contactForm.email}\n\n${contactForm.message}`,
    );
    window.location.href = `mailto:${supportEmail}?subject=${subject}&body=${body}`;
    toast({
      title: "Opening your email app",
      description: `If nothing opens, email us directly at ${supportEmail}.`,
    });
  };

  // Handle WhatsApp click
  const handleWhatsAppClick = () => {
    const message = encodeURIComponent("Hello, I need assistance with Capimax PropShare.");
    window.open(`https://wa.me/${whatsappNumber.replace(/\D/g, "")}?text=${message}`, "_blank");
  };

  // Handle phone click
  const handlePhoneClick = () => {
    window.location.href = `tel:${supportPhone.replace(/\s/g, "")}`;
  };

  // Handle email click
  // PropShare AI is the first line of support (client, 2026-10-20). With no assistant on
  // this page (switched off), the ticket form below is the way to reach the team.
  const handleAskAi = () => {
    if (openAssistant()) return;
    document.getElementById("contact-form")?.scrollIntoView({ behavior: "smooth", block: "start" });
    toast({
      title: "The assistant is not available right now",
      description: "Send us your question with the form below and our team will reply.",
    });
  };

  const handleEmailClick = () => {
    window.location.href = `mailto:${supportEmail}`;
  };

  return (
    <div className="container mx-auto px-4 py-8 max-w-6xl">
      {/* Page Header */}
      <div className="text-center mb-12">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
          <HeadphonesIcon className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-4xl font-bold text-foreground mb-4">Support & Help Center</h1>
        <p className="text-muted-foreground text-lg max-w-2xl mx-auto">
          Ask PropShare AI first: it answers right away, any time. Our team is here too.
        </p>
      </div>

      {/* PropShare AI: the first line of support */}
      <Card className="mb-8 border-primary/30 bg-primary/5" data-testid="propshare-ai">
        <CardContent className="p-6 md:p-8 grid gap-6 md:grid-cols-[1fr_auto] md:items-center">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="h-5 w-5 text-primary" />
              <h2 className="text-2xl font-bold text-foreground">Ask PropShare AI</h2>
              <Badge className="ml-1">24/7</Badge>
            </div>
            <p className="text-muted-foreground mb-4 max-w-2xl">
              PropShare AI is our full customer service, ready any time of day. Ask it any question
              about your account and your investments and it answers straight away, using your own
              account details, and helps you with what you need next.
            </p>
            <ul className="grid gap-2 sm:grid-cols-2 text-sm text-foreground">
              {[
                "Your investments, returns, installments and wallet",
                "Payments, deposits and withdrawals: their status and next steps",
                "Your documents, certificates and statements, and where to get them",
                "Verification (KYC) and what your account still needs",
                "Properties, fees and how PropShare works",
                "When something needs our team, it opens a support ticket for you",
              ].map((item) => (
                <li key={item} className="flex items-start gap-2">
                  <CheckCircle className="h-4 w-4 text-primary mt-0.5 shrink-0" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
          <Button size="lg" className="gap-2" onClick={handleAskAi}>
            <MessageCircle className="h-5 w-5" /> Chat with PropShare AI
          </Button>
        </CardContent>
      </Card>

      {/* Support Channels Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-12">
        {/* PropShare AI */}
        <Card className="hover:shadow-lg transition-shadow cursor-pointer group" onClick={handleAskAi}>
          <CardContent className="p-6 text-center">
            <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4 group-hover:bg-primary/20 transition-colors">
              <MessageCircle className="h-7 w-7 text-primary" />
            </div>
            <h3 className="font-semibold text-foreground mb-2">Ask PropShare AI</h3>
            <p className="text-sm text-muted-foreground mb-3">
              Instant answers about your investments, payments, documents and account
            </p>
            <Badge variant="outline" className="text-primary border-primary/40">
              Available 24/7
            </Badge>
          </CardContent>
        </Card>

        {/* WhatsApp */}
        <Card className="hover:shadow-lg transition-shadow cursor-pointer group" onClick={handleWhatsAppClick}>
          <CardContent className="p-6 text-center">
            <div className="w-14 h-14 rounded-full bg-green-500/10 flex items-center justify-center mx-auto mb-4 group-hover:bg-green-500/20 transition-colors">
              <WhatsAppIcon />
            </div>
            <h3 className="font-semibold text-foreground mb-2">WhatsApp Support</h3>
            <p className="text-sm text-muted-foreground mb-3">
              Quick responses via WhatsApp
            </p>
            <span className="text-sm text-primary font-medium">{whatsappNumber}</span>
          </CardContent>
        </Card>

        {/* Email */}
        <Card className="hover:shadow-lg transition-shadow cursor-pointer group" onClick={handleEmailClick}>
          <CardContent className="p-6 text-center">
            <div className="w-14 h-14 rounded-full bg-blue-500/10 flex items-center justify-center mx-auto mb-4 group-hover:bg-blue-500/20 transition-colors">
              <Mail className="h-7 w-7 text-blue-500" />
            </div>
            <h3 className="font-semibold text-foreground mb-2">Email Support</h3>
            <p className="text-sm text-muted-foreground mb-3">
              Detailed assistance via email
            </p>
            <span className="text-sm text-primary font-medium break-all">{supportEmail}</span>
          </CardContent>
        </Card>

        {/* Phone */}
        <Card className="hover:shadow-lg transition-shadow cursor-pointer group" onClick={handlePhoneClick}>
          <CardContent className="p-6 text-center">
            <div className="w-14 h-14 rounded-full bg-amber-500/10 flex items-center justify-center mx-auto mb-4 group-hover:bg-amber-500/20 transition-colors">
              <Phone className="h-7 w-7 text-amber-500" />
            </div>
            <h3 className="font-semibold text-foreground mb-2">Phone Support</h3>
            <p className="text-sm text-muted-foreground mb-3">
              Speak directly with our team
            </p>
            <div className="flex flex-col gap-1">
              {supportPhones.map((p) => (
                <span key={p} className="text-sm text-primary font-medium">{p}</span>
              ))}
            </div>
            <p className="mt-3 text-xs text-muted-foreground">{officeAddress}</p>
          </CardContent>
        </Card>
      </div>

      {/* Business Hours Notice */}
      <div className="flex items-center justify-center gap-2 text-muted-foreground mb-12">
        <Clock className="h-4 w-4" />
        <span className="text-sm">Business Hours: {businessHours}</span>
      </div>

      {/* Where a person an account holder named reports the holder's death and claims */}
      <Card className="mb-12 border-primary/20 bg-primary/5">
        <CardContent className="p-5 flex flex-col sm:flex-row sm:items-center gap-4">
          <div className="w-11 h-11 rounded-full bg-primary/15 text-primary flex items-center justify-center shrink-0">
            <ScrollText className="h-5 w-5" />
          </div>
          <div className="flex-1">
            <h3 className="font-semibold text-foreground">Reporting the death of an account holder?</h3>
            <p className="text-sm text-muted-foreground">
              If the holder named you as beneficiary or heir and gave you a certificate, make your claim
              here. You do not need an account to send it.
            </p>
          </div>
          <Button asChild variant="outline" className="shrink-0">
            <Link to="/estate-claim">Report a death or make a claim</Link>
          </Button>
        </CardContent>
      </Card>

      <Separator className="mb-12" />

      {/* Contact Form Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div>
          <div className="mb-4 flex items-center justify-between gap-4">
            <h2 id="contact-form" className="text-2xl font-bold text-foreground scroll-mt-20">Send Us a Message</h2>
            {ASSISTANT_V2_FLAG && isAuthenticated && (
              <Button asChild variant="outline" size="sm">
                <Link to="/support/tickets">My tickets</Link>
              </Button>
            )}
          </div>
          <p className="text-muted-foreground mb-6">
            {ASSISTANT_V2_FLAG
              ? "Fill out the form below and a ticket is opened for our team. You will be notified of every reply."
              : "Fill out the form below and we'll get back to you within 24 hours. You'll receive an automatic confirmation email once your message is submitted."}
          </p>

          <Card>
            <CardContent className="p-6">
              <form onSubmit={handleContactSubmit} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="name">Full Name</Label>
                    <Input
                      id="name"
                      placeholder="Your full name"
                      value={contactForm.name}
                      onChange={(e) => setContactForm({ ...contactForm, name: e.target.value })}
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="email">Email Address</Label>
                    <Input
                      id="email"
                      type="email"
                      placeholder="your@email.com"
                      value={contactForm.email}
                      onChange={(e) => setContactForm({ ...contactForm, email: e.target.value })}
                      required
                    />
                  </div>
                </div>

                {ASSISTANT_V2_FLAG && (
                  <div className="space-y-2">
                    <Label htmlFor="category">Topic</Label>
                    <select
                      id="category"
                      value={contactCategory}
                      onChange={(e) => setContactCategory(e.target.value)}
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    >
                      {TICKET_CATEGORIES.map((c) => (
                        <option key={c} value={c}>
                          {c.replace("_", " ")}
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <div className="space-y-2">
                  <Label htmlFor="subject">Subject</Label>
                  <Input
                    id="subject"
                    placeholder="What is your inquiry about?"
                    value={contactForm.subject}
                    onChange={(e) => setContactForm({ ...contactForm, subject: e.target.value })}
                    required
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="message">Message</Label>
                  <Textarea
                    id="message"
                    placeholder="Please describe your inquiry in detail..."
                    rows={5}
                    value={contactForm.message}
                    onChange={(e) => setContactForm({ ...contactForm, message: e.target.value })}
                    required
                  />
                </div>

                <Button type="submit" className="w-full" size="lg">
                  <Send className="h-4 w-4 mr-2" />
                  Send Message
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>

        {/* Quick Help Section */}
        <div>
          <h2 className="text-2xl font-bold text-foreground mb-4">Quick Help</h2>
          <p className="text-muted-foreground mb-6">
            Find answers to common questions or get quick assistance.
          </p>

          <div className="space-y-4">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-lg">How do I start investing?</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Create an account, complete KYC verification, browse properties in the marketplace, and choose your investment amount. It's that simple!
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-lg">What are the minimum investment amounts?</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Minimum investments vary by property, typically starting from AED 500. Check individual property pages for specific requirements.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-lg">How do I track my returns?</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Log in to your investor dashboard to view your portfolio, track returns, and access detailed analytics on all your investments.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-lg">Can I sell my shares?</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Yes! Use our Secondary Market to list your shares for sale. A 2% exit fee applies to all sales.
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>

    </div>
  );
};

export default Support;
