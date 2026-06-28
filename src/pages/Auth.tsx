import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import { useAuth } from "@/contexts/AuthContext";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { authApi, ApiError } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import {
  Mail,
  Lock,
  Phone,
  User,
  Eye,
  EyeOff,
  ArrowRight,
  Chrome,
  Apple,
} from "lucide-react";

const Auth = () => {
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const { isAuthenticated, login, register } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { toast } = useToast();

  // Form states
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [regEmail, setRegEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [usDisclosure, setUsDisclosure] = useState(false);
  const [terms, setTerms] = useState(false);
  // Broker referral code (Phase 11) — captured from a ?ref=CODE share link, editable.
  const [referralCode, setReferralCode] = useState("");

  useEffect(() => {
    const ref = searchParams.get("ref");
    if (ref) setReferralCode(ref);
  }, [searchParams]);

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate("/dashboard");
    }
  }, [isAuthenticated, navigate]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    try {
      await login(loginEmail, loginPassword);
      toast({ title: "Welcome back!", description: "You have successfully signed in." });
      navigate("/dashboard");
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "An unexpected error occurred. Please try again.";
      toast({ title: "Login Failed", description: message, variant: "destructive" });
    } finally {
      setIsLoading(false);
    }
  };

  const handleForgotPassword = async () => {
    if (!loginEmail) {
      toast({
        title: "Enter your email",
        description: "Type your email above, then click “Forgot password?” again.",
        variant: "destructive",
      });
      return;
    }
    try {
      await authApi.forgotPassword(loginEmail);
    } finally {
      // Always show the same message — we never reveal whether an account exists.
      toast({
        title: "Check your email",
        description: "If that email is registered, a password-reset link is on its way.",
      });
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!usDisclosure || !terms) {
      toast({
        title: "Agreement Required",
        description: "Please accept the required agreements to continue.",
        variant: "destructive",
      });
      return;
    }

    if (regPassword.length < 6) {
      toast({
        title: "Password Too Short",
        description: "Password must be at least 6 characters long.",
        variant: "destructive",
      });
      return;
    }

    setIsLoading(true);

    try {
      await register({
        email: regEmail,
        password: regPassword,
        full_name: `${firstName} ${lastName}`.trim(),
        phone: phone || undefined,
        referral_code: referralCode.trim() || undefined,
      });
      toast({
        title: "Account Created!",
        description: "Welcome to Capimax PropShare. Check your email to verify your address.",
      });
      navigate("/dashboard");
    } catch (error) {
      if (error instanceof ApiError && error.code === "EMAIL_EXISTS") {
        toast({
          title: "Account Exists",
          description: "An account with this email already exists. Please sign in instead.",
          variant: "destructive",
        });
      } else {
        const message =
          error instanceof ApiError ? error.message : "An unexpected error occurred. Please try again.";
        toast({ title: "Registration Failed", description: message, variant: "destructive" });
      }
    } finally {
      setIsLoading(false);
    }
  };

  // OAuth: redirect to the provider's authorize page. It returns to
  // /auth/callback/:provider with a ?code, which AuthCallback exchanges with the
  // backend. Degrades honestly: if the public client id isn't configured yet, we
  // say so instead of starting a broken flow.
  const startOAuth = (provider: "google" | "apple") => {
    const origin = window.location.origin;
    const redirectUri = `${origin}/auth/callback/${provider}`;
    if (provider === "google") {
      const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
      if (!clientId) {
        toast({
          title: "Google sign-in not configured yet",
          description: "It will work as soon as the Google client ID is set.",
          variant: "destructive",
        });
        return;
      }
      const params = new URLSearchParams({
        client_id: clientId,
        redirect_uri: redirectUri,
        response_type: "code",
        scope: "openid email profile",
        prompt: "select_account",
      });
      window.location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params}`;
      return;
    }
    // apple
    const clientId = import.meta.env.VITE_APPLE_CLIENT_ID as string | undefined;
    if (!clientId) {
      toast({
        title: "Apple sign-in not configured yet",
        description: "It will work as soon as the Apple Services ID is set.",
        variant: "destructive",
      });
      return;
    }
    const params = new URLSearchParams({
      client_id: clientId,
      redirect_uri: redirectUri,
      response_type: "code",
      scope: "email name",
      response_mode: "query",
    });
    window.location.href = `https://appleid.apple.com/auth/authorize?${params}`;
  };

  const handleGoogleSignIn = () => startOAuth("google");
  const handleAppleSignIn = () => startOAuth("apple");

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-gradient-to-br from-primary to-primary/80 rounded-2xl flex items-center justify-center mx-auto mb-4 shadow-lg">
            <span className="text-primary-foreground font-bold text-2xl">C</span>
          </div>
          <h1 className="text-2xl font-bold text-foreground">
            Welcome to Capimax<span className="text-primary">PropShare</span>
          </h1>
          <p className="text-muted-foreground mt-2">
            Invest in premium real estate from $100
          </p>
        </div>

        <Card className="bg-card border-border">
          <CardContent className="p-6">
            <Tabs defaultValue="login" className="space-y-6">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="login">Sign In</TabsTrigger>
                <TabsTrigger value="register">Register</TabsTrigger>
              </TabsList>

              <TabsContent value="login" className="space-y-4">
                <form onSubmit={handleLogin} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="email">Email</Label>
                    <div className="relative">
                      <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                      <Input
                        id="email"
                        type="email"
                        placeholder="name@example.com"
                        className="pl-10"
                        value={loginEmail}
                        onChange={(e) => setLoginEmail(e.target.value)}
                        required
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="password">Password</Label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                      <Input
                        id="password"
                        type={showPassword ? "text" : "password"}
                        placeholder="••••••••"
                        className="pl-10 pr-10"
                        value={loginPassword}
                        onChange={(e) => setLoginPassword(e.target.value)}
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      >
                        {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  <div className="flex items-center justify-end">
                    <Button
                      type="button"
                      variant="link"
                      className="p-0 h-auto text-primary"
                      onClick={handleForgotPassword}
                    >
                      Forgot password?
                    </Button>
                  </div>

                  <Button type="submit" className="w-full gap-2" disabled={isLoading}>
                    {isLoading ? "Signing in..." : "Sign In"}
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </form>

                <div className="relative">
                  <Separator />
                  <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-card px-2 text-xs text-muted-foreground">
                    or continue with
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <Button 
                    variant="outline" 
                    className="gap-2" 
                    onClick={handleGoogleSignIn}
                    disabled={isLoading}
                  >
                    <Chrome className="h-4 w-4" />
                    Google
                  </Button>
                  <Button 
                    variant="outline" 
                    className="gap-2"
                    onClick={handleAppleSignIn}
                    disabled={isLoading}
                  >
                    <Apple className="h-4 w-4" />
                    Apple
                  </Button>
                </div>
              </TabsContent>

              <TabsContent value="register" className="space-y-4">
                <form onSubmit={handleRegister} className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="firstName">First Name</Label>
                      <div className="relative">
                        <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input
                          id="firstName"
                          placeholder="John"
                          className="pl-10"
                          value={firstName}
                          onChange={(e) => setFirstName(e.target.value)}
                          required
                        />
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="lastName">Last Name</Label>
                      <Input 
                        id="lastName" 
                        placeholder="Doe" 
                        value={lastName}
                        onChange={(e) => setLastName(e.target.value)}
                        required 
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="regEmail">Email</Label>
                    <div className="relative">
                      <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                      <Input
                        id="regEmail"
                        type="email"
                        placeholder="name@example.com"
                        className="pl-10"
                        value={regEmail}
                        onChange={(e) => setRegEmail(e.target.value)}
                        required
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="phone">Phone Number</Label>
                    <div className="relative">
                      <Phone className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                      <Input
                        id="phone"
                        type="tel"
                        placeholder="+971 50 123 4567"
                        className="pl-10"
                        value={phone}
                        onChange={(e) => setPhone(e.target.value)}
                        required
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="referralCode">Referral Code (optional)</Label>
                    <div className="relative">
                      <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                      <Input
                        id="referralCode"
                        placeholder="Broker referral code"
                        className="pl-10"
                        value={referralCode}
                        onChange={(e) => setReferralCode(e.target.value)}
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="regPassword">Password</Label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                      <Input
                        id="regPassword"
                        type={showPassword ? "text" : "password"}
                        placeholder="••••••••"
                        className="pl-10 pr-10"
                        value={regPassword}
                        onChange={(e) => setRegPassword(e.target.value)}
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      >
                        {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  <div className="flex items-start gap-2">
                    <input 
                      type="checkbox" 
                      id="usDisclosure" 
                      className="rounded border-border mt-1" 
                      checked={usDisclosure}
                      onChange={(e) => setUsDisclosure(e.target.checked)}
                      required 
                    />
                    <label htmlFor="usDisclosure" className="text-sm text-muted-foreground">
                      I confirm whether I am a U.S. citizen or U.S. resident and acknowledge that my access to certain investment opportunities may be restricted under applicable U.S. securities regulations (Reg D)
                    </label>
                  </div>

                  <div className="flex items-start gap-2">
                    <input 
                      type="checkbox" 
                      id="terms" 
                      className="rounded border-border mt-1" 
                      checked={terms}
                      onChange={(e) => setTerms(e.target.checked)}
                      required 
                    />
                    <label htmlFor="terms" className="text-sm text-muted-foreground">
                      I agree to the{" "}
                      <Link
                        to="/terms"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary underline"
                      >
                        Terms of Service
                      </Link>{" "}
                      and{" "}
                      <Link
                        to="/privacy"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary underline"
                      >
                        Privacy Policy
                      </Link>
                    </label>
                  </div>

                  <Button type="submit" className="w-full gap-2" disabled={isLoading}>
                    {isLoading ? "Creating account..." : "Create Account"}
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </form>

                <div className="relative">
                  <Separator />
                  <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-card px-2 text-xs text-muted-foreground">
                    or continue with
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <Button 
                    variant="outline" 
                    className="gap-2"
                    onClick={handleGoogleSignIn}
                    disabled={isLoading}
                  >
                    <Chrome className="h-4 w-4" />
                    Google
                  </Button>
                  <Button 
                    variant="outline" 
                    className="gap-2"
                    onClick={handleAppleSignIn}
                    disabled={isLoading}
                  >
                    <Apple className="h-4 w-4" />
                    Apple
                  </Button>
                </div>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        <p className="text-center text-sm text-muted-foreground mt-6">
          By continuing, you acknowledge that you have read and understood our{" "}
          <Link
            to="/risk-disclosure"
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary underline"
          >
            Risk Disclosure
          </Link>
        </p>
      </div>
    </div>
  );
};

export default Auth;
