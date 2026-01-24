export {
  getDateRangeOptions,
  getPortfolioSeries,
  getPnlSeries,
  getWinRateSeries,
  getPositionsSeries,
  getCryptoPriceSeries,
  getHoldings,
  getHoldingsDistribution,
  getTradeFeed,
  getKpiSnapshots,
  searchTradeFeed,
  getMarketTicker,
  getVolumeByExchange,
} from "./data";

export type {
  DateRangeKey,
  TimeSeriesPoint,
  CryptoPricePoint,
  HoldingData,
  TradeType,
  TradeStatus,
  TradeItem,
  KpiSnapshot,
} from "./data";

// Strategy exports
export {
  defaultStrategies,
  getDefaultBacktestResults,
  runBacktest,
  supportedSymbols,
  timeframes,
} from "./strategies";

export type {
  StrategyType,
  TimeFrame,
  BacktestStatus,
  Trade,
  StrategyResult,
  StrategyConfig,
} from "./strategies";
