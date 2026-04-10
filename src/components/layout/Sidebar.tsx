"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  BarChart3,
  Dna,
  FileText,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Wallet,
  Zap,
  TrendingUp,
  TrendingDown,
  FlaskConical,
  PiggyBank,
  BookOpen,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent } from "@/components/ui/sheet";

const navItems = [
  { label: "Terminal", href: "/", icon: LayoutDashboard },
  { label: "Strategies", href: "/strategies", icon: FlaskConical },
  { label: "Analytics", href: "/analytics", icon: BarChart3 },
  { label: "Portfolio", href: "/portfolio", icon: Wallet },
  { label: "Nestegg", href: "/nestegg", icon: PiggyBank },
  { label: "Probes", href: "/probes", icon: Dna },
  { label: "Trade Log", href: "/reports", icon: FileText },
  { label: "Docs", href: "/docs", icon: BookOpen },
  { label: "Settings", href: "/settings", icon: Settings },
];

function NavList({ collapsed, onNavigate }: { collapsed: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-1 px-3">
      {navItems.map((item, index) => {
        const isActive = pathname === item.href;
        const Icon = item.icon;

        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            className={cn(
              "group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-all duration-300",
              "hover:translate-x-1",
              isActive
                ? "bg-[#00fff5]/10 text-[#00fff5]"
                : "text-muted-foreground hover:bg-[#00fff5]/5 hover:text-[#00fff5]"
            )}
            style={{ animationDelay: `${index * 50}ms` }}
          >
            {/* Active indicator line */}
            {isActive && (
              <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 rounded-r-full bg-[#00fff5] shadow-[0_0_10px_#00fff5]" />
            )}
            
            <div className={cn(
              "relative transition-all duration-300",
              isActive && "animate-pulse"
            )}>
              <Icon className={cn(
                "h-4 w-4 transition-all duration-300",
                isActive && "drop-shadow-[0_0_8px_rgba(0,255,245,0.8)]",
                "group-hover:scale-110"
              )} />
              {isActive && (
                <div className="absolute inset-0 h-4 w-4 rounded-full bg-[#00fff5]/30 animate-ping" />
              )}
            </div>
            
            <span className={cn(
              "truncate tracking-wide uppercase text-xs transition-all duration-300",
              collapsed && "sr-only",
              "group-hover:tracking-wider"
            )}>
              {item.label}
            </span>
            
            {isActive && !collapsed && (
              <Activity className="ml-auto h-3 w-3 animate-pulse" />
            )}
            
            {/* Hover glow effect */}
            <div className={cn(
              "absolute inset-0 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity duration-300",
              "bg-gradient-to-r from-[#00fff5]/5 to-transparent"
            )} />
          </Link>
        );
      })}
    </nav>
  );
}

function Logo({ collapsed }: { collapsed: boolean }) {
  return (
    <div className={cn(
      "flex items-center gap-2 group",
      collapsed ? "justify-center" : ""
    )}>
      <div className="relative">
        <div className={cn(
          "flex h-9 w-9 items-center justify-center rounded-lg",
          "bg-gradient-to-br from-[#00fff5] to-[#ff00ff]",
          "transition-all duration-300 group-hover:scale-110 group-hover:rotate-12",
          "shadow-lg shadow-[#00fff5]/20"
        )}>
          <Zap className="h-5 w-5 text-black transition-transform duration-300 group-hover:scale-110" />
        </div>
        {/* Animated glow ring */}
        <div className="absolute -inset-1 rounded-lg bg-gradient-to-br from-[#00fff5] to-[#ff00ff] opacity-40 blur-md animate-pulse" />
        <div className="absolute -inset-2 rounded-xl opacity-20 animate-ping" style={{ 
          background: 'linear-gradient(45deg, #00fff5, #ff00ff)',
          animationDuration: '3s' 
        }} />
      </div>
      {!collapsed && (
        <div className="flex flex-col overflow-hidden">
          <span className="font-[var(--font-orbitron)] text-sm font-bold tracking-wider text-[#00fff5] neon-text-cyan glitch" data-text="NEXUS">
            NEXUS
          </span>
          <span className="text-[10px] tracking-widest text-muted-foreground uppercase animate-pulse">
            Terminal v2.0
          </span>
        </div>
      )}
    </div>
  );
}

function MarketStatus() {
  const btcChange = 2.34;
  const ethChange = -1.12;
  
  return (
    <div className="mx-3 rounded-lg border border-[#00fff5]/20 bg-gradient-to-br from-[#00fff5]/5 to-transparent p-3 relative overflow-hidden">
      {/* Animated background */}
      <div className="absolute inset-0 bg-gradient-to-r from-transparent via-[#00fff5]/5 to-transparent animate-[shimmer_3s_infinite]" />
      
      <div className="relative">
        <div className="flex items-center gap-2 text-xs mb-3">
          <div className="relative">
            <div className="h-2 w-2 rounded-full bg-[#39ff14]" />
            <div className="absolute inset-0 h-2 w-2 rounded-full bg-[#39ff14] animate-ping" />
          </div>
          <span className="text-[#39ff14] uppercase tracking-wider font-bold">Markets Live</span>
        </div>
        
        <div className="grid grid-cols-2 gap-3">
          <div className="group cursor-pointer">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">BTC</p>
            <p className="text-sm font-mono text-[#00fff5] font-bold group-hover:text-[#39ff14] transition-colors">
              $94,523
            </p>
            <p className={`text-[10px] flex items-center gap-0.5 ${btcChange >= 0 ? 'text-[#39ff14]' : 'text-[#ff3366]'}`}>
              {btcChange >= 0 ? <TrendingUp className="h-2.5 w-2.5" /> : <TrendingDown className="h-2.5 w-2.5" />}
              {btcChange >= 0 ? '+' : ''}{btcChange}%
            </p>
          </div>
          <div className="group cursor-pointer">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">ETH</p>
            <p className="text-sm font-mono text-[#00fff5] font-bold group-hover:text-[#39ff14] transition-colors">
              $3,198
            </p>
            <p className={`text-[10px] flex items-center gap-0.5 ${ethChange >= 0 ? 'text-[#39ff14]' : 'text-[#ff3366]'}`}>
              {ethChange >= 0 ? <TrendingUp className="h-2.5 w-2.5" /> : <TrendingDown className="h-2.5 w-2.5" />}
              {ethChange >= 0 ? '+' : ''}{ethChange}%
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

type SidebarProps = {
  collapsed: boolean;
  onToggleCollapse: () => void;
  mobileOpen: boolean;
  onMobileOpenChange: (open: boolean) => void;
};

export function Sidebar({ collapsed, onToggleCollapse, mobileOpen, onMobileOpenChange }: SidebarProps) {
  return (
    <>
      <aside
        className={cn(
          "hidden h-screen flex-col border-r border-[#00fff5]/10 bg-sidebar/95 backdrop-blur-xl transition-all duration-300 lg:flex",
          collapsed ? "w-20" : "w-64"
        )}
      >
        {/* Subtle gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-b from-[#00fff5]/5 via-transparent to-[#ff00ff]/5 pointer-events-none" />
        
        <div className="flex h-16 items-center justify-between px-4 relative">
          <Logo collapsed={collapsed} />
          <Button 
            variant="ghost" 
            size="icon" 
            onClick={onToggleCollapse} 
            aria-label="Toggle sidebar"
            className="text-muted-foreground hover:text-[#00fff5] hover:bg-[#00fff5]/10 transition-all duration-300 hover:rotate-180"
          >
            {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </Button>
        </div>
        
        <NavList collapsed={collapsed} />
        
        {!collapsed && (
          <div className="mt-6 slide-up" style={{ animationDelay: '200ms' }}>
            <MarketStatus />
          </div>
        )}
        
        <div className="mt-auto px-4 py-4">
          {!collapsed ? (
            <div className="rounded-lg border border-[#ff00ff]/20 bg-gradient-to-br from-[#ff00ff]/10 to-transparent p-3 text-xs relative overflow-hidden group cursor-pointer hover:border-[#ff00ff]/40 transition-all duration-300">
              {/* Animated shine effect */}
              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/5 to-transparent -translate-x-full group-hover:translate-x-full transition-transform duration-700" />
              
              <p className="text-[#ff00ff] font-bold uppercase tracking-wider flex items-center gap-2">
                <Zap className="h-3 w-3 animate-pulse" />
                Pro Mode
              </p>
              <p className="mt-1 text-muted-foreground">Advanced trading features enabled</p>
            </div>
          ) : (
            <div className="flex justify-center">
              <div className="relative">
                <div className="h-3 w-3 rounded-full bg-[#ff00ff]" />
                <div className="absolute inset-0 h-3 w-3 rounded-full bg-[#ff00ff] animate-ping opacity-50" />
              </div>
            </div>
          )}
        </div>
      </aside>

      <Sheet open={mobileOpen} onOpenChange={onMobileOpenChange}>
        <SheetContent side="left" className="w-72 border-r border-[#00fff5]/10 bg-sidebar/95 backdrop-blur-xl p-0">
          <div className="absolute inset-0 bg-gradient-to-b from-[#00fff5]/5 via-transparent to-[#ff00ff]/5 pointer-events-none" />
          <div className="flex h-16 items-center px-6 relative">
            <Logo collapsed={false} />
          </div>
          <NavList collapsed={false} onNavigate={() => onMobileOpenChange(false)} />
          <div className="mt-6 px-3">
            <MarketStatus />
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
