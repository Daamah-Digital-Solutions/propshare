import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Home, Building2, LayoutDashboard, UserCircle, ArrowRightLeft, Menu, TrendingUp, Droplets } from "lucide-react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import { useSidebar } from "@/components/ui/sidebar";
import { useAuth } from "@/contexts/AuthContext";
import { roleHome } from "@/lib/roles";

const MobileBottomNav = () => {
  const location = useLocation();
  const { toggleSidebar } = useSidebar();
  const { userRole } = useAuth();
  // Six places, in this order (client, 2026-11-11): Home, Properties, Dashboard, Account,
  // Trade, More. The bar is mirrored with the site in Arabic, so it reads right to left there.
  // Dashboard opens the dashboard of the role in use (an LP / broker / owner cannot open
  // /dashboard); Trade is where units are bought and sold and offers are managed.
  const navItems = [
    { label: "Home", href: "/", icon: Home },
    { label: "Properties", href: "/marketplace", icon: Building2 },
    { label: "Dashboard", href: roleHome(userRole), icon: LayoutDashboard },
    { label: "Account", href: "/settings", icon: UserCircle },
  ];

  // Trade opens the choice between the two markets (client, 2026-11-12, as on Capimax BRX): the
  // liquidity provider market must be as easy to find as the secondary market.
  const markets = [
    {
      href: "/secondary-market",
      label: "Secondary Market",
      desc: "Buy and sell units with other investors and manage your offers.",
      icon: TrendingUp,
    },
    {
      href: "/liquidity-market",
      label: "Liquidity Provider Market",
      desc: "Sell your units instantly to a liquidity provider at the platform price.",
      icon: Droplets,
    },
  ];
  const [tradeOpen, setTradeOpen] = useState(false);
  const navigate = useNavigate();
  const onMarket = (href: string) => location.pathname.startsWith(href);
  const tradeActive = markets.some((m) => onMarket(m.href));

  const isActive = (href: string) => {
    if (href === "/") return location.pathname === "/";
    if (href === "/settings") return location.pathname === "/settings" || location.pathname.startsWith("/account") || location.pathname.startsWith("/settings");
    return location.pathname === href || location.pathname.startsWith(href);
  };

  return (
    <nav className="fixed bottom-0 inset-x-0 z-50 lg:hidden bg-background/95 backdrop-blur-lg border-t border-border safe-area-inset-bottom">
      <div className="flex items-center justify-around h-16 px-1">
        {navItems.map((item) => {
          const active = isActive(item.href);
          return (
            <Link
              key={item.label}
              to={item.href}
              className={cn(
                "flex flex-col items-center justify-center flex-1 h-full gap-0.5 transition-colors relative",
                active
                  ? "text-primary"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              <item.icon
                className={cn(
                  "h-5 w-5 transition-transform",
                  active && "scale-110"
                )}
              />
              <span
                className={cn(
                  "text-[10px] font-medium leading-tight",
                  active && "font-semibold"
                )}
              >
                {item.label}
              </span>
              {active && (
                <div className="absolute bottom-1 w-6 h-0.5 bg-primary rounded-full" />
              )}
            </Link>
          );
        })}

        <button
          type="button"
          onClick={() => setTradeOpen(true)}
          aria-haspopup="dialog"
          aria-expanded={tradeOpen}
          data-testid="nav-trade"
          className={cn(
            "flex flex-col items-center justify-center flex-1 h-full gap-0.5 transition-colors relative",
            tradeActive ? "text-primary" : "text-muted-foreground hover:text-foreground"
          )}
        >
          <ArrowRightLeft className={cn("h-5 w-5 transition-transform", tradeActive && "scale-110")} />
          <span className={cn("text-[10px] font-medium leading-tight", tradeActive && "font-semibold")}>Trade</span>
          {tradeActive && <div className="absolute bottom-1 w-6 h-0.5 bg-primary rounded-full" />}
        </button>

        {/* More button - opens sidebar */}
        <button
          onClick={toggleSidebar}
          className="flex flex-col items-center justify-center flex-1 h-full gap-0.5 text-muted-foreground hover:text-foreground transition-colors"
        >
          <Menu className="h-5 w-5" />
          <span className="text-[10px] font-medium leading-tight">More</span>
        </button>
      </div>

      {/* Trade: choose a market */}
      <Sheet open={tradeOpen} onOpenChange={setTradeOpen}>
        {/* above the PropShare AI button (z-60), which would otherwise cover a card */}
        <SheetContent
          side="bottom"
          className="z-[70] rounded-t-2xl pb-8 lg:hidden"
          overlayClassName="z-[70]"
          data-testid="trade-sheet"
        >
          <SheetHeader>
            <SheetTitle className="text-start">Trade</SheetTitle>
            <SheetDescription className="sr-only">Choose a market</SheetDescription>
          </SheetHeader>
          <div className="grid grid-cols-2 gap-3 mt-4">
            {markets.map((m) => {
              const current = onMarket(m.href);
              return (
                <button
                  key={m.href}
                  type="button"
                  aria-current={current ? "page" : undefined}
                  onClick={() => {
                    setTradeOpen(false);
                    navigate(m.href);
                  }}
                  className={cn(
                    "flex flex-col items-center gap-2 p-4 rounded-xl border text-center transition-colors",
                    current ? "border-primary bg-primary/10" : "border-border bg-muted/50 hover:bg-muted"
                  )}
                >
                  <m.icon className="w-6 h-6 text-primary" />
                  <span className="text-sm font-semibold text-foreground">{m.label}</span>
                  <span className="text-[11px] leading-snug text-muted-foreground">{m.desc}</span>
                </button>
              );
            })}
          </div>
        </SheetContent>
      </Sheet>
    </nav>
  );
};

export default MobileBottomNav;
