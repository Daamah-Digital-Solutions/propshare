import { ReactNode, useState } from "react";
import { SidebarProvider, SidebarTrigger, SidebarInset } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/layout/AppSidebar";
import { BrandMark } from "@/components/layout/BrandMark";
import MobileBottomNav from "@/components/layout/MobileBottomNav";
import { Button } from "@/components/ui/button";
import { Bell, Search, User } from "lucide-react";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/contexts/AuthContext";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { notificationApi } from "@/lib/api";

interface MainLayoutProps {
  children: ReactNode;
}

export function MainLayout({ children }: MainLayoutProps) {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const { data: unread } = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: notificationApi.unreadCount,
    enabled: isAuthenticated,
    refetchInterval: 60000,
  });
  const unreadCount = unread?.count ?? 0;
  const [search, setSearch] = useState("");

  const submitSearch = () => {
    const q = search.trim();
    navigate(q ? `/marketplace?q=${encodeURIComponent(q)}` : "/marketplace");
  };

  return (
    <SidebarProvider defaultOpen={true}>
      <div className="min-h-screen flex w-full bg-background">
        <AppSidebar />
        <SidebarInset className="flex-1 flex flex-col">
          {/* Top Header */}
          <header className="h-14 border-b border-border bg-card/50 backdrop-blur-sm sticky top-0 z-40 flex items-center justify-between px-3 sm:px-4 gap-2 sm:gap-4 overflow-hidden">
            <div className="flex items-center gap-2 sm:gap-3 min-w-0">
              <SidebarTrigger className="h-9 w-9" />
              
              {/* Platform Name - Always visible, name rendered as crisp text */}
              <BrandMark />

              <div className="hidden lg:flex relative ml-4">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search properties..."
                  className="pl-10 w-64 h-9"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") submitSearch();
                  }}
                  aria-label="Search properties"
                />
              </div>
            </div>

            <div className="flex items-center gap-2">
              {isAuthenticated ? (
                <>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="relative"
                    aria-label="Notifications"
                    onClick={() => navigate("/notifications")}
                  >
                    <Bell className="h-5 w-5" />
                    {unreadCount > 0 && (
                      <span className="absolute -top-1 -right-1 h-4 min-w-4 px-1 bg-primary text-primary-foreground text-xs rounded-full flex items-center justify-center">
                        {unreadCount > 9 ? "9+" : unreadCount}
                      </span>
                    )}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Account settings"
                    onClick={() => navigate("/settings")}
                  >
                    <User className="h-5 w-5" />
                  </Button>
                </>
              ) : (
                <div className="flex items-center gap-2">
                  {/* On phones only one CTA fits beside the brand — the ghost link is hidden. */}
                  <Link to="/auth" className="hidden sm:block">
                    <Button variant="ghost" size="sm">Sign In</Button>
                  </Link>
                  <Link to="/auth">
                    <Button size="sm">Get Started</Button>
                  </Link>
                </div>
              )}
            </div>
          </header>

          {/* Main Content */}
          <main className="flex-1 pb-20 lg:pb-0">
            {children}
          </main>

          {/* Mobile Bottom Navigation */}
          <MobileBottomNav />
        </SidebarInset>
      </div>
    </SidebarProvider>
  );
}
