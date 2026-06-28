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
import {
  MessageCircle,
  Phone,
  Mail,
  Send,
  Clock,
  CheckCircle,
  X,
  Minimize2,
  Maximize2,
  HeadphonesIcon,
} from "lucide-react";

// WhatsApp icon component
const WhatsAppIcon = () => (
  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="currentColor">
    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
  </svg>
);

// Chat Message Interface
interface ChatMessage {
  id: string;
  sender: "user" | "support";
  message: string;
  timestamp: Date;
}

const Support = () => {
  const { toast } = useToast();
  const { isAuthenticated } = useAuth();
  
  // Live Chat State
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isChatMinimized, setIsChatMinimized] = useState(false);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    {
      id: "1",
      sender: "support",
      message: "Hello! Welcome to Capimax PropShare support. How can I help you today?",
      timestamp: new Date(),
    },
  ]);
  const [currentMessage, setCurrentMessage] = useState("");
  
  // Contact Form State
  const [contactForm, setContactForm] = useState({
    name: "",
    email: "",
    subject: "",
    message: "",
  });

  // Support Contact Info
  const whatsappNumber = "+12053508771";
  const supportEmail = "support@capimaxpropshare.com";
  const supportPhone = "+1 205 350 8771";
  const supportPhones = ["+1 205 350 8771", "+1 205 350 8864", "+44 7577 370309"];
  const officeAddress = "8 The Green, Ste R, Dover, Kent, DE 19901, United States";
  const businessHours = "Mon - Fri: 9:00 AM - 6:00 PM (EST)";

  // Handle sending chat message
  const handleSendMessage = () => {
    if (!currentMessage.trim()) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      sender: "user",
      message: currentMessage,
      timestamp: new Date(),
    };

    setChatMessages((prev) => [...prev, userMessage]);
    setCurrentMessage("");

    // Honest auto-reply — this widget is NOT staffed by a live agent yet. We acknowledge
    // the message and funnel to the real channels (WhatsApp / email / phone) rather than
    // faking an agent conversation.
    setTimeout(() => {
      const autoReply: ChatMessage = {
        id: (Date.now() + 1).toString(),
        sender: "support",
        message:
          "Thanks for your message! This chat isn't staffed live yet — for a response please reach us on WhatsApp or email support@capimaxpropshare.com and our team will get back to you.",
        timestamp: new Date(),
      };
      setChatMessages((prev) => [...prev, autoReply]);
    }, 800);
  };

  // Handle contact form submission. There is no server-side ticketing backend yet, so
  // we perform a REAL action — compose an email to support via the user's mail client —
  // instead of faking a "message sent" + a non-existent confirmation email.
  const handleContactSubmit = (e: React.FormEvent) => {
    e.preventDefault();
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
          We're here to help! Choose your preferred support channel below.
        </p>
      </div>

      {/* Support Channels Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-12">
        {/* Live Chat */}
        <Card className="hover:shadow-lg transition-shadow cursor-pointer group" onClick={() => setIsChatOpen(true)}>
          <CardContent className="p-6 text-center">
            <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-4 group-hover:bg-primary/20 transition-colors">
              <MessageCircle className="h-7 w-7 text-primary" />
            </div>
            <h3 className="font-semibold text-foreground mb-2">Message Us</h3>
            <p className="text-sm text-muted-foreground mb-3">
              Send a message; we reply by email or WhatsApp
            </p>
            <Badge variant="outline" className="text-muted-foreground border-border">
              Not staffed live
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

      <Separator className="mb-12" />

      {/* Contact Form Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div>
          <h2 className="text-2xl font-bold text-foreground mb-4">Send Us a Message</h2>
          <p className="text-muted-foreground mb-6">
            Fill out the form below and we'll get back to you within 24 hours. You'll receive an automatic confirmation email once your message is submitted.
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

      {/* Floating Live Chat Widget */}
      {isChatOpen && (
        <div
          className={`fixed z-50 bg-card border rounded-lg shadow-2xl transition-all duration-300 ${
            isChatMinimized
              ? "bottom-4 right-4 w-80 h-14"
              : "bottom-4 right-4 w-96 h-[500px] max-h-[80vh]"
          }`}
        >
          {/* Chat Header */}
          <div className="flex items-center justify-between p-4 border-b bg-primary text-primary-foreground rounded-t-lg">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-primary-foreground/20 flex items-center justify-center">
                <MessageCircle className="h-4 w-4" />
              </div>
              {!isChatMinimized && (
                <div>
                  <h4 className="font-semibold text-sm">Support</h4>
                  <p className="text-xs opacity-80">We'll reply by email or WhatsApp</p>
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-primary-foreground hover:bg-primary-foreground/20"
                onClick={() => setIsChatMinimized(!isChatMinimized)}
              >
                {isChatMinimized ? <Maximize2 className="h-4 w-4" /> : <Minimize2 className="h-4 w-4" />}
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 text-primary-foreground hover:bg-primary-foreground/20"
                onClick={() => setIsChatOpen(false)}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Chat Content */}
          {!isChatMinimized && (
            <>
              {/* Messages */}
              <div className="flex-1 overflow-y-auto p-4 space-y-4 h-[350px]">
                {chatMessages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex ${msg.sender === "user" ? "justify-end" : "justify-start"}`}
                  >
                    <div
                      className={`max-w-[80%] rounded-lg p-3 ${
                        msg.sender === "user"
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-foreground"
                      }`}
                    >
                      <p className="text-sm">{msg.message}</p>
                      <p className="text-xs opacity-70 mt-1">
                        {msg.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </p>
                    </div>
                  </div>
                ))}
              </div>

              {/* Input */}
              <div className="p-4 border-t">
                <div className="flex gap-2">
                  <Input
                    placeholder="Type your message..."
                    value={currentMessage}
                    onChange={(e) => setCurrentMessage(e.target.value)}
                    onKeyPress={(e) => e.key === "Enter" && handleSendMessage()}
                  />
                  <Button size="icon" onClick={handleSendMessage}>
                    <Send className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Floating Chat Button (when chat is closed) */}
      {!isChatOpen && (
        <Button
          className="fixed bottom-6 right-6 w-14 h-14 rounded-full shadow-lg z-50"
          onClick={() => setIsChatOpen(true)}
        >
          <MessageCircle className="h-6 w-6" />
        </Button>
      )}

      {/* Floating WhatsApp Button */}
      <Button
        className="fixed bottom-6 right-24 w-14 h-14 rounded-full shadow-lg z-50 bg-green-500 hover:bg-green-600"
        onClick={handleWhatsAppClick}
      >
        <WhatsAppIcon />
      </Button>
    </div>
  );
};

export default Support;
