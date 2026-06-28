import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/contexts/AuthContext";
import { profileApi, authApi, notificationApi, ApiError } from "@/lib/api";
import type { NotificationPreferences as ApiNotificationPreferences } from "@/lib/api";
import { RoleAccessCard } from "@/components/account/RoleAccessCard";
import {
  Settings,
  User,
  Lock,
  Bell,
  Shield,
  Camera,
  Save,
  Loader2,
  CheckCircle,
  AlertTriangle,
  Eye,
  EyeOff,
  Mail,
  Phone,
  Smartphone,
  CreditCard,
  TrendingUp,
  FileText,
  AlertCircle,
} from "lucide-react";

interface ProfileData {
  id: string;
  full_name: string | null;
  email: string | null;
  phone: string | null;
  avatar_url: string | null;
}

interface NotificationPreferences {
  emailInvestmentUpdates: boolean;
  emailReturns: boolean;
  emailNewProperties: boolean;
  emailSecurityAlerts: boolean;
  pushEnabled: boolean;
  pushInvestmentUpdates: boolean;
  pushReturns: boolean;
  smsEnabled: boolean;
  smsSecurityAlerts: boolean;
}

const AccountSettings = () => {
  const { toast } = useToast();
  const navigate = useNavigate();
  const { user, isAuthenticated } = useAuth();
  const emailVerified = !!user?.email_verified;
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  
  // Profile state
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [avatarPreview, setAvatarPreview] = useState<string | null>(null);
  
  // Password state
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  
  // Notification preferences
  const [notifications, setNotifications] = useState<NotificationPreferences>({
    emailInvestmentUpdates: true,
    emailReturns: true,
    emailNewProperties: true,
    emailSecurityAlerts: true,
    pushEnabled: true,
    pushInvestmentUpdates: true,
    pushReturns: true,
    smsEnabled: false,
    smsSecurityAlerts: true,
  });

  useEffect(() => {
    if (!isAuthenticated) {
      navigate("/auth");
      return;
    }
    fetchProfile();
  }, [isAuthenticated, user]);

  const fetchProfile = async () => {
    try {
      const data = await profileApi.get();
      setProfile({
        id: data.id,
        email: data.email,
        full_name: data.full_name,
        phone: data.phone,
        avatar_url: data.avatar_url,
      });
      setFullName(data.full_name || "");
      setPhone(data.phone || "");
      setAvatarPreview(data.avatar_url);
    } catch (error) {
      console.error("Error fetching profile:", error);
    } finally {
      setLoading(false);
    }
    try {
      const prefs = await notificationApi.getPreferences();
      setNotifications((prev) => ({
        ...prev,
        emailInvestmentUpdates: prefs.email_investment_updates,
        emailReturns: prefs.email_returns,
        emailNewProperties: prefs.email_new_properties,
        emailSecurityAlerts: prefs.email_security_alerts,
      }));
    } catch (error) {
      console.error("Error fetching notification preferences:", error);
    }
  };

  // Only the email channels we actually deliver are persisted. push/sms toggles are
  // honest-disabled (no delivery mechanism) and never sent to the server.
  const EMAIL_PREF_KEYS: Partial<Record<keyof NotificationPreferences, keyof ApiNotificationPreferences>> =
    {
      emailInvestmentUpdates: "email_investment_updates",
      emailReturns: "email_returns",
      emailNewProperties: "email_new_properties",
      emailSecurityAlerts: "email_security_alerts",
    };

  const handleAvatarChange = () => {
    // Avatar upload moves onto the app storage seam (a Phase-1 follow-up once the
    // bucket is configured). Honest placeholder — no fake success.
    toast({
      title: "Avatar upload coming soon",
      description: "Profile photo uploads will be enabled shortly.",
    });
  };

  const handleProfileSave = async () => {
    setSaving(true);
    try {
      await profileApi.update({ full_name: fullName, phone });
      toast({ title: "Profile Updated", description: "Your profile has been saved successfully." });
      fetchProfile();
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "Failed to save profile. Please try again.";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setSaving(false);
    }
  };

  const handlePasswordChange = async () => {
    if (newPassword !== confirmPassword) {
      toast({
        title: "Passwords don't match",
        description: "Please make sure your new passwords match.",
        variant: "destructive",
      });
      return;
    }

    if (newPassword.length < 8) {
      toast({
        title: "Password too short",
        description: "Password must be at least 8 characters long.",
        variant: "destructive",
      });
      return;
    }

    setChangingPassword(true);
    try {
      await authApi.changePassword(currentPassword, newPassword);
      toast({
        title: "Password Changed",
        description: "Your password has been updated successfully.",
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (error) {
      const message =
        error instanceof ApiError ? error.message : "Failed to change password. Please try again.";
      toast({ title: "Error", description: message, variant: "destructive" });
    } finally {
      setChangingPassword(false);
    }
  };

  const handleNotificationChange = async (key: keyof NotificationPreferences, value: boolean) => {
    setNotifications((prev) => ({ ...prev, [key]: value }));
    const apiKey = EMAIL_PREF_KEYS[key];
    if (!apiKey) return; // push/sms — disabled, not a real channel, never persisted
    try {
      await notificationApi.updatePreferences({ [apiKey]: value });
      toast({ title: "Preferences saved" });
    } catch (error) {
      setNotifications((prev) => ({ ...prev, [key]: !value })); // revert on failure
      const message = error instanceof ApiError ? error.message : "Couldn't save preferences.";
      toast({ title: "Error", description: message, variant: "destructive" });
    }
  };

  const getInitials = (name: string | null) => {
    if (!name) return "U";
    return name
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
  };

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-4xl flex items-center justify-center min-h-[60vh]">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      {/* Page Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
            <Settings className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-foreground">Account Settings</h1>
            <p className="text-muted-foreground">Manage your profile, security, and preferences</p>
          </div>
        </div>
      </div>

      <Tabs defaultValue="profile" className="space-y-6">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="profile" className="gap-2">
            <User className="h-4 w-4" />
            Profile
          </TabsTrigger>
          <TabsTrigger value="security" className="gap-2">
            <Lock className="h-4 w-4" />
            Security
          </TabsTrigger>
          <TabsTrigger value="notifications" className="gap-2">
            <Bell className="h-4 w-4" />
            Notifications
          </TabsTrigger>
        </TabsList>

        {/* Profile Tab */}
        <TabsContent value="profile" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Profile Information</CardTitle>
              <CardDescription>Update your personal details and profile picture</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Avatar Section */}
              <div className="flex items-center gap-6">
                <div className="relative">
                  <Avatar className="h-24 w-24">
                    <AvatarImage src={avatarPreview || undefined} />
                    <AvatarFallback className="text-2xl bg-primary/10 text-primary">
                      {getInitials(fullName || profile?.full_name)}
                    </AvatarFallback>
                  </Avatar>
                  <label
                    htmlFor="avatar-upload"
                    className="absolute bottom-0 right-0 w-8 h-8 bg-primary rounded-full flex items-center justify-center cursor-pointer hover:bg-primary/90 transition-colors"
                  >
                    <Camera className="h-4 w-4 text-primary-foreground" />
                    <input
                      id="avatar-upload"
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={handleAvatarChange}
                    />
                  </label>
                </div>
                <div>
                  <h3 className="font-medium text-foreground">{fullName || "Your Name"}</h3>
                  <p className="text-sm text-muted-foreground">{profile?.email}</p>
                </div>
              </div>

              <Separator />

              {/* Form Fields */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="space-y-2">
                  <Label htmlFor="fullName">Full Name</Label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="fullName"
                      placeholder="Enter your full name"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      className="pl-10"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="email">Email Address</Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="email"
                      type="email"
                      value={profile?.email || ""}
                      disabled
                      className="pl-10 bg-muted"
                    />
                  </div>
                  <p className="text-xs text-muted-foreground">Email cannot be changed</p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="phone">Phone Number</Label>
                  <div className="relative">
                    <Phone className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      id="phone"
                      type="tel"
                      placeholder="+971 50 123 4567"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      className="pl-10"
                    />
                  </div>
                </div>
              </div>

              <div className="flex justify-end">
                <Button onClick={handleProfileSave} disabled={saving}>
                  {saving ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save className="h-4 w-4 mr-2" />
                      Save Changes
                    </>
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Roles & Access (self-serve role acquisition — D12) */}
          <RoleAccessCard />

          {/* KYC Status Card */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield className="h-5 w-5" />
                Verification Status
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-amber-500/10 flex items-center justify-center">
                    <AlertTriangle className="h-5 w-5 text-amber-500" />
                  </div>
                  <div>
                    <p className="font-medium text-foreground">KYC Verification</p>
                    <p className="text-sm text-muted-foreground">Complete verification to unlock all features</p>
                  </div>
                </div>
                <Button variant="outline" onClick={() => navigate("/kyc")}>
                  Complete KYC
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Security Tab */}
        <TabsContent value="security" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Change Password</CardTitle>
              <CardDescription>Update your password to keep your account secure</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="currentPassword">Current Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="currentPassword"
                    type={showCurrentPassword ? "text" : "password"}
                    placeholder="Enter current password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    className="pl-10 pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showCurrentPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="newPassword">New Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="newPassword"
                    type={showNewPassword ? "text" : "password"}
                    placeholder="Enter new password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="pl-10 pr-10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPassword(!showNewPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showNewPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                <p className="text-xs text-muted-foreground">Minimum 8 characters</p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirmPassword">Confirm New Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="confirmPassword"
                    type="password"
                    placeholder="Confirm new password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="pl-10"
                  />
                </div>
              </div>

              <Button
                onClick={handlePasswordChange}
                disabled={changingPassword || !newPassword || !confirmPassword}
              >
                {changingPassword ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Changing...
                  </>
                ) : (
                  <>
                    <Lock className="h-4 w-4 mr-2" />
                    Change Password
                  </>
                )}
              </Button>
            </CardContent>
          </Card>

          {/* Security Overview */}
          <Card>
            <CardHeader>
              <CardTitle>Security Overview</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg">
                <div className="flex items-center gap-3">
                  {emailVerified ? (
                    <CheckCircle className="h-5 w-5 text-green-500" />
                  ) : (
                    <AlertCircle className="h-5 w-5 text-amber-500" />
                  )}
                  <div>
                    <p className="font-medium text-foreground">Email {emailVerified ? "Verified" : "Not Verified"}</p>
                    <p className="text-sm text-muted-foreground">{profile?.email}</p>
                  </div>
                </div>
                <Badge className={emailVerified ? "bg-green-500" : "bg-amber-500"}>
                  {emailVerified ? "Verified" : "Pending"}
                </Badge>
              </div>

              <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg opacity-75">
                <div className="flex items-center gap-3">
                  <Smartphone className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium text-foreground">Two-Factor Authentication</p>
                    <p className="text-sm text-muted-foreground">Not available yet</p>
                  </div>
                </div>
                <Button variant="outline" size="sm" disabled>Enable</Button>
              </div>

              <div className="flex items-center justify-between p-4 bg-muted/50 rounded-lg opacity-75">
                <div className="flex items-center gap-3">
                  <AlertCircle className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium text-foreground">Active Sessions</p>
                    <p className="text-sm text-muted-foreground">Not available yet</p>
                  </div>
                </div>
                <Button variant="outline" size="sm" disabled>View</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Notifications Tab */}
        <TabsContent value="notifications" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Mail className="h-5 w-5" />
                Email Notifications
              </CardTitle>
              <CardDescription>Choose what emails you want to receive</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <TrendingUp className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium text-foreground">Investment Updates</p>
                    <p className="text-sm text-muted-foreground">Status changes and milestones</p>
                  </div>
                </div>
                <Switch
                  checked={notifications.emailInvestmentUpdates}
                  onCheckedChange={(v) => handleNotificationChange("emailInvestmentUpdates", v)}
                />
              </div>

              <Separator />

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <CreditCard className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium text-foreground">Returns & Distributions</p>
                    <p className="text-sm text-muted-foreground">Rental income and profit distributions</p>
                  </div>
                </div>
                <Switch
                  checked={notifications.emailReturns}
                  onCheckedChange={(v) => handleNotificationChange("emailReturns", v)}
                />
              </div>

              <Separator />

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <FileText className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium text-foreground">New Properties</p>
                    <p className="text-sm text-muted-foreground">Get notified about new investment opportunities</p>
                  </div>
                </div>
                <Switch
                  checked={notifications.emailNewProperties}
                  onCheckedChange={(v) => handleNotificationChange("emailNewProperties", v)}
                />
              </div>

              <Separator />

              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Shield className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium text-foreground">Security Alerts</p>
                    <p className="text-sm text-muted-foreground">Login attempts and security changes</p>
                  </div>
                </div>
                <Switch
                  checked={notifications.emailSecurityAlerts}
                  onCheckedChange={(v) => handleNotificationChange("emailSecurityAlerts", v)}
                />
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Smartphone className="h-5 w-5" />
                Push Notifications
                <Badge variant="outline" className="ml-1 text-xs">Not available yet</Badge>
              </CardTitle>
              <CardDescription>
                Push notifications are not available yet — you'll receive these in-app and by email.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Bell className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium text-foreground">Enable Push Notifications</p>
                    <p className="text-sm text-muted-foreground">Receive alerts on your browser or mobile</p>
                  </div>
                </div>
                <Switch checked={false} disabled />
              </div>

              {notifications.pushEnabled && (
                <>
                  <Separator />
                  <div className="flex items-center justify-between pl-8">
                    <div>
                      <p className="font-medium text-foreground">Investment Updates</p>
                    </div>
                    <Switch
                      checked={notifications.pushInvestmentUpdates}
                      onCheckedChange={(v) => handleNotificationChange("pushInvestmentUpdates", v)}
                    />
                  </div>
                  <div className="flex items-center justify-between pl-8">
                    <div>
                      <p className="font-medium text-foreground">Returns & Distributions</p>
                    </div>
                    <Switch
                      checked={notifications.pushReturns}
                      onCheckedChange={(v) => handleNotificationChange("pushReturns", v)}
                    />
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Phone className="h-5 w-5" />
                SMS Notifications
                <Badge variant="outline" className="ml-1 text-xs">Not available yet</Badge>
              </CardTitle>
              <CardDescription>
                SMS notifications are not available yet — you'll receive these in-app and by email.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <Phone className="h-5 w-5 text-muted-foreground" />
                  <div>
                    <p className="font-medium text-foreground">Enable SMS Notifications</p>
                    <p className="text-sm text-muted-foreground">Standard messaging rates may apply</p>
                  </div>
                </div>
                <Switch checked={false} disabled />
              </div>

              {notifications.smsEnabled && (
                <>
                  <Separator />
                  <div className="flex items-center justify-between pl-8">
                    <div>
                      <p className="font-medium text-foreground">Security Alerts Only</p>
                      <p className="text-sm text-muted-foreground">Login attempts and password changes</p>
                    </div>
                    <Switch
                      checked={notifications.smsSecurityAlerts}
                      onCheckedChange={(v) => handleNotificationChange("smsSecurityAlerts", v)}
                    />
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default AccountSettings;
