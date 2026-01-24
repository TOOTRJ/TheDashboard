export type DateRangeKey = "7d" | "30d" | "90d";

export type TimeSeriesPoint = {
  date: string;
  value: number;
};

export type CryptoPricePoint = {
  date: string;
  btc: number;
  eth: number;
  sol: number;
};

export type HoldingData = {
  symbol: string;
  name: string;
  amount: number;
  value: number;
  change24h: number;
  color: string;
};

export type TradeType = "Buy" | "Sell" | "Swap";
export type TradeStatus = "Completed" | "Pending" | "Failed";

export type TradeItem = {
  id: string;
  timestamp: string;
  type: TradeType;
  asset: string;
  amount: number;
  price: number;
  total: number;
  status: TradeStatus;
  txHash: string;
  wallet: string;
};

export type KpiSnapshot = {
  title: string;
  value: number;
  formattedValue: string;
  change: number;
  trend: TimeSeriesPoint[];
  isPositive: boolean;
  icon: string;
};

const dateRangeOptions = [
  { label: "Last 7 days", value: "7d" },
  { label: "Last 30 days", value: "30d" },
  { label: "Last 90 days", value: "90d" },
] as const;

const cryptoAssets = [
  { symbol: "BTC", name: "Bitcoin", color: "#f7931a" },
  { symbol: "ETH", name: "Ethereum", color: "#627eea" },
  { symbol: "SOL", name: "Solana", color: "#00fff5" },
  { symbol: "AVAX", name: "Avalanche", color: "#e84142" },
  { symbol: "MATIC", name: "Polygon", color: "#8247e5" },
  { symbol: "LINK", name: "Chainlink", color: "#375bd2" },
  { symbol: "UNI", name: "Uniswap", color: "#ff00ff" },
  { symbol: "AAVE", name: "Aave", color: "#b6509e" },
];

const walletAddresses = [
  "0x7a3d...8f2e",
  "0x4b9c...1a3d",
  "0x2e8f...9c4b",
  "0x9d1a...3e7f",
  "0x5f2c...8d1b",
];

const tradeTypes: TradeType[] = ["Buy", "Sell", "Swap"];
const tradeStatuses: TradeStatus[] = ["Completed", "Pending", "Failed"];

function seededRandom(seed: number) {
  let value = seed;
  return () => {
    value = (value * 16807) % 2147483647;
    return (value - 1) / 2147483646;
  };
}

const random = seededRandom(42);

function toIsoDate(date: Date) {
  return date.toISOString().slice(0, 10);
}

function addDays(date: Date, days: number) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function generateSeries(days: number, start: number, volatility: number, trend: number) {
  const today = new Date();
  const startDate = addDays(today, -days + 1);
  const series: TimeSeriesPoint[] = [];
  let current = start;

  for (let i = 0; i < days; i += 1) {
    const noise = 1 + (random() - 0.5) * volatility;
    current = Math.max(0, current * trend * noise);
    series.push({
      date: toIsoDate(addDays(startDate, i)),
      value: Math.round(current * 100) / 100,
    });
  }

  return series;
}

function generateCryptoPriceSeries(days: number): CryptoPricePoint[] {
  const today = new Date();
  const startDate = addDays(today, -days + 1);
  const series: CryptoPricePoint[] = [];
  
  let btcPrice = 94500;
  let ethPrice = 3200;
  let solPrice = 185;

  for (let i = 0; i < days; i += 1) {
    btcPrice = btcPrice * (1 + (random() - 0.48) * 0.04);
    ethPrice = ethPrice * (1 + (random() - 0.48) * 0.05);
    solPrice = solPrice * (1 + (random() - 0.48) * 0.06);

    series.push({
      date: toIsoDate(addDays(startDate, i)),
      btc: Math.round(btcPrice),
      eth: Math.round(ethPrice * 100) / 100,
      sol: Math.round(solPrice * 100) / 100,
    });
  }

  return series;
}

// Portfolio value starts at ~$125k and trends up with crypto volatility
const portfolioSeries = generateSeries(90, 125000, 0.08, 1.004);

// Total P&L series
const pnlSeries = generateSeries(90, 18500, 0.15, 1.002);

// Win rate series (percentage)
const winRateSeries = generateSeries(90, 64, 0.08, 1.0001).map(
  (point) => ({
    ...point,
    value: Math.min(85, Math.max(45, point.value)),
  })
);

// Active positions series
const positionsSeries = generateSeries(90, 12, 0.3, 1.001).map(
  (point) => ({
    ...point,
    value: Math.round(Math.max(3, Math.min(25, point.value))),
  })
);

// Crypto prices
const cryptoPriceSeries = generateCryptoPriceSeries(90);

function sliceRange<T extends { date: string }>(series: T[], range: DateRangeKey) {
  const days = range === "7d" ? 7 : range === "30d" ? 30 : 90;
  return series.slice(-days);
}

function percentChange(current: number, previous: number) {
  if (previous === 0) return 0;
  return ((current - previous) / previous) * 100;
}

function generateHoldings(): HoldingData[] {
  return [
    { symbol: "BTC", name: "Bitcoin", amount: 0.85, value: 80325, change24h: 2.4, color: "#f7931a" },
    { symbol: "ETH", name: "Ethereum", amount: 12.5, value: 40000, change24h: -1.2, color: "#627eea" },
    { symbol: "SOL", name: "Solana", amount: 145, value: 26825, change24h: 5.8, color: "#00fff5" },
    { symbol: "AVAX", name: "Avalanche", amount: 320, value: 12800, change24h: 3.1, color: "#e84142" },
    { symbol: "LINK", name: "Chainlink", amount: 450, value: 9000, change24h: -0.5, color: "#375bd2" },
    { symbol: "UNI", name: "Uniswap", amount: 280, value: 3920, change24h: 1.8, color: "#ff00ff" },
  ];
}

function generateTxHash(): string {
  const chars = "0123456789abcdef";
  let hash = "0x";
  for (let i = 0; i < 8; i++) {
    hash += chars[Math.floor(random() * chars.length)];
  }
  hash += "...";
  for (let i = 0; i < 4; i++) {
    hash += chars[Math.floor(random() * chars.length)];
  }
  return hash;
}

function generateTrades(count: number): TradeItem[] {
  const now = new Date();
  return Array.from({ length: count }).map((_, index) => {
    const daysAgo = Math.floor(random() * 45);
    const hoursAgo = Math.floor(random() * 20);
    const timestamp = new Date(now);
    timestamp.setDate(now.getDate() - daysAgo);
    timestamp.setHours(now.getHours() - hoursAgo);

    const asset = cryptoAssets[Math.floor(random() * cryptoAssets.length)];
    const type = tradeTypes[Math.floor(random() * tradeTypes.length)];
    const status = random() > 0.1 ? "Completed" : random() > 0.5 ? "Pending" : "Failed";
    
    const prices: Record<string, number> = {
      BTC: 94500 + (random() - 0.5) * 4000,
      ETH: 3200 + (random() - 0.5) * 300,
      SOL: 185 + (random() - 0.5) * 30,
      AVAX: 40 + (random() - 0.5) * 8,
      MATIC: 0.95 + (random() - 0.5) * 0.2,
      LINK: 20 + (random() - 0.5) * 4,
      UNI: 14 + (random() - 0.5) * 3,
      AAVE: 280 + (random() - 0.5) * 50,
    };
    
    const price = prices[asset.symbol] ?? 100;
    const amount = asset.symbol === "BTC" 
      ? Math.round(random() * 0.5 * 1000) / 1000
      : asset.symbol === "ETH"
        ? Math.round(random() * 5 * 100) / 100
        : Math.round(random() * 100 * 10) / 10;
    
    const total = Math.round(amount * price * 100) / 100;

    return {
      id: `tx_${index + 1}`,
      timestamp: timestamp.toISOString(),
      type,
      asset: asset.symbol,
      amount,
      price: Math.round(price * 100) / 100,
      total,
      status,
      txHash: generateTxHash(),
      wallet: walletAddresses[Math.floor(random() * walletAddresses.length)],
    };
  });
}

const tradeFeed = generateTrades(60).sort((a, b) =>
  a.timestamp < b.timestamp ? 1 : -1
);

export function getDateRangeOptions() {
  return dateRangeOptions;
}

export function getPortfolioSeries(range: DateRangeKey) {
  return sliceRange(portfolioSeries, range);
}

export function getPnlSeries(range: DateRangeKey) {
  return sliceRange(pnlSeries, range);
}

export function getWinRateSeries(range: DateRangeKey) {
  return sliceRange(winRateSeries, range);
}

export function getPositionsSeries(range: DateRangeKey) {
  return sliceRange(positionsSeries, range);
}

export function getCryptoPriceSeries(range: DateRangeKey) {
  return sliceRange(cryptoPriceSeries, range);
}

export function getHoldings() {
  return generateHoldings();
}

export function getHoldingsDistribution() {
  const holdings = generateHoldings();
  return holdings.map(h => ({
    name: h.symbol,
    value: h.value,
    color: h.color,
  }));
}

export function getTradeFeed(range: DateRangeKey) {
  const days = range === "7d" ? 7 : range === "30d" ? 30 : 90;
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - days);
  return tradeFeed.filter((item) => new Date(item.timestamp) >= cutoff);
}

export function getKpiSnapshots(range: DateRangeKey) {
  const portfolioSlice = sliceRange(portfolioSeries, range);
  const portfolioPrev = sliceRange(portfolioSeries, range === "7d" ? "30d" : "90d");
  const pnlSlice = sliceRange(pnlSeries, range);
  const pnlPrev = sliceRange(pnlSeries, range === "7d" ? "30d" : "90d");
  const winRateSlice = sliceRange(winRateSeries, range);
  const winRatePrev = sliceRange(winRateSeries, range === "7d" ? "30d" : "90d");
  const positionsSlice = sliceRange(positionsSeries, range);
  const positionsPrev = sliceRange(positionsSeries, range === "7d" ? "30d" : "90d");

  const portfolioValue = portfolioSlice.at(-1)?.value ?? 0;
  const portfolioPrevValue = portfolioPrev.at(-portfolioSlice.length)?.value ?? portfolioValue;
  
  const pnlValue = pnlSlice.at(-1)?.value ?? 0;
  const pnlPrevValue = pnlPrev.at(-pnlSlice.length)?.value ?? pnlValue;
  
  const winRateValue = winRateSlice.at(-1)?.value ?? 0;
  const winRatePrevValue = winRatePrev.at(-winRateSlice.length)?.value ?? winRateValue;
  
  const positionsValue = positionsSlice.at(-1)?.value ?? 0;
  const positionsPrevValue = positionsPrev.at(-positionsSlice.length)?.value ?? positionsValue;

  return [
    {
      title: "Portfolio Value",
      value: portfolioValue,
      formattedValue: `$${Math.round(portfolioValue).toLocaleString("en-US")}`,
      change: percentChange(portfolioValue, portfolioPrevValue),
      trend: portfolioSlice.slice(-14),
      isPositive: portfolioValue >= portfolioPrevValue,
      icon: "wallet",
    },
    {
      title: "Total P&L",
      value: pnlValue,
      formattedValue: `+$${Math.round(pnlValue).toLocaleString("en-US")}`,
      change: percentChange(pnlValue, pnlPrevValue),
      trend: pnlSlice.slice(-14),
      isPositive: pnlValue >= pnlPrevValue,
      icon: "trending-up",
    },
    {
      title: "Win Rate",
      value: winRateValue,
      formattedValue: `${winRateValue.toFixed(1)}%`,
      change: percentChange(winRateValue, winRatePrevValue),
      trend: winRateSlice.slice(-14),
      isPositive: winRateValue >= winRatePrevValue,
      icon: "target",
    },
    {
      title: "Active Positions",
      value: positionsValue,
      formattedValue: positionsValue.toString(),
      change: percentChange(positionsValue, positionsPrevValue),
      trend: positionsSlice.slice(-14),
      isPositive: true,
      icon: "layers",
    },
  ] satisfies KpiSnapshot[];
}

export function searchTradeFeed(items: TradeItem[], query: string) {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed) return items;
  return items.filter(
    (item) =>
      item.asset.toLowerCase().includes(trimmed) ||
      item.type.toLowerCase().includes(trimmed) ||
      item.txHash.toLowerCase().includes(trimmed)
  );
}

// Market data for ticker
export function getMarketTicker() {
  return [
    { symbol: "BTC", price: 94523.45, change: 2.34 },
    { symbol: "ETH", price: 3198.72, change: -1.12 },
    { symbol: "SOL", price: 186.45, change: 5.67 },
    { symbol: "AVAX", price: 41.23, change: 3.21 },
    { symbol: "LINK", price: 19.87, change: -0.45 },
    { symbol: "MATIC", price: 0.94, change: 1.23 },
    { symbol: "UNI", price: 13.56, change: 2.89 },
    { symbol: "AAVE", price: 278.34, change: -2.15 },
  ];
}

// Volume data
export function getVolumeByExchange() {
  return [
    { exchange: "Binance", volume: 45200 },
    { exchange: "Coinbase", volume: 28400 },
    { exchange: "Kraken", volume: 15600 },
    { exchange: "Uniswap", volume: 12300 },
    { exchange: "Jupiter", volume: 8900 },
  ];
}
