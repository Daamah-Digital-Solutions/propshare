import { Link, useLocation } from "react-router-dom";
import { Home, Store, PieChart, UserCircle, ArrowLeftRight, Menu } from "lucide-react";
import { cn } from "@/lib/utils";
import { useSidebar } from "@/components/ui/sidebar";

const navItems = [
  { label: "Home", href: "/", icon: Home },
  { label: "Marketplace", href: "/marketplace", icon: Store },
  { label: "Portfolio", href: "/dashboard", icon: PieChart },
  { label: "Account", href: "/settings", icon: UserCircle },
  { label: "P2P", href: "/secondary-market", icon: ArrowLeftRight },
];

const MobileBottomNav = () => {
  const location = useLocation();
  const { toggleSidebar } = useSidebar();

  const isActive = (href: string) => {
    if (href === "/") return location.pathname === "/";
    if (href === "/settings") return location.pathname === "/settings" || location.pathname.startsWith("/account") || location.pathname.startsWith("/settings");
    return location.pathname === href || location.pathname.startsWith(href);
  };

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 lg:hidden bg-background/95 backdrop-blur-lg border-t border-border safe-area-inset-bottom">
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

        {/* More button - opens sidebar */}
        <button
          onClick={toggleSidebar}
          className="flex flex-col items-center justify-center flex-1 h-full gap-0.5 text-muted-foreground hover:text-foreground transition-colors"
        >
          <Menu className="h-5 w-5" />
          <span className="text-[10px] font-medium leading-tight">More</span>
        </button>
      </div>
    </nav>
  );
};

export default MobileBottomNav;
