"use client";

import React from "react";

import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { DashboardProvider } from "@/components/layout/DashboardProvider";
import { Toaster } from "@/components/ui/sonner";

function AuroraBackground() {
  return (
    <div className="aurora-bg" aria-hidden="true" />
  );
}

function Particles() {
  return (
    <div className="particles" aria-hidden="true">
      <div className="particle" style={{ left: '10%' }} />
      <div className="particle" style={{ left: '25%' }} />
      <div className="particle" style={{ left: '40%' }} />
      <div className="particle" style={{ left: '55%' }} />
      <div className="particle" style={{ left: '70%' }} />
      <div className="particle" style={{ left: '85%' }} />
    </div>
  );
}

function DataStreamLine() {
  return (
    <div className="fixed top-0 left-0 right-0 h-[2px] z-50 overflow-hidden">
      <div className="h-full w-full bg-gradient-to-r from-transparent via-[#00fff5] to-transparent animate-[data-flow_3s_linear_infinite]" />
    </div>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = React.useState(false);
  const [mobileOpen, setMobileOpen] = React.useState(false);

  return (
    <DashboardProvider>
      <div className="flex min-h-screen bg-background text-foreground crt-flicker">
        {/* Aurora glow background */}
        <AuroraBackground />
        
        {/* Floating particles */}
        <Particles />
        
        {/* Grid background */}
        <div className="fixed inset-0 synthwave-grid pointer-events-none opacity-50" />
        
        {/* Gradient overlay */}
        <div className="fixed inset-0 bg-gradient-to-br from-[#00fff5]/5 via-transparent to-[#ff00ff]/5 pointer-events-none" />
        
        {/* Subtle scanlines */}
        <div className="fixed inset-0 pointer-events-none opacity-[0.02]">
          <div className="absolute inset-0 bg-[repeating-linear-gradient(0deg,transparent,transparent_2px,rgba(0,0,0,0.3)_2px,rgba(0,0,0,0.3)_4px)]" />
        </div>
        
        {/* Top data stream line */}
        <DataStreamLine />
        
        <Sidebar
          collapsed={collapsed}
          onToggleCollapse={() => setCollapsed((prev) => !prev)}
          mobileOpen={mobileOpen}
          onMobileOpenChange={setMobileOpen}
        />
        <div className="flex w-full flex-1 flex-col relative z-10">
          <Header onOpenMobileNav={() => setMobileOpen(true)} />
          <main className="flex-1 px-6 py-6">
            <div className="mx-auto w-full max-w-7xl space-y-6">{children}</div>
          </main>
          
          {/* Footer */}
          <footer className="border-t border-[#00fff5]/10 px-6 py-4 relative">
            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#00fff5]/50 to-transparent" />
            <div className="mx-auto max-w-7xl flex flex-wrap items-center justify-between gap-4 text-xs text-muted-foreground">
              <div className="flex items-center gap-4">
                <span className="uppercase tracking-wider font-medium">Nexus Terminal v2.0</span>
                <span className="hidden sm:inline text-[#00fff5]/30">•</span>
                <span className="hidden sm:inline opacity-60">Market ticker uses demo data</span>
              </div>
            </div>
          </footer>
        </div>
        <Toaster 
          richColors 
          toastOptions={{
            style: {
              background: 'rgba(15, 15, 26, 0.95)',
              border: '1px solid rgba(0, 255, 245, 0.2)',
              color: '#eaeaea',
              backdropFilter: 'blur(10px)',
            },
            className: 'slide-up',
          }}
        />
      </div>
    </DashboardProvider>
  );
}
