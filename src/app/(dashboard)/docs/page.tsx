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
          The Probes page is a real-time dashboard for running, monitoring, and analyzing autonomous evolutionary trading agents. Each &ldquo;probe&rdquo; is an independent trading entity with a genetic blueprint (genome) that defines its signal computation parameters, risk management rules, and lifecycle thresholds. Simulation uses synthetic data; paper mode observes Solana prices without signing transactions. Candidates evolve through evaluated selection and variation. Live trading is rejected.
        </P>
        <P>
          The system is powered by a Python FastAPI service (the Von Neumann service) that runs the tick loop, manages the probe lifecycle, and broadcasts events over WebSocket. The frontend receives events in real time and also polls Supabase for persistence.
        </P>

        <H3 id="probes-overview">Dashboard Overview</H3>
        <P>
          When you open the Probes page, the top section shows the simulation control bar and a set of summary metric cards.
        </P>
        <H4 id="probes-metric-cards">Metric Cards</H4>
        <P>Four summary cards, plus an optional API-usage card, display the colony&rsquo;s reported state:</P>
        <Table
          headers={["Card", "Value", "Secondary"]}
          rows={[
            ["Active Probes", "Count of live (non-DEAD) probes", "Last reported dead count, or explicitly labeled loaded-row count"],
            ["Generation", "Current generation number", "Current tick count"],
            ["Best Fitness", "Highest fitness among loaded active candidates (3 decimals)", "Population diversity metric"],
            ["Colony Capital", "Last valid total account equity, including reserve and owned positions", "Unavailable when current valuation cannot be confirmed"],
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
            ["Differential Evolution", "Paired current-window target/trial DE; even funded account count, at least eight."],
            ["Window-reset Swarm", "Normalized PSO variant with inertia and current-window social evidence."],
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
            ["Simulation", "Synthetic market prices via Geometric Brownian Motion. Authentication and persistence still require the configured services."],
            ["Paper Trade", "Live prices from Jupiter DEX aggregator on Solana. Real market conditions, no real capital."],
          ]}
        />

        <H4 id="probes-config-presets">Presets</H4>
        <P>Eight colony presets provide starting points. Examples:</P>
        <Table
          headers={["Preset", "Behavior"]}
          rows={[
            ["Default", "All 15 genes evolve freely across their full range. All configured assets available."],
            ["RSI Focus", "EMA and volume genes are fixed; only RSI + risk + lifecycle genes evolve."],
            ["Conservative Risk", "Tighter risk gene bounds (smaller positions, tighter stops). Max 1 open position."],
            ["Wide Exploration", "50-market-minute evaluation windows after readiness instead of 100; lower profit thresholds apply only to legacy self-reproduction."],
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
            ["Tick Interval", "1000ms", "Wall-clock pacing; does not change synthetic market time"],
            ["Mutation Rate", "0.20", "Probability of mutating each gene (GA)"],
            ["Evaluation Window", "100 market minutes", "Common candidate window after every candidate is ready"],
            ["Maximum Candidate Age", "none", "Market minutes after group readiness; early results remain in the group"],
            ["Max Probes", "50", "Funded evaluation account cap"],
            ["Search Seed", "0", "Exact integer text for reproducible search; independent of market seed"],
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
            ["Risk halted", "Explicit Recover with a confirmed current trip, or Stop; protection continues only while the worker is reachable"],
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
        <P>Candidates appear by birth generation with every recorded source link: clone parent, crossover parents, DE contributors, swarm particle/social sources or CMA distribution sources. Missing sources are labeled outside loaded history. Numerical ancestry does not mean sexual reproduction. The list avoids recursive expansion of a multi-parent graph.</P>

        <H3 id="probes-probe-detail">Probe Detail Dialog</H3>
        <P>
          A modal dialog with full details about a single probe.
        </P>
        <H4 id="probes-detail-header">Header</H4>
        <P>Probe name (cyan), state badge, birth-generation badge, and every recorded source ID. An open detail view follows new lifecycle updates.</P>
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
          A scrollable table of loaded persisted trades for the probe, showing: asset pair, open time, entry price, exit price, P&L (color-coded), and exit reason (TAKE_PROFIT, STOP_LOSS, SIGNAL_EXIT, PROBE_DYING, REPRODUCING).
        </P>

        <H3 id="probes-price-feed">Live Price Feed</H3>
        <P>
          A horizontal ticker strip below the controls showing real-time prices for all active assets. Each price pill displays the asset symbol, current price (with format adapting to magnitude), and a change indicator (up/down arrow with percentage). Only appears when a simulation is running and prices are streaming.
        </P>

        <H3 id="probes-websocket">Real-Time WebSocket</H3>
        <P>
          The page connects to the Python service using <Code>NEXT_PUBLIC_VN_WS_URL</Code>. Production requires an explicit secure WSS endpoint; development can use <Code>ws://localhost:8765/ws</Code>. The connection authenticates with the current Supabase session before receiving events, reconnects with bounded exponential backoff, and closes when the session changes or expires.
        </P>
        <P>
          Every WebSocket message includes a <Code>colony_id</Code> field so the frontend can filter events per colony when multiple colonies are running. Message types handled:
        </P>
        <Table
          headers={["Message Type", "Effect"]}
          rows={[
            ["probe_born", "Adds a new probe to the grid"],
            ["probe_update", "Updates metrics for an existing probe"],
            ["probe_dying / probe_reproducing", "Records transition intent; not final death"],
            ["probe_dead", "Applies final terminal balance, metrics, time and reason"],
            ["simulation_status", "Updates system status, generation, tick, active colonies list"],
            ["generation_complete", "Upserts acknowledged generation stats for the evolution chart"],
            ["price_update", "Updates the live price feed ticker"],
          ]}
        />
        <P>
          The WebSocket is read-only and carries events belonging to the signed-in user. Pause, resume, and stop use authenticated REST requests with an explicit colony ID. The selected colony is checked before its events update the display.
        </P>

        <H3 id="probes-data-persistence">Data Persistence</H3>
        <P>Five Supabase tables store all probe data, scoped per user via Row Level Security:</P>
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
          The frontend polls Supabase every 5 seconds as a fallback complement to WebSocket updates. Historical colony runs are browsable via the Colony Selector; loaded rows can be a subset of stored history. Generation numbers describe birth epochs, not ancestry depth. Completion requires sealed births and acknowledged terminal records for all members. New generation diversity excludes assets and uses the saved RMS numeric policy.
        </P>
        <P>
          Worker memory retains the latest 256 closed trades per probe, 500 dead probes and 100 generation-completion markers. Lifetime trade/death totals and online generation aggregates survive cache eviction; persisted historical rows are not deleted by these limits. Ancestry records every actual source, including numerical contributors. Older records created before explicit terminal acknowledgements are not automatically repaired. Saved history is not an executable recovery checkpoint.
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
        <P>Every gene has hard bounds, a type and a default. Configured ranges must fit those bounds. Fixed values, disabled defaults and equal-bound ranges are locked. Integer values are rounded half up before checking fast EMA &lt; slow EMA and stop loss &lt; take profit. Only active values can move to repair a relationship; incompatible locked controls are rejected before a run starts.</P>
        <P>The same deterministic validation applies to initialization and every evolutionary operator. Assets are unique supported pairs and their count matches the validated num_assets gene. Validation does not draw random values. Mutation noise uses the configured active range.</P>

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
            ["position_size_pct", "Risk", "FLOAT", "0.05", "0.90", "0.75"],
            ["stop_loss_pct", "Risk", "FLOAT", "0.01", "0.10", "0.03"],
            ["take_profit_pct", "Risk", "FLOAT", "0.03", "0.20", "0.07"],
            ["max_open_positions", "Risk", "INT", "1", "4", "1"],
            ["timeframe_minutes", "Lifecycle", "INT", "5", "60", "15"],
            ["benchmark_target_pct", "Lifecycle", "FLOAT", "0.03", "0.15", "0.08"],
            ["reproduce_target_dollars", "Lifecycle", "FLOAT", "2.0", "50.0", "10.0"],
            ["death_drawdown_pct", "Lifecycle", "FLOAT", "0.10", "0.35", "0.20"],
            ["num_assets", "Lifecycle", "INT", "1", "3", "2"],
          ]}
        />

        <H3 id="service-probe-lifecycle">Probe Lifecycle</H3>
        <P>Candidates begin BORN, receive funding, then observe shared completed-candle history. TRADING means a candidate has entered its trading lifecycle; it can temporarily hold no positions. REPRODUCING and DYING are transition intentions, not confirmed terminal records. Only an acknowledged probe_dead event completes retirement with final capital, metrics, timestamp and reason.</P>
        <P>Built-in optimizers evaluate the entire common-window group, including candidates that never traded. Selected sources are distinguished from culled candidates. Profit-triggered reproduction applies to legacy/custom strategies; risk, age and explicit optimizer retirement have distinct reasons.</P>

        <H3 id="service-signal-computation">Signal Computation</H3>
        <P>Signals use completed timestamped candles aggregated to each genome&rsquo;s timeframe, independent of polling speed. A shared history covers the configured asset universe, including newly selected assets. Entries wait until every candidate has valid RSI, EMA and volume inputs. Decisions execute only on a subsequent eligible quote; quote marks do not become indicator candles. Protective stops and take profit still run on each valid quote.</P>

        <H4 id="service-signal-rsi">RSI (Relative Strength Index)</H4>
        <P>The implemented RSI uses rolling average gains and losses over rsi_period completed-candle differences, requiring period + 1 closes. It is not Wilder&rsquo;s recursive smoothing. An entirely flat window is neutral at 50. The chosen convention is explicit so benchmarks can compare the same indicator.</P>

        <H4 id="service-signal-ema">EMA (Exponential Moving Average)</H4>
        <P>
          Two EMAs: fast (<Code>ema_fast</Code> period) and slow (<Code>ema_slow</Code> period). Smoothing factor: <Code>k = 2 / (period + 1)</Code>. Update: <Code>ema = price * k + ema * (1 - k)</Code>.
        </P>

        <H4 id="service-signal-entry">Entry Signal</H4>
        <P>All three conditions must be true simultaneously:</P>
        <ol className="list-decimal list-inside text-sm text-white/70 space-y-1 mb-3 ml-4">
          <li><strong>RSI Oversold:</strong> <Code>RSI &lt; rsi_oversold</Code> (below the configured threshold)</li>
          <li><strong>EMA Bullish Cross:</strong> <Code>ema_fast &gt; ema_slow</Code> (upward momentum)</li>
          <li><strong>Volume Confirmation:</strong> current volume &gt; <Code>volume_threshold</Code> &times; 20-candle average volume</li>
        </ol>

        <H4 id="service-signal-exit">Exit Signal</H4>
        <P>Either condition triggers a signal exit:</P>
        <ol className="list-decimal list-inside text-sm text-white/70 space-y-1 mb-3 ml-4">
          <li><Code>RSI &gt; rsi_overbought</Code> (above the configured threshold), OR</li>
          <li><Code>ema_fast &lt; ema_slow</Code> (bearish crossover)</li>
        </ol>

        <H4 id="service-signal-sltp">Stop Loss / Take Profit</H4>
        <P>
          Checked every tick for each open position. Computes return: <Code>(current_price - entry_price) / entry_price</Code>. Closes the position if return &le; <Code>-stop_loss_pct</Code> or return &ge; <Code>take_profit_pct</Code>.
        </P>

        <H4 id="service-signal-lifecycle">Lifecycle Triggers</H4>
        <P>Drawdown and configured age limits can terminate a candidate early. Its final cash and score stay in its original evaluation slot until the common deadline. Built-in solvers do not let profit-triggered self-reproduction or diversity injection change the active comparison group. Profit thresholds remain legacy controls for custom strategies.</P>
        <H3 id="service-tick-loop">Tick Loop</H3>
        <P>The controller obtains fresh quotes for the configured universe, applies protective position management, checks whole-account loss and updates completed-candle history. It then advances warmup or the common evaluation deadline, permits entries only when the group is ready and risk is unlocked, and publishes acknowledged state. Early deaths do not shrink the group passed to an optimizer. Invalid/stale observations cannot fabricate a score or a liquidation price.</P>
        <P>A risk halt blocks entries and new candidates while protective management continues on valid data. Explicit recovery requires current marks and the matching saved trip; ordinary resume does not clear the halt. Pause, halt, stop or failure aborts the unfinished group without an optimizer update. Recovery/resume starts fresh funded accounts and an optimizer epoch.</P>

        <H3 id="service-capital-management">Capital Management</H3>
        <P>Capital flows through a reserve pool:</P>
        <ul className="list-disc list-inside text-sm text-white/70 space-y-1 mb-3 ml-4">
          <li><strong>Reserve Capital:</strong> Starts at <Code>max_capital</Code> ($10,000 default). Each probe spawned deducts <Code>seed_capital</Code> ($100) from reserve.</li>
          <li><strong>Active Capital:</strong> Cash plus marked open positions still owned by registered probes, including records awaiting reconciliation after a failure. Probes gain/lose capital through trading.</li>
          <li><strong>On Death:</strong> After the explicit terminal write succeeds, remaining cash is transferred atomically from the owned candidate to reserve. A failed write or accounting step preserves ownership for reconciliation.</li>
          <li><strong>On Reproduction:</strong> Each offspring receives the configured <Code>seed_capital</Code> evaluation budget. The complete replacement must fit the population limit and be funded by reserve plus retirement proceeds before any parent is retired. Profits and losses flow to reserve. An unaffordable or invalid replacement stops execution for review; candidates are never silently omitted or underfunded.</li>
          <li><strong>Circuit Breaker:</strong> The configured whole-account loss threshold blocks entries and new candidates while protective management continues on fresh data. Explicit recovery is required.</li>
        </ul>

        <H3 id="service-market-feeds">Market Feeds</H3>
        <P>
          All market feeds implement the <Code>MarketFeed</Code> abstract class with quote methods <Code>get_tick(asset)</Code> and <Code>get_ticks(assets)</Code>, plus <Code>get_candles</Code> for completed history.
        </P>

        <H4 id="service-feed-sim">Simulation Feed</H4>
        <P>Synthetic prices use a seeded positive geometric model with an explicit one-minute default market step. Separate private streams for each asset make the market path independent of optimizer draws, requested asset order and wall-clock playback. Equal market seeds and model settings produce the same path across colonies. Synthetic volume and endpoint candles are uncalibrated; they are useful for mechanics tests, not evidence of profitability.</P>

        <H4 id="service-feed-jupiter">Jupiter Feed</H4>
        <P>
          Paper mode uses Jupiter quotes, RPC source-time validation, and Birdeye completed candle history. These provider credentials and quotas must be configured and verified before a hosted paper run. The API counter is diagnostic and does not estimate total provider cost.
        </P>

        <H3 id="service-api">REST API</H3>
        <P>
          The FastAPI server runs on port 8765 by default. Colony endpoints require the signed-in user&rsquo;s Supabase access token in the <Code>Authorization: Bearer</Code> header. The service verifies the token and checks colony ownership. Health, strategies, and the gene registry are public metadata; shared browser API keys are not used.
        </P>
        <Table
          headers={["Method", "Endpoint", "Description"]}
          rows={[
            ["GET", "/api/v1/health", "Basic service liveness"],
            ["GET", "/api/v1/status", "Latest owned colony (compatibility); prefer an explicit colony ID"],
            ["GET", "/api/v1/strategies", "List all available evolution strategies"],
            ["GET", "/api/v1/gene-registry", "Gene definitions, assets, and preset configs"],
            ["POST", "/api/v1/colonies/", "Validate, persist, and prepare a new colony before confirming startup"],
            ["GET", "/api/v1/colonies/", "List the authenticated user's in-memory colonies, including retained terminal states"],
            ["GET", "/api/v1/colonies/{id}", "Get an owned colony's status"],
            ["POST", "/api/v1/colonies/{id}/stop", "Stop a colony"],
            ["POST", "/api/v1/colonies/{id}/pause", "Pause a colony"],
            ["POST", "/api/v1/colonies/{id}/resume", "Resume a paused colony"],
            ["POST", "/api/v1/colonies/{id}/recover", "Recover a confirmed risk halt with its trip ID and fresh marks"],
            ["POST", "/api/v1/simulation/start", "Start colony (backward compat)"],
            ["POST", "/api/v1/simulation/stop", "Retired; returns 410, use /colonies/{id}/stop"],
            ["POST", "/api/v1/simulation/pause", "Retired; returns 410, use /colonies/{id}/pause"],
            ["POST", "/api/v1/simulation/resume", "Retired; returns 410, use /colonies/{id}/resume"],
            ["WS", "/ws", "Authenticate first, then receive only the user's events"],
          ]}
        />

        <P>
          Colony states are <Code>starting</Code>, <Code>running</Code>, <Code>paused</Code>, <Code>risk_halted</Code>, <Code>stopped</Code>, and <Code>failed</Code>. Invalid launch settings return 422 before creating a colony; live trading is rejected. Preparation and persistence failures return 503 with a safe error code and colony ID. An invalid control transition returns 409. A successful launch means the initial population and strategy were prepared; it does not establish trading profitability or readiness for real funds.
        </P>
        <P>
          Stopped and failed colonies retain paper-position records for reconciliation. The status reports whether failure information was saved and whether reconciliation is required. A control request may finish after the caller disconnects, so refresh the colony status before retrying an uncertain result. Failed reads show an error and preserve the last successful result; missing worker status is shown as unavailable.
        </P>

        {/* ───────── EVOLUTIONARY ALGORITHMS ───────── */}
        <H2 id="evolution">Evolutionary Algorithms</H2>
        <P>
          The system supports four evolutionary algorithm strategies, selectable per colony. All strategies implement the <Code>EvolutionStrategy</Code> abstract base class and are auto-discovered at startup. New strategies can be added by dropping a single Python file into <Code>core/strategies/</Code> with zero registration boilerplate.
        </P>

        <H3 id="evo-strategy-pattern">Evaluation Contract</H3>
        <P>Every built-in optimizer evaluates a fixed group over a common market-minute window, starting only after all candidates have current indicator inputs. Candidate identities and actual phenotypes remain bound to that group. Missing, duplicate, changed, partial or nonfinite evidence is rejected. Each next group receives the same configured account budgets after capacity and funding preflight. Current result summaries are diagnostic; durable executable restart checkpoints remain a separate requirement.</P>
        <H3 id="evo-fitness">Fitness Scoring</H3>
        <CodeBlock title="Provisional fitness">{`fitness = portfolio ROI - 2 * observed historical maximum drawdown`}</CodeBlock>
        <P>Portfolio equity includes cash and marked open positions. Historical drawdown does not disappear after recovery. This is a provisional ranking heuristic with an uncalibrated drawdown weight. Sharpe is a separate nullable diagnostic from fixed-time portfolio-equity returns, not per-trade returns, and is excluded from selection. Missing/insufficient/zero-variance evidence is reported instead of an invented ratio.</P>
        <H3 id="evo-ga">Genetic Algorithm</H3>
        <H4 id="evo-ga-selection">Selection</H4>
        <P>A complete group produces exactly the configured number of children, including populations of two. Negative scores and zero-trade windows remain valid mechanical evidence. There is no top-30% or three-trade parent gate.</P>
        <H4 id="evo-ga-tournament">Tournament Selection</H4>
        <P>Parents are chosen from the completed group by tournaments of up to three. A mate comes from the same group excluding the chosen parent. An untested candidate cannot be treated as a proven winner.</P>
        <H4 id="evo-ga-crossover">Uniform Crossover</H4>
        <P>Active genes can inherit either parent&rsquo;s value. Fixed and disabled controls remain locked. Ordered asset preferences are merged and the actual phenotype is validated.</P>
        <H4 id="evo-ga-mutation">Gaussian Mutation</H4>
        <P>Active coordinates receive configured-range Gaussian perturbations at the requested rate. Asset swaps are separate categorical operations. Validation preserves fixed controls and integer relationships.</P>
        <H4 id="evo-ga-reproduction">Reproduction Flow</H4>
        <P>Variation chooses crossover plus mutation or cloning plus mutation, filling exactly one next group. Only actual crossover records a mate; clone/fallback ancestry records its actual source. Numerical optimizer sources are not described as sexual mates.</P>
        <H3 id="evo-de">Differential Evolution</H3>
        <P>DE/rand/1/bin compares each trial with a funded target clone over the same current market window. The configured account count is even and at least eight: four or more target slots and an equal number of trials. Bootstrap selects incumbents from an initial random evaluated group.</P>
        <H4 id="evo-de-trial">Trial and Selection</H4>
        <CodeBlock title="Paired DE">{`donor = a + 0.8 * (b - c)
trial = binomial_crossover(target, donor, probability=0.9)
force at least one ACTIVE donor coordinate
project trial into the configured valid phenotype

Evaluate target and trial on the SAME market window.
Keep trial only if trial.fitness > target.fitness; ties keep target.
Freeze all winners before sampling the next donors.`}</CodeBlock>
        <P>Historical target scores do not compete with current trials. Losing trials do not become next-generation donors. Source metadata identifies target, base and positive/negative difference contributors.</P>
        <H3 id="evo-pso">Window-reset Swarm (PSO variant)</H3>
        <P>The swarm uses normalized active coordinates. Best scores reset on every new market window because old and new regimes are different objectives. With one observation per particle per window, current position is its personal best and cognitive attraction is zero. This is an explicit variant, not textbook cumulative-memory PSO.</P>
        <H4 id="evo-pso-velocity">Movement</H4>
        <CodeBlock title="Window-reset social movement">{`proposal = current + 0.7 * velocity
                   + 1.5 * random_vector * (current_window_best - current)
child = decode_and_validate(clip_to_unit_interval(proposal))
next_velocity = encode(child) - current`}</CodeBlock>
        <P>Initial private momentum avoids an all-zero first move. Actual repaired displacement is retained, with one particle state per fresh evaluation account. Fixed dimensions are omitted; integer projection can still cause stagnation and needs further benchmarking.</P>
        <H3 id="evo-cmaes">CMA-ES</H3>
        <P>The installed cmaes package operates over effective active unit coordinates with initial sigma 0.3 and bounds [0,1]. Integer/coupled constraints are applied through the shared phenotype validator; asset identities use explicit inheritance and resize.</P>
        <H4 id="evo-cmaes-flow">Ask-Tell Flow</H4>
        <P>The random bootstrap defines an initial normalized mean. Each later asked array is copied and bound to its actual candidate phenotype and account ID. A complete group tells the optimizer those original arrays with negated fitness; repaired genomes are never reconstructed as ask vectors. Early deaths retain their slots. Interrupted groups are discarded without tell. Zero active dimensions yields a full clone group.</P>
        <H3 id="evo-diversity">Diversity and Reproducibility</H3>
        <P>Current-population diversity uses mean pairwise normalized gene/asset distance; it is not a percentage and can exceed one. New records with lifecycle policy acknowledged-terminal-sealed-generations-v1 use RMS pairwise numeric distance over global registry ranges, excluding categorical assets and calculated independently of recent-history retention. Older records without this policy retain their original semantics. The two statistics describe different things.</P>
        <P>Search seeds are exact decimal strings, independent of the synthetic market seed. Each controller and optimizer owns private versioned streams. Matching seed, configuration, software and input data reproduce search from the beginning; this does not restore a stopped process&rsquo;s executable state. UUIDs and display names are not part of the economic replay comparison.</P>
        <Callout type="warning">Passing numerical and accounting tests does not establish trading quality. Realistic fees, slippage, immutable datasets, multiple-testing controls, durable recovery and hosted worker acceptance are still required before a paper evaluation or live design.</Callout>

        <H3 id="evo-multi-colony">Multi-Colony System</H3>
        <P>
          The ColonyManager allows multiple colonies to run simultaneously. Each colony has its own:
        </P>
        <ul className="list-disc list-inside text-sm text-white/70 space-y-1 mb-3 ml-4">
          <li>Evolution strategy instance (with its own internal state)</li>
          <li>GenesisController (tick loop, population, capital pool)</li>
          <li>Private market feed (identical paths for identical market seed/settings)</li>
          <li>Database persistence (isolated by colony_id/run_id)</li>
          <li>Event handler (WebSocket messages tagged with colony_id)</li>
        </ul>
        <P>
          Colonies run as independent <Code>asyncio.Task</Code> instances. Blocking database writes are dispatched through asyncio.to_thread while market and WebSocket work is asynchronous; optimizer computation still needs resource budgeting. The frontend filters WebSocket events by the selected colony and can switch between active colonies in real time.
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
