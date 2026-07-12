import { useState, useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { useAuth, UserRole } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import {
  Home,
  Store,
  Building2,
  HardHat,
  ArrowLeftRight,
  Users,
  Info,
  HelpCircle,
  Shield,
  FileText,
  Scale,
  AlertTriangle,
  BookOpen,
  HeadphonesIcon,
  LogIn,
  LayoutDashboard,
  Briefcase,
  Wallet,
  PiggyBank,
  BarChart3,
  FolderOpen,
  Bell,
  Settings,
  LogOut,
  Calendar,
  TrendingUp,
  Plus,
  Download,
  Landmark,
  Bitcoin,
  Handshake,
  ChevronDown,
  ChevronRight,
  Globe,
  Sun,
  Moon,
  Smartphone,
  CreditCard,
  UserCheck,
  Droplets,
  Layers,
} from "lucide-react";

interface NavItem {
  title: string;
  url: string;
  icon: React.ElementType;
  children?: NavItem[];
}

interface NavSection {
  label: string;
  items: NavItem[];
  defaultOpen?: boolean;
}

const publicNavigation: NavSection[] = [
  {
    label: "General",
    defaultOpen: true,
    items: [
      { title: "Home", url: "/", icon: Home },
      { 
        title: "Marketplace", 
        url: "/marketplace", 
        icon: Store,
        children: [
          { title: "Browse Properties", url: "/marketplace", icon: Building2 },
          { title: "Ready Properties", url: "/marketplace?type=ready", icon: Building2 },
          { title: "Under Construction", url: "/marketplace?type=construction", icon: HardHat },
        ]
      },
      { title: "Property Types", url: "/property-types", icon: Layers },
      { title: "Secondary Market", url: "/secondary-market", icon: ArrowLeftRight },
      { title: "Liquidity Provider Market", url: "/liquidity-market", icon: Droplets },
      { title: "Exit Mechanisms", url: "/exit-mechanisms", icon: LogOut },
      { title: "Partners", url: "/partners", icon: Users },
    ],
  },
  {
    label: "About Platform",
    items: [
      { title: "About Capimax PropShare", url: "/about-capimax-propshare", icon: Info },
      { title: "How It Works", url: "/how-it-works", icon: HelpCircle },
      { title: "SPV Model", url: "/spv-model", icon: Shield },
      { title: "Fees", url: "/fees", icon: CreditCard },
    ],
  },
  {
    label: "Legal & Compliance",
    items: [
      { title: "Terms & Conditions", url: "/terms", icon: FileText },
      { title: "Privacy Policy", url: "/privacy", icon: Shield },
      { title: "Risk Disclosure", url: "/risk-disclosure", icon: AlertTriangle },
      { title: "Disclaimer", url: "/disclaimer", icon: BookOpen },
      { title: "Platform Rules", url: "/platform-rules", icon: Scale },
    ],
  },
  {
    label: "Help",
    items: [
      { title: "FAQ", url: "/faq", icon: HelpCircle },
      { title: "Support", url: "/support", icon: HeadphonesIcon },
      { title: "Login / Register", url: "/auth", icon: LogIn },
    ],
  },
];

const investorNavigation: NavSection[] = [
  {
    label: "Investor",
    defaultOpen: true,
    items: [
      { title: "Home", url: "/", icon: Home },
      { title: "Dashboard", url: "/dashboard", icon: LayoutDashboard },
      { title: "Browse Marketplace", url: "/marketplace", icon: Store },
      { title: "New Investment", url: "/marketplace", icon: Plus },
      {
        title: "My Portfolio",
        url: "/portfolio", 
        icon: Briefcase,
        children: [
          { title: "My Investments", url: "/dashboard?tab=investments", icon: Building2 },
          { title: "Installments", url: "/dashboard?tab=installments", icon: Calendar },
          { title: "Returns & Distributions", url: "/dashboard?tab=returns", icon: TrendingUp },
        ]
      },
      { title: "Reports & Analytics", url: "/reports", icon: BarChart3 },
      { title: "Documents Center", url: "/dashboard?tab=documents", icon: FolderOpen },
      { title: "Wallet", url: "/dashboard?tab=wallet", icon: Wallet },
      { title: "Property Types", url: "/property-types", icon: Layers },
      { title: "Secondary Market", url: "/secondary-market", icon: ArrowLeftRight },
      { title: "Liquidity Provider Market", url: "/liquidity-market", icon: Droplets },
      { title: "Exit Mechanisms", url: "/exit-mechanisms", icon: LogOut },
    ],
  },
  {
    label: "Account",
    items: [
      { title: "KYC Verification", url: "/kyc", icon: UserCheck },
      { title: "Notifications", url: "/notifications", icon: Bell },
      { title: "Support", url: "/support", icon: HeadphonesIcon },
      { title: "Account Settings", url: "/settings", icon: Settings },
    ],
  },
];

const ownerNavigation: NavSection[] = [
  {
    label: "Property Owner",
    defaultOpen: true,
    items: [
      { title: "Owner Dashboard", url: "/owner-dashboard", icon: LayoutDashboard },
      { title: "List a Property", url: "/owner-dashboard?tab=list-property", icon: Plus },
      { title: "My Assets", url: "/owner-dashboard?tab=properties", icon: Building2 },
      { title: "Performance Reports", url: "/owner-dashboard?tab=overview", icon: BarChart3 },
      { title: "Financial Analytics", url: "/owner-dashboard?tab=financials", icon: TrendingUp },
      { title: "Documents", url: "/owner-dashboard?tab=documents", icon: FolderOpen },
      { title: "Wallet", url: "/owner-wallet", icon: Wallet },
      { title: "Property Types", url: "/property-types", icon: Layers },
      { title: "Secondary Market", url: "/secondary-market", icon: ArrowLeftRight },
      { title: "Liquidity Provider Market", url: "/liquidity-market", icon: Droplets },
      { title: "Exit Mechanisms", url: "/exit-mechanisms", icon: LogOut },
    ],
  },
  {
    label: "Account",
    items: [
      { title: "KYC Verification", url: "/kyc", icon: UserCheck },
      { title: "Notifications", url: "/notifications", icon: Bell },
      { title: "Account Settings", url: "/settings", icon: Settings },
    ],
  },
];

const liquidityProviderNavigation: NavSection[] = [
  {
    label: "Liquidity Provider",
    defaultOpen: true,
    items: [
      { title: "LP Dashboard", url: "/liquidity-dashboard", icon: LayoutDashboard },
      { title: "Liquidity Provider Market", url: "/liquidity-market", icon: Droplets },
      { title: "Property Types", url: "/property-types", icon: Layers },
      { title: "Exit Mechanisms", url: "/exit-mechanisms", icon: LogOut },
      { title: "Provide Liquidity", url: "/provide-liquidity", icon: PiggyBank },
      { title: "Backed Assets", url: "/backed-assets", icon: Building2 },
      { title: "Returns & Analytics", url: "/lp-analytics", icon: TrendingUp },
      { title: "Reports", url: "/lp-reports", icon: BarChart3 },
      { title: "Documents", url: "/lp-documents", icon: FolderOpen },
      { 
        title: "Wallet", 
        url: "/lp-wallet", 
        icon: Wallet,
        children: [
          { title: "Bank Withdrawals", url: "/lp-wallet?method=bank", icon: Landmark },
          { title: "Crypto Withdrawals", url: "/lp-wallet?method=crypto", icon: Bitcoin },
        ]
      },
    ],
  },
  {
    label: "Account",
    items: [
      { title: "KYC Verification", url: "/kyc", icon: UserCheck },
      { title: "Notifications", url: "/notifications", icon: Bell },
      { title: "Account Settings", url: "/settings", icon: Settings },
    ],
  },
];

const brokerNavigation: NavSection[] = [
  {
    label: "Broker",
    defaultOpen: true,
    items: [
      { title: "Broker Dashboard", url: "/broker-dashboard", icon: LayoutDashboard },
      { title: "Referrals", url: "/broker-dashboard?tab=referrals", icon: Handshake },
      { title: "Commissions", url: "/broker-dashboard?tab=commissions", icon: PiggyBank },
      { title: "Wallet", url: "/broker-dashboard?tab=wallet", icon: Wallet },
      { title: "Property Types", url: "/property-types", icon: Layers },
      { title: "Secondary Market", url: "/secondary-market", icon: ArrowLeftRight },
      { title: "Liquidity Provider Market", url: "/liquidity-market", icon: Droplets },
      { title: "Exit Mechanisms", url: "/exit-mechanisms", icon: LogOut },
    ],
  },
  {
    label: "Account",
    items: [
      { title: "KYC Verification", url: "/kyc", icon: UserCheck },
      { title: "Notifications", url: "/notifications", icon: Bell },
      { title: "Account Settings", url: "/settings", icon: Settings },
    ],
  },
];

const developerNavigation: NavSection[] = [
  {
    label: "Developer",
    defaultOpen: true,
    items: [
      { title: "Developer Dashboard", url: "/developer-dashboard", icon: LayoutDashboard },
      { title: "Projects", url: "/developer-dashboard?tab=projects", icon: HardHat },
      { title: "Funding", url: "/developer-dashboard?tab=funding", icon: TrendingUp },
      { title: "Milestones", url: "/developer-dashboard?tab=milestones", icon: Calendar },
      { title: "Investors", url: "/developer-dashboard?tab=investors", icon: Users },
      { title: "Property Types", url: "/property-types", icon: Layers },
      { title: "Secondary Market", url: "/secondary-market", icon: ArrowLeftRight },
      { title: "Liquidity Provider Market", url: "/liquidity-market", icon: Droplets },
      { title: "Exit Mechanisms", url: "/exit-mechanisms", icon: LogOut },
    ],
  },
  {
    label: "Account",
    items: [
      { title: "KYC Verification", url: "/kyc", icon: UserCheck },
      { title: "Notifications", url: "/notifications", icon: Bell },
      { title: "Account Settings", url: "/settings", icon: Settings },
    ],
  },
];

const getNavigationForRole = (role: UserRole): NavSection[] => {
  switch (role) {
    case "investor":
      return [...investorNavigation, ...publicNavigation.slice(1)];
    case "owner":
      return [...ownerNavigation, ...publicNavigation.slice(1)];
    case "broker":
      return [...brokerNavigation, ...publicNavigation.slice(1)];
    case "liquidity_provider":
      return [...liquidityProviderNavigation, ...publicNavigation.slice(1)];
    default:
      // guest + admin (admin console arrives in Phase 13) fall back to public nav.
      return publicNavigation;
  }
};

// Views a visitor can explore from the always-on switcher. This is a CLIENT-SIDE preview of
// each role's navigation so anyone (guests included) can see the whole platform; the backend
// still enforces real roles + KYC on every action, so previewing never grants access.
const EXPLORABLE_VIEWS: { value: UserRole; label: string }[] = [
  { value: "guest", label: "Guest" },
  { value: "investor", label: "Investor" },
  { value: "owner", label: "Property Owner" },
  { value: "broker", label: "Broker" },
  { value: "liquidity_provider", label: "Liquidity Provider" },
];

export function AppSidebar() {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const location = useLocation();
  const { userRole, authorizedRoles, switchActiveRole, isAuthenticated, signOut } = useAuth();
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  // Which role's view the sidebar shows. Defaults to (and follows) the real active role, but
  // anyone can switch it to preview another role's navigation via the switcher below.
  const [previewRole, setPreviewRole] = useState<UserRole>(userRole);
  useEffect(() => {
    setPreviewRole(EXPLORABLE_VIEWS.some((v) => v.value === userRole) ? userRole : "guest");
  }, [userRole]);

  const handleViewChange = (role: UserRole) => {
    setPreviewRole(role);
    // If the signed-in user genuinely holds this role, also switch their REAL active role so
    // their dashboards load real data; otherwise this is purely a navigation preview.
    if (isAuthenticated && role !== "guest" && role !== userRole && authorizedRoles.includes(role)) {
      void switchActiveRole(role);
    }
  };

  const navigation = getNavigationForRole(previewRole);

  useEffect(() => {
    const isDark = document.documentElement.classList.contains("dark");
    setIsDarkMode(isDark);
  }, []);

  const toggleDarkMode = () => {
    setIsDarkMode(!isDarkMode);
    document.documentElement.classList.toggle("dark");
  };

  const isActive = (url: string) => {
    if (url === "/") return location.pathname === "/";
    return location.pathname.startsWith(url.split("?")[0]);
  };

  const toggleGroup = (label: string) => {
    setOpenGroups(prev => ({ ...prev, [label]: !prev[label] }));
  };

  const handleInstallPWA = () => {
    // PWA install logic would go here
    alert("Install Capimax PropShare App");
  };

  return (
    <Sidebar 
      className={cn(
        "border-r border-border bg-card transition-all duration-300",
        collapsed ? "w-16" : "w-64"
      )}
      collapsible="icon"
    >
      {/* Header */}
      <SidebarHeader className="border-b border-border p-4">
        <Link to="/" className="flex items-center">
          {collapsed ? (
            <img src="/icon-192.png" alt="CapiMax PropShare" className="w-9 h-9 mx-auto" />
          ) : (
            <img src="/capimax-logo.png" alt="CapiMax PropShare" className="h-8 w-auto" />
          )}
        </Link>
      </SidebarHeader>

      {/* View switcher — ALWAYS visible so anyone (guests included) can explore every role's
          view of the platform. This is a client-side navigation preview; the backend still
          enforces real roles + KYC on every action, so it never grants access and never
          interferes with signing up / logging in. When the signed-in user actually holds the
          picked role, we also switch their real active role so dashboards load their data. */}
      {!collapsed && (
        <div className="px-4 py-3 border-b border-border">
          <span className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
            Explore as
          </span>
          <Select value={previewRole} onValueChange={(v) => handleViewChange(v as UserRole)}>
            <SelectTrigger className="w-full h-9 text-xs mt-1">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {EXPLORABLE_VIEWS.map((view) => (
                <SelectItem key={view.value} value={view.value}>
                  {view.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Navigation Content */}
      <SidebarContent className="px-2 py-2">
        {navigation.map((section) => (
          <SidebarGroup key={section.label}>
            {!collapsed && (
              <SidebarGroupLabel className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-3 py-2">
                {section.label}
              </SidebarGroupLabel>
            )}
            <SidebarGroupContent>
              <SidebarMenu>
                {section.items.map((item) => (
                  <SidebarMenuItem key={item.title}>
                    {item.children ? (
                      <Collapsible
                        open={openGroups[item.title] ?? section.defaultOpen}
                        onOpenChange={() => toggleGroup(item.title)}
                      >
                        <CollapsibleTrigger asChild>
                          <SidebarMenuButton
                            className={cn(
                              "w-full justify-between",
                              isActive(item.url) && "bg-primary/10 text-primary"
                            )}
                          >
                            <div className="flex items-center gap-3">
                              <item.icon className="h-4 w-4 flex-shrink-0" />
                              {!collapsed && <span className="text-sm">{item.title}</span>}
                            </div>
                            {!collapsed && (
                              openGroups[item.title] ? (
                                <ChevronDown className="h-4 w-4" />
                              ) : (
                                <ChevronRight className="h-4 w-4" />
                              )
                            )}
                          </SidebarMenuButton>
                        </CollapsibleTrigger>
                        {!collapsed && (
                          <CollapsibleContent className="pl-7 space-y-1 mt-1">
                            {item.children.map((child) => (
                              <NavLink
                                key={child.title}
                                to={child.url}
                                className={({ isActive }) =>
                                  cn(
                                    "flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors",
                                    isActive
                                      ? "bg-primary/10 text-primary font-medium"
                                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                                  )
                                }
                              >
                                <child.icon className="h-4 w-4" />
                                <span>{child.title}</span>
                              </NavLink>
                            ))}
                          </CollapsibleContent>
                        )}
                      </Collapsible>
                    ) : (
                      <SidebarMenuButton asChild>
                        <NavLink
                          to={item.url}
                          className={({ isActive }) =>
                            cn(
                              "flex items-center gap-3 px-3 py-2 rounded-md transition-colors",
                              isActive
                                ? "bg-primary/10 text-primary font-medium"
                                : "text-muted-foreground hover:bg-muted hover:text-foreground"
                            )
                          }
                        >
                          <item.icon className="h-4 w-4 flex-shrink-0" />
                          {!collapsed && <span className="text-sm">{item.title}</span>}
                        </NavLink>
                      </SidebarMenuButton>
                    )}
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}

        {/* Logout for authenticated users */}
        {isAuthenticated && (
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    onClick={async () => {
                      try {
                        await signOut();
                      } catch (e) {
                        console.error("Logout failed", e);
                      }
                    }}
                    className="text-destructive hover:bg-destructive/10"
                  >
                    <LogOut className="h-4 w-4 flex-shrink-0" />
                    {!collapsed && <span className="text-sm ml-3">Logout</span>}
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>

      {/* Footer */}
      <SidebarFooter className="border-t border-border p-3 space-y-3">
        {/* Language Switcher */}
        {!collapsed && (
          <div className="flex items-center justify-between px-2">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Globe className="h-4 w-4" />
              <span>Language</span>
            </div>
            <Select defaultValue="en">
              <SelectTrigger className="w-20 h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="en">EN</SelectItem>
                <SelectItem value="ar">AR</SelectItem>
              </SelectContent>
            </Select>
          </div>
        )}

        {/* Dark Mode Toggle */}
        <div className={cn(
          "flex items-center px-2",
          collapsed ? "justify-center" : "justify-between"
        )}>
          {!collapsed && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              {isDarkMode ? <Moon className="h-4 w-4" /> : <Sun className="h-4 w-4" />}
              <span>{isDarkMode ? "Dark Mode" : "Light Mode"}</span>
            </div>
          )}
          <Switch
            checked={isDarkMode}
            onCheckedChange={toggleDarkMode}
            className="data-[state=checked]:bg-primary"
          />
        </div>

        {/* PWA Install */}
        {!collapsed && (
          <Button
            variant="outline"
            size="sm"
            className="w-full gap-2 text-xs"
            onClick={handleInstallPWA}
          >
            <Smartphone className="h-4 w-4" />
            Install CapimaxPropShare App
          </Button>
        )}
      </SidebarFooter>
    </Sidebar>
  );
}
