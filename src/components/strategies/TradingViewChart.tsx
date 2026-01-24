"use client";

import * as React from "react";

type TradingViewChartProps = {
  symbol?: string;
  interval?: string;
  theme?: "light" | "dark";
  height?: number;
  showToolbar?: boolean;
};

/**
 * TradingView Advanced Chart Widget
 * 
 * This component uses TradingView's official embeddable widget.
 * Documentation: https://www.tradingview.com/widget/advanced-chart/
 * 
 * Note: TradingView does not provide a public API for programmatic backtesting.
 * Backtesting is done through Pine Script on their platform.
 * This widget is for chart visualization only.
 */
export function TradingViewChart({
  symbol = "BINANCE:BTCUSDT",
  interval = "60",
  theme = "dark",
  height = 500,
  showToolbar = true,
}: TradingViewChartProps) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const scriptRef = React.useRef<HTMLScriptElement | null>(null);

  React.useEffect(() => {
    if (!containerRef.current) return;

    // Clear previous widget
    containerRef.current.innerHTML = "";

    // Create widget container
    const widgetContainer = document.createElement("div");
    widgetContainer.className = "tradingview-widget-container";
    widgetContainer.style.height = "100%";
    widgetContainer.style.width = "100%";

    const widgetDiv = document.createElement("div");
    widgetDiv.className = "tradingview-widget-container__widget";
    widgetDiv.style.height = "calc(100% - 32px)";
    widgetDiv.style.width = "100%";

    widgetContainer.appendChild(widgetDiv);
    containerRef.current.appendChild(widgetContainer);

    // Create and append the TradingView script
    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.type = "text/javascript";
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: symbol,
      interval: interval,
      timezone: "Etc/UTC",
      theme: theme,
      style: "1",
      locale: "en",
      enable_publishing: false,
      backgroundColor: theme === "dark" ? "rgba(10, 10, 15, 1)" : "rgba(255, 255, 255, 1)",
      gridColor: theme === "dark" ? "rgba(0, 255, 245, 0.06)" : "rgba(0, 0, 0, 0.06)",
      hide_top_toolbar: !showToolbar,
      hide_legend: false,
      save_image: false,
      calendar: false,
      hide_volume: false,
      support_host: "https://www.tradingview.com",
      studies: [
        "STD;RSI",
        "STD;MACD",
      ],
    });

    widgetContainer.appendChild(script);
    scriptRef.current = script;

    return () => {
      if (containerRef.current) {
        containerRef.current.innerHTML = "";
      }
    };
  }, [symbol, interval, theme, showToolbar]);

  return (
    <div 
      ref={containerRef} 
      style={{ height: `${height}px`, width: "100%" }}
      className="rounded-lg overflow-hidden border border-[#00fff5]/20"
    />
  );
}

/**
 * TradingView Symbol Info Widget
 * Shows ticker info for a symbol
 */
export function TradingViewTicker({ symbol = "BINANCE:BTCUSDT" }: { symbol?: string }) {
  const containerRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!containerRef.current) return;

    containerRef.current.innerHTML = "";

    const widgetContainer = document.createElement("div");
    widgetContainer.className = "tradingview-widget-container";

    const widgetDiv = document.createElement("div");
    widgetDiv.className = "tradingview-widget-container__widget";

    widgetContainer.appendChild(widgetDiv);
    containerRef.current.appendChild(widgetContainer);

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-symbol-info.js";
    script.type = "text/javascript";
    script.async = true;
    script.innerHTML = JSON.stringify({
      symbol: symbol,
      width: "100%",
      locale: "en",
      colorTheme: "dark",
      isTransparent: true,
    });

    widgetContainer.appendChild(script);

    return () => {
      if (containerRef.current) {
        containerRef.current.innerHTML = "";
      }
    };
  }, [symbol]);

  return <div ref={containerRef} className="w-full" />;
}

/**
 * TradingView Technical Analysis Widget
 * Shows technical analysis summary
 */
export function TradingViewAnalysis({ 
  symbol = "BINANCE:BTCUSDT",
  interval = "1h"
}: { 
  symbol?: string;
  interval?: string;
}) {
  const containerRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!containerRef.current) return;

    containerRef.current.innerHTML = "";

    const widgetContainer = document.createElement("div");
    widgetContainer.className = "tradingview-widget-container";

    const widgetDiv = document.createElement("div");
    widgetDiv.className = "tradingview-widget-container__widget";

    widgetContainer.appendChild(widgetDiv);
    containerRef.current.appendChild(widgetContainer);

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js";
    script.type = "text/javascript";
    script.async = true;
    script.innerHTML = JSON.stringify({
      interval: interval,
      width: "100%",
      isTransparent: true,
      height: "100%",
      symbol: symbol,
      showIntervalTabs: true,
      displayMode: "single",
      locale: "en",
      colorTheme: "dark",
    });

    widgetContainer.appendChild(script);

    return () => {
      if (containerRef.current) {
        containerRef.current.innerHTML = "";
      }
    };
  }, [symbol, interval]);

  return <div ref={containerRef} className="w-full h-[400px]" />;
}
