"use client";

import * as React from "react";
import { usePathname, useRouter } from "next/navigation";
import { 
  ChevronDown, 
  Menu, 
  Search, 
  TrendingUp, 
  TrendingDown,
  Signal,
  LogOut,
  User,
  Settings,
  Key
} from "lucide-react";

import { useDashboardFilters } from "@/components/layout/DashboardProvider";
import { useAuth } from "@/components/auth/AuthProvider";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { getMarketTicker } from "@/lib/mock";

const titleMap: Record<string, { title: string; description: string }> = {
  "/": {
    title: "Trading Terminal",
    description: "Sample portfolio charts and activity previews",
  },
  "/strategies": {
    title: "Strategy Concepts",
    description: "Example strategies and independent charts; historical evaluation unavailable",
  },
  "/analytics": {
    title: "Sample Analytics",
    description: "Sample trading charts and fixed example metrics",
  },
  "/nestegg": {
    title: "Nestegg",
    description: "Retirement analytics and scenario modeling",
  },
  "/probes": {
    title: "Von Neumann Probes",
    description: "Self-replicating evolutionary trading colony",
  },
  "/reports": {
    title: "Trade Log",
    description: "Complete history of your trading activity",
  },
  "/settings": {
    title: "Configuration",
    description: "Customize your terminal experience",
  },
};

function MarketTicker() {
  const ticker = getMarketTicker();
  const [prices, setPrices] = React.useState(ticker);
  
  // Simulate price updates
  React.useEffect(() => {
    const interval = setInterval(() => {
      setPrices(prev => prev.map(item => ({
        ...item,
        price: item.price * (1 + (Math.random() - 0.5) * 0.001),
        change: item.change + (Math.random() - 0.5) * 0.1,
      })));
    }, 3000);
    return () => clearInterval(interval);
  }, []);
  
  return (
    <div className="hidden xl:flex items-center gap-4 overflow-hidden">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <div className="relative">
          <Signal className="h-3 w-3 text-[#39ff14]" />
          <div className="absolute inset-0 animate-ping">
            <Signal className="h-3 w-3 text-[#39ff14] opacity-50" />
          </div>
        </div>
        <span className="uppercase tracking-wider font-medium">Demo prices</span>
      </div>
      <div className="flex items-center gap-5">
        {prices.slice(0, 4).map((item, index) => (
          <div 
            key={item.symbol} 
            className="flex items-center gap-2 group cursor-pointer transition-all duration-300 hover:scale-105"
            style={{ animationDelay: `${index * 100}ms` }}
          >
            <span className="text-xs font-bold text-foreground group-hover:text-[#00fff5] transition-colors">
              {item.symbol}
            </span>
            <span className="text-xs font-mono text-[#00fff5] transition-all duration-300">
              ${item.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            <span className={`flex items-center text-xs font-medium transition-all duration-300 ${
              item.change >= 0 ? "text-[#39ff14]" : "text-[#ff3366]"
            }`}>
              {item.change >= 0 ? (
                <TrendingUp className="h-3 w-3 mr-0.5" />
              ) : (
                <TrendingDown className="h-3 w-3 mr-0.5" />
              )}
              {item.change >= 0 ? '+' : ''}{item.change.toFixed(2)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Header({ onOpenMobileNav }: { onOpenMobileNav: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, profile, signOut } = useAuth();
  const { dateRange, setDateRange, searchQuery, setSearchQuery, dateRangeOptions } =
    useDashboardFilters();
  const [isSearchFocused, setIsSearchFocused] = React.useState(false);
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => { setMounted(true); }, []);

  const headerCopy = React.useMemo(() => titleMap[pathname] ?? titleMap["/"], [pathname]);
  const showSearch = pathname === "/";
  const showSampleRange = pathname === "/" || pathname === "/analytics";

  const displayName =
    profile?.full_name ||
    user?.user_metadata?.full_name ||
    user?.user_metadata?.display_name ||
    user?.email?.split("@")[0] ||
    "Trader";
  const initials = displayName.slice(0, 2).toUpperCase();
  const avatarSrc =
    profile?.avatar_url || user?.user_metadata?.avatar_url;

  const handleSignOut = async () => {
    await signOut();
    router.push("/login");
    router.refresh();
  };

  return (
    <header className="sticky top-0 z-30 flex flex-col gap-4 border-b border-[#00fff5]/10 bg-background/90 px-6 py-4 backdrop-blur-xl">
      {/* Animated top border */}
      <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-[#00fff5]/50 to-transparent" />
      
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden text-muted-foreground hover:text-[#00fff5] hover:bg-[#00fff5]/10 transition-all duration-300 hover:scale-105"
            onClick={onOpenMobileNav}
            aria-label="Open navigation menu"
          >
            <Menu className="h-4 w-4" />
          </Button>
          <div className="slide-right">
            <h1 className="text-xl font-semibold leading-tight tracking-wide uppercase text-[#00fff5] neon-text-cyan">
              {headerCopy.title}
            </h1>
            <p className="text-xs text-muted-foreground tracking-wider mt-0.5">{headerCopy.description}</p>
          </div>
        </div>
        
        <MarketTicker />
        
        <div className="flex flex-wrap items-center gap-3 slide-left">
          <span className="text-xs text-muted-foreground">Notifications unavailable</span>
          
          <ThemeToggle />
          
          {mounted ? (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  className="flex items-center gap-2 hover:bg-[#00fff5]/10 transition-all duration-300 group"
                >
                  <div className="relative">
                    <Avatar className="h-8 w-8 border border-[#00fff5]/30 transition-all duration-300 group-hover:border-[#00fff5]/60 group-hover:shadow-[0_0_10px_rgba(0,255,245,0.3)]">
                      <AvatarImage src={avatarSrc ?? undefined} alt="User avatar" />
                      <AvatarFallback className="bg-[#00fff5]/20 text-[#00fff5]">{initials}</AvatarFallback>
                    </Avatar>
                    <div className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-background bg-[#39ff14]" />
                  </div>
                  <span className="hidden text-sm font-medium sm:inline-flex text-foreground group-hover:text-[#00fff5] transition-colors">
                    {displayName}
                  </span>
                  <ChevronDown className="hidden h-4 w-4 sm:inline-flex text-muted-foreground group-hover:text-[#00fff5] transition-all duration-300 group-hover:rotate-180" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                className="w-48 border-[#00fff5]/20 bg-card/95 backdrop-blur-xl scale-in"
              >
                <DropdownMenuLabel className="text-[#00fff5]">
                  <div className="flex flex-col">
                    <span>{displayName}</span>
                    <span className="text-xs font-normal text-muted-foreground truncate">{user?.email}</span>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator className="bg-[#00fff5]/10" />
                <DropdownMenuItem disabled aria-describedby="account-settings-unavailable">
                  <User className="h-4 w-4 mr-2" />
                  Profile unavailable
                </DropdownMenuItem>
                <DropdownMenuItem disabled aria-describedby="account-settings-unavailable">
                  <Settings className="h-4 w-4 mr-2" />
                  Wallet settings unavailable
                </DropdownMenuItem>
                <DropdownMenuItem disabled aria-describedby="account-settings-unavailable">
                  <Key className="h-4 w-4 mr-2" />
                  API keys unavailable
                </DropdownMenuItem>
                <DropdownMenuLabel id="account-settings-unavailable" className="text-xs font-normal text-muted-foreground">
                  Profile, wallet settings and API key management are not available.
                </DropdownMenuLabel>
                <DropdownMenuSeparator className="bg-[#00fff5]/10" />
                <DropdownMenuItem
                  onClick={handleSignOut}
                  className="focus:bg-[#ff3366]/10 text-[#ff3366] focus:text-[#ff3366] cursor-pointer transition-colors"
                >
                  <LogOut className="h-4 w-4 mr-2" />
                  Sign Out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <Button variant="ghost" className="flex items-center gap-2">
              <Avatar className="h-8 w-8 border border-[#00fff5]/30">
                <AvatarFallback className="bg-[#00fff5]/20 text-[#00fff5]">{initials}</AvatarFallback>
              </Avatar>
              <span className="hidden text-sm font-medium sm:inline-flex">{displayName}</span>
            </Button>
          )}
        </div>
      </div>
      
      {showSampleRange ? (
        <div className="flex flex-wrap items-center gap-3">
          {showSearch ? (
            <div className={`relative flex-1 min-w-[220px] transition-all duration-300 ${isSearchFocused ? 'scale-[1.02]' : ''}`}>
              <Search className={`pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 transition-colors duration-300 ${
                isSearchFocused ? 'text-[#00fff5]' : 'text-muted-foreground'
              }`} />
              <Input
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                onFocus={() => setIsSearchFocused(true)}
                onBlur={() => setIsSearchFocused(false)}
                aria-label="Search sample activity"
                placeholder="Search sample assets or transaction hashes..."
                className={`pl-9 border-[#00fff5]/20 bg-[#00fff5]/5 transition-all duration-300 ${
                  isSearchFocused
                    ? 'border-[#00fff5]/50 shadow-[0_0_20px_rgba(0,255,245,0.15)] bg-[#00fff5]/10'
                    : 'focus:border-[#00fff5]/40'
                } placeholder:text-muted-foreground`}
              />
              {isSearchFocused && (
                <div className="absolute inset-0 rounded-md pointer-events-none">
                  <div className="absolute inset-0 rounded-md border border-[#00fff5]/30 animate-pulse" />
                </div>
              )}
            </div>
          ) : null}
          {mounted ? (
            <Select value={dateRange} onValueChange={(value) => {
              const option = dateRangeOptions.find(option => option.value === value);
              if (option) setDateRange(option.value);
            }}>
              <SelectTrigger aria-label="Sample date range" aria-describedby="sample-date-range-scope" className="w-[180px] border-[#00fff5]/20 bg-[#00fff5]/5 focus:border-[#00fff5]/40 focus:ring-[#00fff5]/20 transition-all duration-300 hover:bg-[#00fff5]/10">
                <SelectValue placeholder="Sample date range" />
              </SelectTrigger>
              <SelectContent className="border-[#00fff5]/20 bg-card/95 backdrop-blur-xl">
                {dateRangeOptions.map((option) => (
                  <SelectItem
                    key={option.value}
                    value={option.value}
                    className="focus:bg-[#00fff5]/10 focus:text-[#00fff5] cursor-pointer transition-colors"
                  >
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <div className="w-[180px] h-9 rounded-md border border-[#00fff5]/20 bg-[#00fff5]/5" />
          )}
          <p id="sample-date-range-scope" className="w-full text-xs text-muted-foreground">
            Sample range filters dated examples only. Allocation, exchange-volume and fixed stat examples stay unchanged.
          </p>
        </div>
      ) : null}
    </header>
  );
}
