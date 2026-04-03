export type NesteggScenarioId = "base" | "conservative" | "aggressive";

export type RiskProfile = "conservative" | "moderate" | "aggressive";

export type HouseholdMode = "single" | "couple";

export type NesteggInputs = {
  currentAge: number;
  retirementAge: number;
  lifeExpectancy: number;
  currentSavings: number;
  monthlyContribution: number;
  annualReturnPercent: number;
  monthlyRetirementSpending: number;
  inflationPercent: number;
  salaryGrowthPercent: number;
  socialSecurityMonthly: number;
  otherRetirementIncomeMonthly: number;
  oneTimeIncome: number;
  oneTimeExpense: number;
  riskProfile: RiskProfile;
  householdMode: HouseholdMode;
  spouseCurrentAge: number;
  spouseRetirementAge: number;
  spouseLifeExpectancy: number;
  spouseMonthlyContribution: number;
  spouseSocialSecurityMonthly: number;
  enableTaxOnWithdrawals: boolean;
  marginalTaxRatePercent: number;
  enableRmd: boolean;
  rmdStartAge: number;
  /** 0–100: portion of balance treated as tax-deferred for RMD divisor math */
  taxDeferredSharePercent: number;
};

export type ProjectionPhase = "accumulation" | "retirement";

export type ProjectionPoint = {
  age: number;
  balance: number;
  phase: ProjectionPhase;
};

export type ReadinessLevel = "Excellent" | "Strong" | "Needs Attention" | "High Risk";

export type ProjectionResult = {
  series: ProjectionPoint[];
  nestEggAtRetirement: number;
  depletionAge: number | null;
  lastsThroughLifeExpectancy: boolean;
  monthlyGapOrSurplus: number;
  readiness: ReadinessLevel;
  readinessScore: number;
  heroMessage: string;
  heroTone: "positive" | "caution" | "warning";
  suggestedExtraMonthly: number | null;
};

export type SavedNesteggScenario = {
  id: string;
  name: string;
  inputs: NesteggInputs;
  marketScenario: NesteggScenarioId;
  updatedAt: string;
};

export type NesteggDraftV1 = {
  inputs: NesteggInputs;
  marketScenario: NesteggScenarioId;
  compareOverlay: boolean;
  updatedAt: string;
};
