"use client";

import * as React from "react";
import { Search, ChevronRight, ExternalLink, BookOpen, Dna, LayoutDashboard, FlaskConical, BarChart3, Wallet, PiggyBank, FileText, Settings, Cpu, Sparkles, Crosshair, Activity, TrendingUp, Braces, Layers, Boxes, Gauge, ShieldAlert, Radio, BarChart, GitBranch, ScanLine } from "lucide-react";
import { cn } from "@/lib/utils";

/* ─── Types ───────────────────────────────────────────────────────────── */

interface DocSection {
  id: string;
  title: string;
  icon?: React.ReactNode;
  children?: DocSection[];
}

/* ─── Table of Contents ───────────────────────────────────────────────── */

const TOC: DocSection[] = [
  {
    id: "overview",
    title: "Overview",
    icon: <BookOpen className="w-4 h-4" />,
  },
  {
    id: "terminal",
    title: "Terminal",
    icon: <LayoutDashboard className="w-4 h-4" />,
  },
  {
    id: "strategies",
    title: "Strategies",
    icon: <FlaskConical className="w-4 h-4" />,
  },
  {
    id: "analytics",
    title: "Analytics",
    icon: <BarChart3 className="w-4 h-4" />,
  },
  {
    id: "portfolio",
    title: "Portfolio",
    icon: <Wallet className="w-4 h-4" />,
  },
  {
    id: "nestegg",
    title: "Nestegg",
    icon: <PiggyBank className="w-4 h-4" />,
  },
  {
    id: "probes",
    title: "Von Neumann Probes",
    icon: <Dna className="w-4 h-4" />,
    children: [
      { id: "probes-overview", title: "Dashboard Overview" },
      { id: "probes-colony-config", title: "Colony Configuration" },
      { id: "probes-controls", title: "Simulation Controls" },
      { id: "probes-colony-tab", title: "Colony Tab" },
      { id: "probes-evolution-tab", title: "Evolution Tab" },
      { id: "probes-genealogy-tab", title: "Genealogy Tab" },
      { id: "probes-probe-detail", title: "Probe Detail Dialog" },
      { id: "probes-price-feed", title: "Live Price Feed" },
      { id: "probes-websocket", title: "Real-Time WebSocket" },
      { id: "probes-data-persistence", title: "Data Persistence" },
    ],
  },
  {
    id: "service",
    title: "Python Service",
    icon: <Cpu className="w-4 h-4" />,
    children: [
      { id: "service-architecture", title: "Architecture" },
      { id: "service-gene-registry", title: "Gene Registry" },
      { id: "service-probe-lifecycle", title: "Probe Lifecycle" },
      { id: "service-signal-computation", title: "Signal Computation" },
      { id: "service-tick-loop", title: "Tick Loop" },
      { id: "service-capital-management", title: "Capital Management" },
      { id: "service-market-feeds", title: "Market Feeds" },
      { id: "service-api", title: "REST API" },
    ],
  },
  {
    id: "evolution",
    title: "Evolutionary Algorithms",
    icon: <Sparkles className="w-4 h-4" />,
    children: [
      { id: "evo-strategy-pattern", title: "Strategy Pattern" },
      { id: "evo-fitness", title: "Fitness Scoring" },
      { id: "evo-ga", title: "Genetic Algorithm" },
      { id: "evo-de", title: "Differential Evolution" },
      { id: "evo-pso", title: "Particle Swarm Optimization" },
      { id: "evo-cmaes", title: "CMA-ES" },
      { id: "evo-diversity", title: "Diversity Management" },
      { id: "evo-multi-colony", title: "Multi-Colony System" },
    ],
  },
  {
    id: "trade-log",
    title: "Trade Log",
    icon: <FileText className="w-4 h-4" />,
  },
  {
    id: "settings",
    title: "Settings",
    icon: <Settings className="w-4 h-4" />,
  },
];

/* ─── Coming Soon Block ───────────────────────────────────────────────── */

function ComingSoon({ title }: { title: string }) {
  return (
    <div className="rounded-lg border border-dashed border-white/10 bg-white/[0.02] p-8 text-center">
      <p className="text-lg font-medium text-white/40">Coming Soon!</p>
      <p className="mt-1 text-sm text-white/25">
        Documentation for {title} is under construction.
      </p>
    </div>
  );
}

/* ─── Heading Anchors ─────────────────────────────────────────────────── */

function H2({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h2 id={id} className="scroll-mt-20 text-2xl font-bold text-[#00fff5] border-b border-white/10 pb-2 mb-4 mt-10 first:mt-0">
      {children}
    </h2>
  );
}

function H3({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h3 id={id} className="scroll-mt-20 text-xl font-semibold text-white/90 mt-8 mb-3">
      {children}
    </h3>
  );
}

function H4({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <h4 id={id} className="scroll-mt-20 text-base font-semibold text-[#ff00ff] mt-6 mb-2">
      {children}
    </h4>
  );
}

function P({ children }: { children: React.ReactNode }) {
  return <p className="text-sm text-white/70 leading-relaxed mb-3">{children}</p>;
}

function Code({ children }: { children: React.ReactNode }) {
  return (
    <code className="px-1.5 py-0.5 rounded bg-white/5 text-[#00fff5] text-xs font-mono">
      {children}
    </code>
  );
}

function CodeBlock({ children, title }: { children: string; title?: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-black/40 mb-4 overflow-hidden">
      {title && (
        <div className="px-4 py-1.5 border-b border-white/10 bg-white/[0.03] text-xs text-white/50 font-mono">
          {title}
        </div>
      )}
      <pre className="p-4 text-xs text-white/70 font-mono overflow-x-auto whitespace-pre leading-relaxed">
        {children}
      </pre>
    </div>
  );
}

function Table({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto mb-4 rounded-lg border border-white/10">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-white/10 bg-white/[0.03]">
            {headers.map((h) => (
              <th key={h} className="px-3 py-2 text-left font-semibold text-[#00fff5]">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-white/5 hover:bg-white/[0.02]">
              {row.map((cell, j) => (
                <td key={j} className="px-3 py-2 text-white/60 font-mono">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Callout({ type = "info", children }: { type?: "info" | "warning" | "tip"; children: React.ReactNode }) {
  const colors = {
    info: "border-[#00fff5]/30 bg-[#00fff5]/5 text-[#00fff5]",
    warning: "border-yellow-500/30 bg-yellow-500/5 text-yellow-400",
    tip: "border-[#39ff14]/30 bg-[#39ff14]/5 text-[#39ff14]",
  };
  const labels = { info: "INFO", warning: "WARNING", tip: "TIP" };
  return (
    <div className={cn("rounded-lg border p-4 mb-4 text-sm", colors[type])}>
      <span className="font-bold text-xs tracking-wider">{labels[type]}</span>
      <div className="mt-1 text-white/70">{children}</div>
    </div>
  );
}

/* ─── Main Docs Page ──────────────────────────────────────────────────── */

export default function DocsPage() {
  const [search, setSearch] = React.useState("");
  const [activeSectionId, setActiveSectionId] = React.useState("overview");
  const contentRef = React.useRef<HTMLDivElement>(null);

  const scrollTo = React.useCallback((id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    const y = el.getBoundingClientRect().top + window.scrollY - 100;
    window.scrollTo({ top: y, behavior: "smooth" });
  }, []);

  // Intersection observer for active section tracking
  React.useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActiveSectionId(entry.target.id);
          }
        }
      },
      { rootMargin: "-100px 0px -60% 0px" },
    );
    const headings = document.querySelectorAll("h2[id], h3[id]");
    headings.forEach((h) => observer.observe(h));
    return () => observer.disconnect();
  }, []);

  // Build flat list for search
  const allSections = React.useMemo(() => {
    const flat: { id: string; title: string; parent?: string }[] = [];
    for (const s of TOC) {
      flat.push({ id: s.id, title: s.title });
      for (const c of s.children ?? []) {
        flat.push({ id: c.id, title: c.title, parent: s.title });
      }
    }
    return flat;
  }, []);

  const filteredSections = search.trim()
    ? allSections.filter(
        (s) =>
          s.title.toLowerCase().includes(search.toLowerCase()) ||
          (s.parent ?? "").toLowerCase().includes(search.toLowerCase()),
      )
    : [];

  return (
    <div className="flex -mx-6 -mt-6">
      {/* Sidebar / Table of Contents */}
      <aside className="hidden xl:block w-64 shrink-0 border-r border-white/10 sticky top-4 self-start max-h-[calc(100vh-2rem)] overflow-y-auto py-6 px-4">
        <div className="mb-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search docs..."
              className="w-full rounded-md border border-white/10 bg-white/[0.03] pl-9 pr-3 py-2 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-[#00fff5]/40"
            />
          </div>
          {search.trim() && filteredSections.length > 0 && (
            <div className="mt-2 rounded-md border border-white/10 bg-black/80 p-2 space-y-1 max-h-48 overflow-y-auto">
              {filteredSections.map((s) => (
                <button
                  key={s.id}
                  onClick={() => { scrollTo(s.id); setSearch(""); }}
                  className="block w-full text-left rounded px-2 py-1.5 text-xs text-white/70 hover:bg-[#00fff5]/10 hover:text-[#00fff5]"
                >
                  {s.parent && <span className="text-white/30">{s.parent} / </span>}
                  {s.title}
                </button>
              ))}
            </div>
          )}
        </div>

        <nav className="space-y-1">
          {TOC.map((section) => (
            <div key={section.id}>
              <button
                onClick={() => scrollTo(section.id)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors text-left",
                  activeSectionId === section.id
                    ? "bg-[#00fff5]/10 text-[#00fff5]"
                    : "text-white/50 hover:text-white/80 hover:bg-white/5",
                )}
              >
                {section.icon}
                {section.title}
              </button>
              {section.children && (
                <div className="ml-6 mt-1 space-y-0.5 border-l border-white/5 pl-3">
                  {section.children.map((child) => (
                    <button
                      key={child.id}
                      onClick={() => scrollTo(child.id)}
                      className={cn(
                        "block w-full text-left rounded-md px-2 py-1 text-xs transition-colors",
                        activeSectionId === child.id
                          ? "text-[#00fff5]"
                          : "text-white/40 hover:text-white/70",
                      )}
                    >
                      {child.title}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>
      </aside>

      {/* Main Content */}
      <main ref={contentRef} className="flex-1 min-w-0 px-6 py-8">
        <div className="max-w-4xl mx-auto">
        {/* Title */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white">
            <span className="text-[#00fff5]">NEXUS</span> Documentation
          </h1>
          <p className="mt-2 text-sm text-white/50">
            Complete reference for every page, feature, and system in The Dashboard.
          </p>
          {/* Mobile search */}
          <div className="xl:hidden mt-4 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search docs..."
              className="w-full rounded-md border border-white/10 bg-white/[0.03] pl-9 pr-3 py-2 text-sm text-white placeholder:text-white/30 focus:outline-none focus:border-[#00fff5]/40"
            />
            {search.trim() && filteredSections.length > 0 && (
              <div className="absolute z-50 mt-1 w-full rounded-md border border-white/10 bg-black/95 p-2 space-y-1 max-h-48 overflow-y-auto">
                {filteredSections.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => { scrollTo(s.id); setSearch(""); }}
                    className="block w-full text-left rounded px-2 py-1.5 text-xs text-white/70 hover:bg-[#00fff5]/10 hover:text-[#00fff5]"
                  >
                    {s.parent && <span className="text-white/30">{s.parent} / </span>}
                    {s.title}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ───────── OVERVIEW ───────── */}
        <H2 id="overview">Overview</H2>
        <P>
          The Dashboard is a cyberpunk-themed trading terminal and research platform built with Next.js, Supabase, and a Python asyncio backend. It provides tools for market analysis, portfolio tracking, strategy research, financial planning, and autonomous evolutionary trading probes.
        </P>
        <P>
          The app consists of eight main sections accessible from the sidebar, plus a Python microservice that powers the Von Neumann evolutionary probe system. All pages are behind authentication and data is scoped per user.
        </P>

        {/* ───────── TERMINAL ───────── */}
        <H2 id="terminal">Terminal</H2>
        <ComingSoon title="Terminal" />

        {/* ───────── STRATEGIES ───────── */}
        <H2 id="strategies">Strategies</H2>
        <ComingSoon title="Strategies" />

        {/* ───────── ANALYTICS ───────── */}
        <H2 id="analytics">Analytics</H2>
        <ComingSoon title="Analytics" />

        {/* ───────── PORTFOLIO ───────── */}
        <H2 id="portfolio">Portfolio</H2>
        <ComingSoon title="Portfolio" />

        {/* ───────── NESTEGG ───────── */}
        <H2 id="nestegg">Nestegg</H2>
        <ComingSoon title="Nestegg" />

        {/* ───────── VON NEUMANN PROBES ───────── */}
        <H2 id="probes">Von Neumann Probes</H2>
        <P>
          The Probes page is a real-time dashboard for running, monitoring, and analyzing autonomous evolutionary trading agents. Each &ldquo;probe&rdquo; is an independent trading entity with a genetic blueprint (genome) that defines its signal computation parameters, risk management rules, and lifecycle thresholds. Probes trade Solana DEX pairs, and the colony evolves over time through selection, reproduction, and mutation.
        </P>
        <P>
          The system is powered by a Python FastAPI service (the Von Neumann service) that runs the tick loop, manages the probe lifecycle, and broadcasts events over WebSocket. The frontend receives events in real time and also polls Supabase for persistence.
        </P>

        <H3 id="probes-overview">Dashboard Overview</H3>
        <P>
          When you open the Probes page, the top section shows the simulation control bar and a set of summary metric cards.
        </P>
        <H4 id="probes-metric-cards">Metric Cards</H4>
        <P>Five metric cards display the colony&rsquo;s vital signs at a glance:</P>
        <Table
          headers={["Card", "Value", "Secondary"]}
          rows={[
            ["Active Probes", "Count of live (non-DEAD) probes", "Count of dead probes"],
            ["Generation", "Current generation number", "Current tick count"],
            ["Best Fitness", "Highest fitness score in the colony (3 decimals)", "Population diversity metric"],
            ["Colony Capital", "Total capital across all live probes", "Reserve capital available"],
            ["JUP API Calls", "Total API calls to Jupiter (paper mode)", "Calls/min and projected 24h rate"],
          ]}
        />
        <P>
          The JUP API Calls card only appears in paper trading mode or when API calls have been made.
        </P>

        <H3 id="probes-colony-config">Colony Configuration</H3>
        <P>
          Clicking &ldquo;New Colony&rdquo; opens the Colony Configuration dialog. This is the launch control for a new simulation run.
        </P>

        <H4 id="probes-config-strategy">Evolution Strategy Selector</H4>
        <P>
          The top of the dialog shows a dropdown to select the evolutionary algorithm. The available strategies are fetched from the Python service at <Code>/api/v1/strategies</Code>. If the backend is unreachable, a hardcoded fallback list is used.
        </P>
        <Table
          headers={["Strategy", "Description"]}
          rows={[
            ["Genetic Algorithm", "Classic GA with tournament selection, uniform crossover, and Gaussian mutation."],
            ["Differential Evolution", "DE/rand/1/bin -- differential mutation with binomial crossover."],
            ["Particle Swarm Optimization", "PSO with inertia weight, cognitive and social components."],
            ["CMA-ES", "Covariance Matrix Adaptation Evolution Strategy."],
          ]}
        />

        <H4 id="probes-config-mode">Trading Mode</H4>
        <P>
          Two modes are available:
        </P>
        <Table
          headers={["Mode", "Description"]}
          rows={[
            ["Simulation", "Fully synthetic prices via Geometric Brownian Motion. No external API calls. Fast iteration."],
            ["Paper Trade", "Live prices from Jupiter DEX aggregator on Solana. Real market conditions, no real capital."],
          ]}
        />

        <H4 id="probes-config-presets">Presets</H4>
        <P>Four colony configuration presets provide starting points:</P>
        <Table
          headers={["Preset", "Behavior"]}
          rows={[
            ["Default", "All 15 genes evolve freely across their full range. All 8 assets available."],
            ["RSI Focus", "EMA and volume genes are fixed; only RSI + risk + lifecycle genes evolve."],
            ["Conservative Risk", "Tighter risk gene bounds (smaller positions, tighter stops). Max 1 open position."],
            ["Wide Exploration", "Lower reproduction benchmarks (3-8% ROI, $2-$8 profit), reproduction every 50 ticks instead of 100."],
          ]}
        />

        <H4 id="probes-config-genes">Gene Controls</H4>
        <P>
          Each of the 15 genes can be individually configured. Genes are organized into three groups: Signal, Risk, and Lifecycle. For each gene you can:
        </P>
        <ul className="list-disc list-inside text-sm text-white/70 space-y-1 mb-3 ml-4">
          <li>Enable or disable it from mutation/crossover (checkbox)</li>
          <li>Fix it to a specific value (toggle switch + input)</li>
          <li>Set custom min/max bounds (dual-thumb range slider)</li>
        </ul>

        <H4 id="probes-config-assets">Asset Selection</H4>
        <P>
          A checkbox grid of 8 Solana DEX trading pairs. Deselecting an asset removes it from the pool available to probes. At least one asset must be selected.
        </P>
        <Table
          headers={["Asset", "Sim Base Price"]}
          rows={[
            ["SOL/USDC", "$150.00"],
            ["JUP/USDC", "$0.85"],
            ["BONK/USDC", "$0.000025"],
            ["WIF/USDC", "$2.10"],
            ["JTO/USDC", "$3.50"],
            ["PYTH/USDC", "$0.42"],
            ["ORCA/USDC", "$3.80"],
            ["RAY/USDC", "$2.20"],
          ]}
        />

        <H4 id="probes-config-advanced">Advanced Settings</H4>
        <Table
          headers={["Setting", "Default", "Description"]}
          rows={[
            ["Initial Probes", "10", "Number of Gen-0 probes spawned at start"],
            ["Max Capital", "$10,000", "Total capital pool for the colony"],
            ["Capital Per Probe", "$100", "Seed capital given to each new probe"],
            ["Tick Interval", "1000ms", "Milliseconds between market ticks"],
            ["Mutation Rate", "0.20", "Probability of mutating each gene (GA)"],
            ["Reproduction Interval", "100", "Ticks between evolution steps"],
            ["Max Lifespan", "none", "Force-kill probes after N ticks (optional)"],
            ["Max Probes", "50", "Population cap"],
          ]}
        />

        <H3 id="probes-controls">Simulation Controls</H3>
        <P>
          The control bar at the top of the dashboard adapts based on simulation state:
        </P>
        <Table
          headers={["State", "Available Actions"]}
          rows={[
            ["Stopped", "\"New Colony\" button opens the config dialog"],
            ["Running", "Pause and Stop buttons. Shows mode badge, strategy badge, generation, tick, and live probe count."],
            ["Paused", "Resume and Stop buttons"],
          ]}
        />
        <P>
          The connection indicator in the top-right shows the WebSocket status: a green &ldquo;LIVE&rdquo; dot when connected to the backend, red &ldquo;OFFLINE&rdquo; when disconnected.
        </P>
        <P>
          The Colony Selector (History button) opens a slide-out panel showing all past and active colony runs. Active colonies show live stats; historical runs show probe counts and best fitness. Clicking a run switches the dashboard to view that colony&rsquo;s data.
        </P>

        <H3 id="probes-colony-tab">Colony Tab</H3>
        <P>
          The Colony tab shows a responsive grid of probe cards with sorting and filtering controls.
        </P>
        <H4 id="probes-colony-sort">Sorting and Filtering</H4>
        <P>
          A dropdown sorts the grid by Fitness, Capital, Generation, or Trades (descending). A &ldquo;Show Dead&rdquo; checkbox toggles visibility of probes that have died. A badge shows the total count of displayed probes.
        </P>
        <H4 id="probes-colony-card">Probe Cards</H4>
        <P>
          Each card displays:
        </P>
        <ul className="list-disc list-inside text-sm text-white/70 space-y-1 mb-3 ml-4">
          <li><strong>Header:</strong> Probe name, generation badge, state badge (color-coded)</li>
          <li><strong>Metrics:</strong> Fitness (cyan), Capital (green), Win Rate (%), Trade count</li>
          <li><strong>ROI Bar:</strong> Progress bar showing capital vs initial. Green for profit, red for loss, with P&L amount</li>
        </ul>
        <P>Dead probes render at 50% opacity. Clicking any card opens the Probe Detail dialog.</P>

        <H3 id="probes-evolution-tab">Evolution Tab</H3>
        <P>
          The Evolution tab contains two visualizations:
        </P>
        <H4 id="probes-fitness-chart">Fitness Chart</H4>
        <P>
          A stacked area chart (Recharts) showing fitness progression across generations. Three series are plotted:
        </P>
        <ul className="list-disc list-inside text-sm text-white/70 space-y-1 mb-3 ml-4">
          <li><span className="text-[#00fff5]">Best Fitness</span> (cyan, solid area) — the top performer each generation</li>
          <li><span className="text-[#ff00ff]">Average Fitness</span> (magenta, solid area) — colony-wide average</li>
          <li><span className="text-white/50">Worst Fitness</span> (gray, dashed line) — the lowest scorer</li>
        </ul>
        <P>The X-axis shows generation numbers, the Y-axis shows fitness scores.</P>

        <H4 id="probes-generation-timeline">Generation Timeline</H4>
        <P>
          A horizontally-scrollable row of generation summary cards. Each card shows:
        </P>
        <ul className="list-disc list-inside text-sm text-white/70 space-y-1 mb-3 ml-4">
          <li>Generation number</li>
          <li>Probe count (alive / total)</li>
          <li>Best fitness (cyan)</li>
          <li>Average ROI (green if positive, red if negative)</li>
          <li>Genome diversity score</li>
        </ul>

        <H3 id="probes-genealogy-tab">Genealogy Tab</H3>
        <P>
          The Genealogy tab renders a recursive parent-child tree showing probe lineage. Each node displays the probe name (truncated), a generation badge, and the fitness score. Nodes are color-coded by state. Connecting lines show parent-child relationships. Clicking any node opens the Probe Detail dialog.
        </P>

        <H3 id="probes-probe-detail">Probe Detail Dialog</H3>
        <P>
          A modal dialog with full details about a single probe.
        </P>
        <H4 id="probes-detail-header">Header</H4>
        <P>Probe name (cyan), state badge, generation badge, and parent ID (first 8 characters).</P>
        <H4 id="probes-detail-timeline">Lifecycle Timeline</H4>
        <P>A visual bar showing born timestamp, died timestamp (if dead), lifespan duration, and death reason. Living probes show a pulsing green dot.</P>
        <H4 id="probes-detail-metrics">Metrics Grid</H4>
        <Table
          headers={["Metric", "Color"]}
          rows={[
            ["Fitness Score", "Cyan (#00fff5)"],
            ["Capital", "Green (#39ff14)"],
            ["P&L", "Green if positive, red if negative"],
            ["Win Rate", "Purple (#bf00ff)"],
            ["Sharpe Ratio", "Magenta (#ff00ff)"],
            ["Max Drawdown", "Red (#ff3366)"],
          ]}
        />
        <H4 id="probes-detail-genome">Genome DNA</H4>
        <P>
          A radar chart (Recharts) visualizes the probe&rsquo;s genome with each gene normalized to a 0-100 scale based on its min/max range. Below the radar chart, a table lists every gene with its label and current value.
        </P>
        <H4 id="probes-detail-trades">Trade History</H4>
        <P>
          A scrollable table of all trades the probe has executed, showing: asset pair, open time, entry price, exit price, P&L (color-coded), and exit reason (TAKE_PROFIT, STOP_LOSS, SIGNAL_EXIT, PROBE_DYING, REPRODUCING).
        </P>

        <H3 id="probes-price-feed">Live Price Feed</H3>
        <P>
          A horizontal ticker strip below the controls showing real-time prices for all active assets. Each price pill displays the asset symbol, current price (with format adapting to magnitude), and a change indicator (up/down arrow with percentage). Only appears when a simulation is running and prices are streaming.
        </P>

        <H3 id="probes-websocket">Real-Time WebSocket</H3>
        <P>
          The page maintains a persistent WebSocket connection to the Python service at <Code>ws://localhost:8765/ws</Code> (configurable via <Code>NEXT_PUBLIC_VN_WS_URL</Code>). The connection auto-reconnects with exponential backoff (1.5x multiplier, 15s cap).
        </P>
        <P>
          Every WebSocket message includes a <Code>colony_id</Code> field so the frontend can filter events per colony when multiple colonies are running. Message types handled:
        </P>
        <Table
          headers={["Message Type", "Effect"]}
          rows={[
            ["probe_born", "Adds a new probe to the grid"],
            ["probe_update", "Updates metrics for an existing probe"],
            ["probe_dying / probe_reproducing", "Marks a probe as DEAD with reason"],
            ["simulation_status", "Updates system status, generation, tick, active colonies list"],
            ["generation_complete", "Appends generation stats for the evolution chart"],
            ["price_update", "Updates the live price feed ticker"],
          ]}
        />
        <P>
          Commands can be sent over the WebSocket: <Code>{`{"type":"command","data":{"action":"stop","colony_id":"..."}}`}</Code>
        </P>

        <H3 id="probes-data-persistence">Data Persistence</H3>
        <P>Four Supabase tables store all probe data, scoped per user via Row Level Security:</P>
        <Table
          headers={["Table", "Purpose"]}
          rows={[
            ["vn_colonies", "Colony metadata: strategy, config, mode, status, timestamps"],
            ["vn_probes", "Every probe: genome, capital, trade stats, fitness, lifecycle timestamps"],
            ["vn_trades", "Individual trades: entry/exit prices, P&L, signal values, reasons"],
            ["vn_fitness_snapshots", "Point-in-time fitness readings per probe per tick"],
            ["vn_generation_stats", "Aggregate stats per generation: best/avg/worst fitness, capital, diversity"],
          ]}
        />
        <P>
          The frontend polls Supabase every 5 seconds as a fallback complement to WebSocket updates. Historical colony runs are browsable via the Colony Selector.
        </P>

        {/* ───────── PYTHON SERVICE ───────── */}
        <H2 id="service">Python Service</H2>
        <P>
          The Von Neumann service is a standalone Python asyncio application built with FastAPI and uvicorn. It runs independently from the Next.js frontend, communicating via REST API and WebSocket.
        </P>

        <H3 id="service-architecture">Architecture</H3>
        <P>The service is organized into four packages:</P>
        <CodeBlock title="vonneumann/">{`vonneumann/
  core/              # Evolutionary engine
    gene_registry.py   # Gene definitions and validation
    genome.py          # Genome dataclass and random factory
    probe.py           # Autonomous trading agent
    genesis.py         # Colony orchestrator (tick loop, lifecycle)
    evolution.py       # Fitness scoring, mutation, diversity utilities
    colony_config.py   # Per-run configuration and presets
    colony_manager.py  # Multi-colony manager
    types.py           # State machine, events, trade records
    names.py           # Probe name generator
    strategies/        # Pluggable EA strategy implementations
      base.py            # EvolutionStrategy ABC
      genetic_algorithm.py
      differential_evolution.py
      particle_swarm.py
      cma_es.py
  market/            # Market data feeds
    feed.py            # Abstract MarketFeed interface
    sim_feed.py        # GBM simulation feed
    jupiter_feed.py    # Live Jupiter DEX prices
    birdeye_feed.py    # Birdeye API integration
  db/                # Persistence
    connection.py      # Supabase client singleton
    repository.py      # CRUD operations + EventPersister
  server/            # API layer
    app.py             # FastAPI app, REST + WebSocket endpoints
    websocket.py       # Connection manager and broadcast`}</CodeBlock>
        <P>
          The dependency flow is strictly layered: <Code>types</Code> &rarr; <Code>gene_registry</Code> &rarr; <Code>genome</Code> &rarr; <Code>evolution</Code> &rarr; <Code>probe</Code> &rarr; <Code>genesis</Code>. The server layer orchestrates everything, wiring market feeds, the database persister, and WebSocket broadcasting into the genesis controller.
        </P>

        <H3 id="service-gene-registry">Gene Registry</H3>
        <P>
          The gene registry (<Code>GENE_REGISTRY</Code>) is the single source of truth for all evolvable parameters. Every gene has a name, label, group (Signal/Risk/Lifecycle), hard bounds (min/max), default value, type (FLOAT or INT), and a description. Three constraint functions run during validation:
        </P>
        <Table
          headers={["Constraint", "Rule", "Correction"]}
          rows={[
            ["EMA Fast", "ema_fast must be < ema_slow", "Set to max(3, ema_slow * 0.5)"],
            ["RSI Oversold", "rsi_oversold must be < rsi_overbought - 5", "Set to max(20, overbought - 15)"],
            ["Stop Loss", "stop_loss_pct must be < take_profit_pct", "Set to max(0.01, take_profit * 0.4)"],
          ]}
        />
        <P>Validation runs in two phases: first clamp all values to hard bounds, then run constraint functions in registration order and re-clamp.</P>

        <H4 id="service-gene-table">Complete Gene Table</H4>
        <Table
          headers={["Gene", "Group", "Type", "Min", "Max", "Default"]}
          rows={[
            ["rsi_period", "Signal", "INT", "5", "30", "14"],
            ["rsi_oversold", "Signal", "FLOAT", "20", "45", "32"],
            ["rsi_overbought", "Signal", "FLOAT", "55", "85", "70"],
            ["ema_fast", "Signal", "INT", "3", "20", "9"],
            ["ema_slow", "Signal", "INT", "10", "60", "21"],
            ["volume_threshold", "Signal", "FLOAT", "1.0", "3.0", "1.4"],
            ["position_size_pct", "Risk", "FLOAT", "0.05", "0.30", "0.15"],
            ["stop_loss_pct", "Risk", "FLOAT", "0.01", "0.10", "0.03"],
            ["take_profit_pct", "Risk", "FLOAT", "0.03", "0.20", "0.07"],
            ["max_open_positions", "Risk", "INT", "1", "4", "2"],
            ["timeframe_minutes", "Lifecycle", "INT", "5", "60", "15"],
            ["benchmark_target_pct", "Lifecycle", "FLOAT", "0.03", "0.15", "0.08"],
            ["reproduce_target_dollars", "Lifecycle", "FLOAT", "2.0", "50.0", "10.0"],
            ["death_drawdown_pct", "Lifecycle", "FLOAT", "0.10", "0.35", "0.20"],
            ["num_assets", "Lifecycle", "INT", "1", "3", "2"],
          ]}
        />

        <H3 id="service-probe-lifecycle">Probe Lifecycle</H3>
        <P>Every probe follows a strict state machine:</P>
        <CodeBlock>{`BORN ─> FUNDED ─> OBSERVING ─> TRADING ─> REPRODUCING ─> DEAD
                                  │                  │
                                  └──> DYING ─────────> DEAD`}</CodeBlock>
        <P>
          <Code>BORN</Code>: Probe created with a genome. <Code>FUNDED</Code>: Capital allocated from reserve. <Code>OBSERVING</Code>: Collecting price data, waiting for entry signals. <Code>TRADING</Code>: Has at least one open position. <Code>REPRODUCING</Code>: Fitness target met, positions closed, offspring being created. <Code>DYING</Code>: Drawdown threshold exceeded, positions being closed. <Code>DEAD</Code>: Terminal state, archived.
        </P>
        <P>
          A probe can die from OBSERVING (never traded) or from TRADING. Reproduction is only possible from TRADING state. Probes can also be force-killed by max lifespan enforcement or the evolution strategy&rsquo;s retirement logic.
        </P>

        <H3 id="service-signal-computation">Signal Computation</H3>
        <P>
          Each probe computes its own trading signals using its genome parameters. Signal evaluation (entry/exit) is gated by the probe&rsquo;s <Code>timeframe_minutes</Code> gene &mdash; signals are only checked every <Code>timeframe_minutes</Code> ticks. Stop loss and take profit are still checked every tick for risk management. A probe with <Code>timeframe_minutes=5</Code> evaluates signals every 5 ticks, while one with <Code>timeframe_minutes=60</Code> is much more deliberate.
        </P>

        <H4 id="service-signal-rsi">RSI (Relative Strength Index)</H4>
        <P>
          Standard Wilder&rsquo;s RSI over <Code>rsi_period</Code> candles. Requires at least <Code>rsi_period + 1</Code> price observations. Computes average gains and losses, then: <Code>RSI = 100 - (100 / (1 + avg_gain / avg_loss))</Code>.
        </P>

        <H4 id="service-signal-ema">EMA (Exponential Moving Average)</H4>
        <P>
          Two EMAs: fast (<Code>ema_fast</Code> period) and slow (<Code>ema_slow</Code> period). Smoothing factor: <Code>k = 2 / (period + 1)</Code>. Update: <Code>ema = price * k + ema * (1 - k)</Code>.
        </P>

        <H4 id="service-signal-entry">Entry Signal</H4>
        <P>All three conditions must be true simultaneously:</P>
        <ol className="list-decimal list-inside text-sm text-white/70 space-y-1 mb-3 ml-4">
          <li><strong>RSI Oversold:</strong> <Code>RSI &lt; rsi_oversold</Code> (asset is undervalued)</li>
          <li><strong>EMA Bullish Cross:</strong> <Code>ema_fast &gt; ema_slow</Code> (upward momentum)</li>
          <li><strong>Volume Confirmation:</strong> current volume &gt; <Code>volume_threshold</Code> &times; 20-candle average volume</li>
        </ol>

        <H4 id="service-signal-exit">Exit Signal</H4>
        <P>Either condition triggers a signal exit:</P>
        <ol className="list-decimal list-inside text-sm text-white/70 space-y-1 mb-3 ml-4">
          <li><Code>RSI &gt; rsi_overbought</Code> (asset is overvalued), OR</li>
          <li><Code>ema_fast &lt; ema_slow</Code> (bearish crossover)</li>
        </ol>

        <H4 id="service-signal-sltp">Stop Loss / Take Profit</H4>
        <P>
          Checked every tick for each open position. Computes return: <Code>(current_price - entry_price) / entry_price</Code>. Closes the position if return &le; <Code>-stop_loss_pct</Code> or return &ge; <Code>take_profit_pct</Code>.
        </P>

        <H4 id="service-signal-lifecycle">Lifecycle Triggers</H4>
        <P>
          After processing all asset signals each tick, the probe checks two lifecycle conditions:
        </P>
        <ul className="list-disc list-inside text-sm text-white/70 space-y-1 mb-3 ml-4">
          <li><strong>Reproduce:</strong> <Code>roi &ge; benchmark_target_pct</Code> OR <Code>profit &ge; reproduce_target_dollars</Code> (probe has earned enough to spawn offspring via either percentage or absolute dollar threshold)</li>
          <li><strong>Die:</strong> <Code>max_drawdown &ge; death_drawdown_pct</Code> (probe has lost too much from peak)</li>
        </ul>

        <H3 id="service-tick-loop">Tick Loop</H3>
        <P>The GenesisController runs a continuous tick loop. Each tick executes these steps in order:</P>
        <ol className="list-decimal list-inside text-sm text-white/70 space-y-1 mb-3 ml-4">
          <li>Check circuit breaker (exit if active)</li>
          <li>Fetch market prices from the feed for all assets across live probes</li>
          <li>Push price/volume data to each probe via <Code>on_price_update()</Code></li>
          <li>Broadcast prices to WebSocket clients (every 5 ticks)</li>
          <li>Call <Code>probe.tick()</Code> on each live probe, collecting events</li>
          <li>Process death events (reclaim capital, auto-spawn if population low)</li>
          <li>Enforce max lifespan (force-kill probes exceeding the limit)</li>
          <li>Run evolution step (every <Code>reproduction_interval</Code> ticks)</li>
          <li>Broadcast simulation status (every 5 ticks) and probe updates (every 10 ticks)</li>
          <li>Capture fitness snapshots (every 25 ticks)</li>
          <li>Check circuit breaker threshold</li>
        </ol>

        <H3 id="service-capital-management">Capital Management</H3>
        <P>Capital flows through a reserve pool:</P>
        <ul className="list-disc list-inside text-sm text-white/70 space-y-1 mb-3 ml-4">
          <li><strong>Reserve Capital:</strong> Starts at <Code>max_capital</Code> ($10,000 default). Each probe spawned deducts <Code>seed_capital</Code> ($100) from reserve.</li>
          <li><strong>Active Capital:</strong> Sum of all live probe capitals. Probes gain/lose capital through trading.</li>
          <li><strong>On Death:</strong> Dead probe&rsquo;s remaining capital returns to reserve.</li>
          <li><strong>On Reproduction:</strong> Retired probe&rsquo;s capital returns to reserve. Offspring are funded at <Code>(reclaimed * capital_split) / num_offspring</Code>. Default <Code>capital_split = 0.45</Code>.</li>
          <li><strong>Circuit Breaker:</strong> If total capital drops by 30% from initial, all trading halts immediately.</li>
        </ul>

        <H3 id="service-market-feeds">Market Feeds</H3>
        <P>
          All market feeds implement the <Code>MarketFeed</Code> abstract class with two methods: <Code>get_tick(asset)</Code> and <Code>get_ticks(assets)</Code>.
        </P>

        <H4 id="service-feed-sim">Simulation Feed (GBM)</H4>
        <P>
          Generates synthetic prices using Geometric Brownian Motion. Each tick applies: <Code>price *= (1 + drift + volatility * N(0,1))</Code> where drift defaults to 0.0001 (slight upward bias) and volatility to 0.02 (2% standard deviation per tick). Volume is generated as <Code>base_volume * max(0.1, 1 + N(0, 0.5))</Code>. Each colony gets its own independent SimulationFeed instance, so prices diverge across colonies.
        </P>

        <H4 id="service-feed-jupiter">Jupiter Feed</H4>
        <P>
          Fetches live prices from the Jupiter DEX aggregator on Solana. Used in paper trading mode. Tracks API call count for rate monitoring.
        </P>

        <H3 id="service-api">REST API</H3>
        <P>
          The FastAPI server runs on port 8765 by default. All endpoints except health and strategies require an API key via the <Code>x-api-key</Code> header.
        </P>
        <Table
          headers={["Method", "Endpoint", "Description"]}
          rows={[
            ["GET", "/api/v1/health", "Service status + WS client count + active colony count"],
            ["GET", "/api/v1/status", "Latest colony status (backward compat)"],
            ["GET", "/api/v1/strategies", "List all available evolution strategies"],
            ["GET", "/api/v1/gene-registry", "Gene definitions, assets, and preset configs"],
            ["POST", "/api/v1/colonies/", "Create and start a new colony"],
            ["GET", "/api/v1/colonies/", "List all active colonies"],
            ["GET", "/api/v1/colonies/{id}", "Get specific colony status"],
            ["POST", "/api/v1/colonies/{id}/stop", "Stop a colony"],
            ["POST", "/api/v1/colonies/{id}/pause", "Pause a colony"],
            ["POST", "/api/v1/colonies/{id}/resume", "Resume a colony"],
            ["POST", "/api/v1/simulation/start", "Start colony (backward compat)"],
            ["POST", "/api/v1/simulation/stop", "Stop latest colony (backward compat)"],
            ["POST", "/api/v1/simulation/pause", "Pause latest colony"],
            ["POST", "/api/v1/simulation/resume", "Resume latest colony"],
            ["WS", "/ws", "WebSocket for real-time event streaming"],
          ]}
        />

        {/* ───────── EVOLUTIONARY ALGORITHMS ───────── */}
        <H2 id="evolution">Evolutionary Algorithms</H2>
        <P>
          The system supports four evolutionary algorithm strategies, selectable per colony. All strategies implement the <Code>EvolutionStrategy</Code> abstract base class and are auto-discovered at startup. New strategies can be added by dropping a single Python file into <Code>core/strategies/</Code> with zero registration boilerplate.
        </P>

        <H3 id="evo-strategy-pattern">Strategy Pattern</H3>
        <P>
          Every strategy must implement four methods:
        </P>
        <Table
          headers={["Method", "Purpose"]}
          rows={[
            ["name (property)", "Unique snake_case identifier (e.g. 'genetic_algorithm')"],
            ["label (property)", "Human-readable name for the UI"],
            ["initialize(probes, config)", "Called once after Gen-0 spawns. Set up internal state (velocities, distributions)."],
            ["evolve(probes, dead, config) -> EvolutionResult", "Called every reproduction_interval ticks. Returns genomes to spawn and probe IDs to retire."],
          ]}
        />
        <P>
          The <Code>EvolutionResult</Code> contains: <Code>offspring</Code> (list of new Genomes), <Code>retire_ids</Code> (probe IDs to archive), <Code>parent_map</Code> (maps offspring index to parent probe IDs for genealogy), and <Code>metadata</Code> (strategy-specific stats).
        </P>
        <P>
          Strategies never touch capital or probe lifecycle state. They produce a declarative result; genesis handles all the orchestration (closing positions, transferring price buffers, reclaiming capital, spawning offspring).
        </P>

        <H3 id="evo-fitness">Fitness Scoring</H3>
        <P>
          The composite fitness function used for selection across all strategies:
        </P>
        <CodeBlock title="Fitness Formula">{`fitness = ROI
       + (Sharpe * 0.3)
       - (MaxDrawdown * 2.0)
       - ActivityPenalty
       + WinBonus

Where:
  ActivityPenalty = max(0, (10 - num_trades) * 0.01)  // penalize inactivity
  WinBonus       = (win_rate - 0.5) * 0.1             // reward >50% win rate

If num_trades < 3:  fitness = ROI - 0.5  (harsh penalty for insufficient data)`}</CodeBlock>
        <P>
          Sharpe Ratio is computed as sample-standard-deviation Sharpe over per-trade returns: <Code>(mean_return - risk_free) / std_dev</Code>. Returns 0 if fewer than 2 trades.
        </P>

        <H3 id="evo-ga">Genetic Algorithm</H3>
        <P>The default strategy. Classic GA with these operators:</P>

        <H4 id="evo-ga-selection">Selection</H4>
        <P>
          Fitness-ranked selection: filter probes with &ge;3 trades and non-negative ROI, sort by fitness descending, take the top 30%. All selected parents reproduce with a mate chosen via tournament selection.
        </P>

        <H4 id="evo-ga-tournament">Tournament Selection (Mate)</H4>
        <P>
          For each reproducing parent, a mate is chosen via tournament selection: sample 3 random probes from the population (excluding the parent), return the one with highest fitness.
        </P>

        <H4 id="evo-ga-crossover">Uniform Crossover</H4>
        <P>
          For each evolvable gene: 50/50 coin flip assigns the value from parent A or parent B. Fixed/disabled genes always take parent A&rsquo;s value. Asset lists are merged from both parents, then sampled down to <Code>num_assets</Code>.
        </P>

        <H4 id="evo-ga-mutation">Gaussian Mutation</H4>
        <P>
          For each evolvable gene: with probability <Code>mutation_rate</Code> (default 0.20), add Gaussian noise scaled to <Code>mutation_strength * gene_range</Code> (default 0.15 * (max - min)). Asset mutation: 30% chance to swap one asset for a random different one from the available pool.
        </P>

        <H4 id="evo-ga-reproduction">Reproduction Flow</H4>
        <P>
          70% chance of sexual reproduction (crossover + mutation) and 30% chance of asexual (clone + mutation at 1.5&times; rate). Each parent produces <Code>child_count</Code> offspring (default 2). Children inherit generation = parent.generation + 1.
        </P>

        <Callout type="info">
          Default parameters: mutation_rate=0.20, mutation_strength=0.15, top_pct=0.30, child_count=2, min_trades=3.
        </Callout>

        <H3 id="evo-de">Differential Evolution</H3>
        <P>
          DE/rand/1/bin strategy. Operates on the worst half of the population each evolution step.
        </P>

        <H4 id="evo-de-trial">Trial Vector Formula</H4>
        <CodeBlock title="DE/rand/1/bin">{`For each target (worst 50% of population):
  Select 3 random distinct probes a, b, c from the rest

  For each gene i:
    mutant_i = a_i + F * (b_i - c_i)

  Binomial crossover with target:
    j_rand = random integer in [0, num_genes)
    For each gene i:
      if random() < CR  OR  i == j_rand:
        trial_i = mutant_i
      else:
        trial_i = target_i

Parameters: F = 0.8 (scaling factor), CR = 0.9 (crossover probability)
Minimum population: 4 probes`}</CodeBlock>
        <P>
          The worst half of the population is retired and replaced with trial vectors. Fixed/non-evolvable genes always keep the target&rsquo;s value.
        </P>

        <H3 id="evo-pso">Particle Swarm Optimization</H3>
        <P>
          Each probe is treated as a particle moving through gene-space. Velocities update based on personal best, global best, and inertia.
        </P>

        <H4 id="evo-pso-velocity">Velocity Update Formula</H4>
        <CodeBlock title="PSO Velocity Update">{`For each probe (particle):
  For each evolvable gene:
    v_new = w * v_old
          + c1 * r1 * (personal_best - current)
          + c2 * r2 * (global_best  - current)

    position_new = position_old + v_new

Parameters:
  w  = 0.7  (inertia weight)
  c1 = 1.5  (cognitive coefficient — personal best attraction)
  c2 = 1.5  (social coefficient — global best attraction)
  r1, r2 = independent random() in [0, 1]`}</CodeBlock>
        <P>
          PSO retires and respawns the entire population each evolution step. Price buffers are transferred from parent to offspring to avoid signal warmup delays. Velocity state is remapped from the old probe ID to the new one via <Code>remap_probe_id()</Code>.
        </P>

        <H3 id="evo-cmaes">CMA-ES</H3>
        <P>
          Covariance Matrix Adaptation Evolution Strategy. Uses the <Code>cmaes</Code> Python package with an ask-and-tell interface. Best suited for continuous optimization in parameter spaces under 100 dimensions (the system has 15 genes).
        </P>

        <H4 id="evo-cmaes-flow">Ask-Tell Flow</H4>
        <CodeBlock title="CMA-ES Ask-Tell">{`Initialize:
  mean   = centroid of Gen-0 population
  sigma  = 0.3 * mean(gene_ranges)
  bounds = [(min, max) for each evolvable gene]
  optimizer = CMA(mean, sigma, bounds, population_size)

Each evolution step (after first):
  1. TELL: Feed current population fitness to optimizer
     solutions = [(params_array, -fitness) for each probe]
     optimizer.tell(solutions)          # CMA-ES minimizes, so negate

  2. ASK: Sample new candidate solutions
     For each position in population:
       params = optimizer.ask()         # Returns numpy array
       Build Genome from params, fill non-evolvable genes from best probe
       Validate genome against bounds

  3. Retire all current probes, spawn new ones

First evolution step skips TELL (Gen-0 probes were random, not from ask()).`}</CodeBlock>

        <H3 id="evo-diversity">Diversity Management</H3>
        <P>
          Population diversity is measured as the average pairwise normalized Euclidean distance in gene space, plus a Jaccard distance term for asset overlap. The diversity metric ranges from 0.0 (identical) to ~1.0 (maximally diverse).
        </P>
        <P>
          When diversity drops below the threshold (default 0.10), diversity injection creates new genomes. The default mechanism prefers strongly-mutated copies of the best recently-dead probe (mutation rate 0.30, strength 0.25). If no dead probes exist, random Gen-0 genomes are created. Strategies can override this with their own diversity mechanism.
        </P>

        <H3 id="evo-multi-colony">Multi-Colony System</H3>
        <P>
          The ColonyManager allows multiple colonies to run simultaneously. Each colony has its own:
        </P>
        <ul className="list-disc list-inside text-sm text-white/70 space-y-1 mb-3 ml-4">
          <li>Evolution strategy instance (with its own internal state)</li>
          <li>GenesisController (tick loop, population, capital pool)</li>
          <li>Market feed (independent price paths in simulation mode)</li>
          <li>Database persistence (isolated by colony_id/run_id)</li>
          <li>Event handler (WebSocket messages tagged with colony_id)</li>
        </ul>
        <P>
          Colonies run as independent <Code>asyncio.Task</Code> instances. No threads or multiprocessing — the workload is I/O-bound (market feeds, DB writes, WebSocket broadcasts). The frontend filters WebSocket events by the selected colony and can switch between active colonies in real time.
        </P>

        {/* ───────── TRADE LOG ───────── */}
        <H2 id="trade-log">Trade Log</H2>
        <ComingSoon title="Trade Log" />

        {/* ───────── SETTINGS ───────── */}
        <H2 id="settings">Settings</H2>
        <ComingSoon title="Settings" />

        {/* Footer */}
        <div className="mt-16 pt-8 border-t border-white/10 text-center text-xs text-white/25">
          NEXUS Terminal Documentation
        </div>
        </div>
      </main>
    </div>
  );
}
