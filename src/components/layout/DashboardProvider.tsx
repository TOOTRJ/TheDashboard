"use client";

import React from "react";

import type { DateRangeKey } from "@/lib/mock";
import { getDateRangeOptions } from "@/lib/mock";

type DashboardContextValue = {
  dateRange: DateRangeKey;
  setDateRange: (value: DateRangeKey) => void;
  searchQuery: string;
  setSearchQuery: (value: string) => void;
  dateRangeOptions: { label: string; value: DateRangeKey }[];
};

const DashboardContext = React.createContext<DashboardContextValue | null>(null);

export function DashboardProvider({ children }: { children: React.ReactNode }) {
  const [dateRange, setDateRange] = React.useState<DateRangeKey>("30d");
  const [searchQuery, setSearchQuery] = React.useState("");

  const value = React.useMemo(
    () => ({
      dateRange,
      setDateRange,
      searchQuery,
      setSearchQuery,
      dateRangeOptions: getDateRangeOptions(),
    }),
    [dateRange, searchQuery]
  );

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}

export function useDashboardFilters() {
  const context = React.useContext(DashboardContext);
  if (!context) {
    throw new Error("useDashboardFilters must be used within DashboardProvider");
  }
  return context;
}
