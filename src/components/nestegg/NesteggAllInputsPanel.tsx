"use client";

import { Info } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { NesteggScenarioSelector } from "./NesteggScenarioSelector";
import type {
  HouseholdMode,
  NesteggInputs,
  NesteggScenarioId,
  RiskProfile,
} from "@/lib/nestegg/types";
import {
  ANNUAL_VOLATILITY_BY_RISK,
  effectiveAnnualVolatilityPercent,
} from "@/lib/nestegg/monte-carlo";
import { formatPercent } from "@/lib/formatters";

type Props = {
  inputs: NesteggInputs;
  onChange: (patch: Partial<NesteggInputs>) => void;
  scenario: NesteggScenarioId;
  onScenarioChange: (s: NesteggScenarioId) => void;
  compareOverlay: boolean;
  onCompareOverlayChange: (v: boolean) => void;
};

const inputClass =
  "h-8 border-[#00fff5]/20 bg-[#00fff5]/5 focus:border-[#00fff5]/40 font-mono text-sm";

/* ── Tooltip helper ── */

function TipIcon({ tip }: { tip: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center justify-center text-muted-foreground/60 hover:text-[#00fff5]/80 transition-colors"
          tabIndex={-1}
        >
          <Info className="h-3 w-3" />
        </button>
      </TooltipTrigger>
      <TooltipContent
        side="top"
        className="max-w-[240px] border border-[#00fff5]/20 bg-card/95 text-foreground backdrop-blur-xl"
      >
        {tip}
      </TooltipContent>
    </Tooltip>
  );
}

function TipLabel({
  htmlFor,
  label,
  tip,
}: {
  htmlFor: string;
  label: string;
  tip: string;
}) {
  return (
    <div className="flex items-center gap-1">
      <Label
        htmlFor={htmlFor}
        className="text-[10px] uppercase tracking-wider text-muted-foreground"
      >
        {label}
      </Label>
      <TipIcon tip={tip} />
    </div>
  );
}

function SectionHeading({ label }: { label: string }) {
  return (
    <div className="pt-1">
      <p className="text-[10px] font-bold uppercase tracking-widest text-[#00fff5]/80 border-b border-[#00fff5]/10 pb-1.5">
        {label}
      </p>
    </div>
  );
}

export function NesteggAllInputsPanel({
  inputs,
  onChange,
  scenario,
  onScenarioChange,
  compareOverlay,
  onCompareOverlayChange,
}: Props) {
  const mcCustom = inputs.monteCarloVolatilityPercent !== null;
  const mcEffective = effectiveAnnualVolatilityPercent(inputs);
  const mcSliderVal = mcCustom ? inputs.monteCarloVolatilityPercent! : mcEffective;

  return (
    <TooltipProvider delayDuration={250}>
      <div className="space-y-5">
        {/* ── Timeline ── */}
        <div className="space-y-3">
          <SectionHeading label="Timeline" />
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1">
              <TipLabel
                htmlFor="ai-currentAge"
                label="Current age"
                tip="Your age today — sets how many years of saving remain"
              />
              <Input
                id="ai-currentAge"
                type="number"
                min={18}
                max={80}
                step={1}
                value={inputs.currentAge}
                onChange={(e) => onChange({ currentAge: Math.round(Number(e.target.value)) })}
                className={inputClass}
              />
            </div>
            <div className="space-y-1">
              <TipLabel
                htmlFor="ai-retirementAge"
                label="Retirement age"
                tip="When you stop contributing and start drawing down"
              />
              <Input
                id="ai-retirementAge"
                type="number"
                min={Math.max(40, inputs.currentAge)}
                max={85}
                step={1}
                value={inputs.retirementAge}
                onChange={(e) => onChange({ retirementAge: Math.round(Number(e.target.value)) })}
                className={inputClass}
              />
            </div>
            <div className="space-y-1">
              <TipLabel
                htmlFor="ai-lifeExpectancy"
                label="Life expectancy"
                tip="Planning horizon — the model runs until this age"
              />
              <Input
                id="ai-lifeExpectancy"
                type="number"
                min={Math.max(inputs.retirementAge + 1, inputs.currentAge + 1)}
                max={105}
                step={1}
                value={inputs.lifeExpectancy}
                onChange={(e) => onChange({ lifeExpectancy: Math.round(Number(e.target.value)) })}
                className={inputClass}
              />
            </div>
          </div>
        </div>

        {/* ── Savings & Growth ── */}
        <div className="space-y-3">
          <SectionHeading label="Savings & growth" />
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <TipLabel
                htmlFor="ai-currentSavings"
                label="Current savings"
                tip="Total invested portfolio balance today"
              />
              <Input
                id="ai-currentSavings"
                type="number"
                min={0}
                step={500}
                value={inputs.currentSavings}
                onChange={(e) => onChange({ currentSavings: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
            <div className="space-y-1">
              <TipLabel
                htmlFor="ai-monthlyContrib"
                label="Monthly contribution"
                tip="How much you add each month while working"
              />
              <Input
                id="ai-monthlyContrib"
                type="number"
                min={0}
                step={50}
                value={inputs.monthlyContribution}
                onChange={(e) => onChange({ monthlyContribution: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
            <div className="space-y-1">
              <TipLabel
                htmlFor="ai-annualReturn"
                label="Expected annual return %"
                tip="Expected average annual investment return before inflation"
              />
              <Input
                id="ai-annualReturn"
                type="number"
                min={1}
                max={12}
                step={0.25}
                value={inputs.annualReturnPercent}
                onChange={(e) => onChange({ annualReturnPercent: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
            <div className="space-y-1">
              <TipLabel
                htmlFor="ai-salaryGrowth"
                label="Annual salary growth %"
                tip="Annual raise applied to contributions while working"
              />
              <Input
                id="ai-salaryGrowth"
                type="number"
                min={0}
                max={10}
                step={0.1}
                value={inputs.salaryGrowthPercent}
                onChange={(e) => onChange({ salaryGrowthPercent: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
          </div>
        </div>

        {/* ── Retirement Spending ── */}
        <div className="space-y-3">
          <SectionHeading label="Retirement spending" />
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <TipLabel
                htmlFor="ai-monthlySpend"
                label="Monthly retirement spending"
                tip="Target monthly spending in retirement (today's dollars, inflated automatically)"
              />
              <Input
                id="ai-monthlySpend"
                type="number"
                min={0}
                step={100}
                value={inputs.monthlyRetirementSpending}
                onChange={(e) => onChange({ monthlyRetirementSpending: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
            <div className="space-y-1">
              <TipLabel
                htmlFor="ai-inflation"
                label="Inflation rate %"
                tip="Annual price increase — spending and income step up by this rate each year"
              />
              <Input
                id="ai-inflation"
                type="number"
                min={0}
                max={8}
                step={0.1}
                value={inputs.inflationPercent}
                onChange={(e) => onChange({ inflationPercent: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
          </div>
        </div>

        {/* ── Income Sources ── */}
        <div className="space-y-3">
          <SectionHeading label="Income sources" />
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <TipLabel
                htmlFor="ai-ss"
                label="Social Security (monthly)"
                tip="Monthly SS benefit at retirement (today's dollars)"
              />
              <Input
                id="ai-ss"
                type="number"
                min={0}
                step={50}
                value={inputs.socialSecurityMonthly}
                onChange={(e) => onChange({ socialSecurityMonthly: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
            <div className="space-y-1">
              <TipLabel
                htmlFor="ai-otherIncome"
                label="Other monthly retirement income"
                tip="Pensions, annuities, rental income, or other steady sources in retirement"
              />
              <Input
                id="ai-otherIncome"
                type="number"
                min={0}
                step={50}
                value={inputs.otherRetirementIncomeMonthly}
                onChange={(e) => onChange({ otherRetirementIncomeMonthly: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
            <div className="space-y-1">
              <TipLabel
                htmlFor="ai-oneTimeIn"
                label="One-time income at retirement"
                tip="Lump sum added to your portfolio when you retire (e.g. home sale, inheritance)"
              />
              <Input
                id="ai-oneTimeIn"
                type="number"
                step={500}
                value={inputs.oneTimeIncome}
                onChange={(e) => onChange({ oneTimeIncome: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
            <div className="space-y-1">
              <TipLabel
                htmlFor="ai-oneTimeOut"
                label="One-time expense at retirement"
                tip="Lump sum subtracted from your portfolio at retirement (e.g. mortgage payoff, gift)"
              />
              <Input
                id="ai-oneTimeOut"
                type="number"
                step={500}
                value={inputs.oneTimeExpense}
                onChange={(e) => onChange({ oneTimeExpense: Number(e.target.value) })}
                className={inputClass}
              />
            </div>
          </div>
        </div>

        {/* ── Market & Simulation ── */}
        <div className="space-y-3">
          <SectionHeading label="Market & simulation" />
          <div className="space-y-3">
            <div className="space-y-1">
              <div className="flex items-center gap-1 mb-1">
                <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  Market preset
                </Label>
                <TipIcon tip="Same inputs, three stress levels — switches return and inflation assumptions" />
              </div>
              <NesteggScenarioSelector value={scenario} onChange={onScenarioChange} />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <TipLabel
                  htmlFor="ai-riskProfile"
                  label="Risk profile"
                  tip="Fine-tunes modeled return: conservative -0.5%, moderate 0%, aggressive +0.5%"
                />
                <Select
                  value={inputs.riskProfile}
                  onValueChange={(v) => onChange({ riskProfile: v as RiskProfile })}
                >
                  <SelectTrigger id="ai-riskProfile" className="h-8 border-[#00fff5]/20 bg-[#00fff5]/5 focus:border-[#00fff5]/40 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="border-[#00fff5]/20 bg-card/95 backdrop-blur-xl">
                    <SelectItem value="conservative">Conservative</SelectItem>
                    <SelectItem value="moderate">Moderate</SelectItem>
                    <SelectItem value="aggressive">Aggressive</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center justify-between gap-3 self-end pb-0.5">
                <div className="flex items-center gap-1">
                  <Label htmlFor="ai-compareOverlay" className="text-xs font-medium">
                    Chart comparison overlay
                  </Label>
                  <TipIcon tip="Show base, conservative, and aggressive projections on the main chart" />
                </div>
                <Switch
                  id="ai-compareOverlay"
                  checked={compareOverlay}
                  onCheckedChange={onCompareOverlayChange}
                  className="shrink-0 data-[state=checked]:bg-[#00fff5]"
                />
              </div>
            </div>
            <div className="rounded-lg border border-[#39ff14]/15 bg-[#39ff14]/5 p-3 space-y-2">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-1">
                  <Label htmlFor="ai-mcCustom" className="text-xs font-medium">
                    Custom MC volatility
                  </Label>
                  <TipIcon tip="Override the risk-profile default annual return volatility for Monte Carlo noise" />
                </div>
                <Switch
                  id="ai-mcCustom"
                  checked={mcCustom}
                  onCheckedChange={(v) =>
                    onChange({
                      monteCarloVolatilityPercent: v
                        ? ANNUAL_VOLATILITY_BY_RISK[inputs.riskProfile]
                        : null,
                    })
                  }
                  className="data-[state=checked]:bg-[#39ff14]"
                />
              </div>
              {mcCustom ? (
                <div className="space-y-1.5">
                  <div className="flex justify-between text-[10px] uppercase tracking-wider text-muted-foreground">
                    <span>4% (calm)</span>
                    <span className="font-mono text-[#39ff14]">{mcSliderVal.toFixed(1)}%</span>
                    <span>45% (stress)</span>
                  </div>
                  <Slider
                    min={4}
                    max={45}
                    step={0.5}
                    value={[mcSliderVal]}
                    onValueChange={([v]) =>
                      onChange({ monteCarloVolatilityPercent: v })
                    }
                    aria-label="Annual volatility percent"
                  />
                </div>
              ) : (
                <p className="text-[10px] text-muted-foreground">
                  Using risk-profile default:{" "}
                  <span className="font-mono text-[#39ff14]">{mcEffective.toFixed(1)}%</span>{" "}
                  ({inputs.riskProfile})
                </p>
              )}
            </div>
          </div>
        </div>

        {/* ── Household ── */}
        <div className="space-y-3">
          <SectionHeading label="Household" />
          <div className="space-y-3">
            <div className="space-y-1">
              <TipLabel
                htmlFor="ai-household"
                label="Household mode"
                tip="Couple mode extends the plan to the later life expectancy, adds partner contributions and Social Security"
              />
              <Select
                value={inputs.householdMode}
                onValueChange={(v) => onChange({ householdMode: v as HouseholdMode })}
              >
                <SelectTrigger id="ai-household" className="h-8 border-[#00fff5]/20 bg-[#00fff5]/5 focus:border-[#00fff5]/40 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-[#00fff5]/20 bg-card/95 backdrop-blur-xl">
                  <SelectItem value="single">Single</SelectItem>
                  <SelectItem value="couple">Couple (two earners / two SS)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {inputs.householdMode === "couple" ? (
              <>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <TipLabel
                      htmlFor="ai-spouseAge"
                      label="Partner current age"
                      tip="Partner's current age — used for their contribution window and life expectancy"
                    />
                    <Input
                      id="ai-spouseAge"
                      type="number"
                      min={18}
                      max={100}
                      value={inputs.spouseCurrentAge}
                      onChange={(e) => onChange({ spouseCurrentAge: Number(e.target.value) })}
                      className={inputClass}
                    />
                  </div>
                  <div className="space-y-1">
                    <TipLabel
                      htmlFor="ai-spouseRetAge"
                      label="Partner retirement age"
                      tip="When the partner stops contributing"
                    />
                    <Input
                      id="ai-spouseRetAge"
                      type="number"
                      min={40}
                      max={85}
                      value={inputs.spouseRetirementAge}
                      onChange={(e) => onChange({ spouseRetirementAge: Number(e.target.value) })}
                      className={inputClass}
                    />
                  </div>
                  <div className="space-y-1">
                    <TipLabel
                      htmlFor="ai-spouseLife"
                      label="Partner life expectancy"
                      tip="Planning runs until the longer-lived partner's life expectancy"
                    />
                    <Input
                      id="ai-spouseLife"
                      type="number"
                      min={inputs.spouseRetirementAge + 1}
                      max={110}
                      value={inputs.spouseLifeExpectancy}
                      onChange={(e) => onChange({ spouseLifeExpectancy: Number(e.target.value) })}
                      className={inputClass}
                    />
                  </div>
                  <div className="space-y-1">
                    <TipLabel
                      htmlFor="ai-spouseContrib"
                      label="Partner monthly contribution"
                      tip="Monthly savings the partner adds while working"
                    />
                    <Input
                      id="ai-spouseContrib"
                      type="number"
                      min={0}
                      step={50}
                      value={inputs.spouseMonthlyContribution}
                      onChange={(e) => onChange({ spouseMonthlyContribution: Number(e.target.value) })}
                      className={inputClass}
                    />
                  </div>
                  <div className="space-y-1 sm:col-span-2">
                    <TipLabel
                      htmlFor="ai-spouseSS"
                      label="Partner Social Security (monthly)"
                      tip="Partner's monthly SS benefit at their retirement"
                    />
                    <Input
                      id="ai-spouseSS"
                      type="number"
                      min={0}
                      step={50}
                      value={inputs.spouseSocialSecurityMonthly}
                      onChange={(e) => onChange({ spouseSocialSecurityMonthly: Number(e.target.value) })}
                      className={inputClass}
                    />
                  </div>
                </div>
                <div className="rounded-lg border border-[#ff99ff]/20 bg-[#ff99ff]/5 p-3 space-y-2">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-1">
                      <Label htmlFor="ai-survivor" className="text-xs font-medium text-[#ff99ff]">
                        Survivor transition
                      </Label>
                      <TipIcon tip="After the first modeled death, spending scales down and SS uses the larger of the two benefits" />
                    </div>
                    <Switch
                      id="ai-survivor"
                      checked={inputs.enableSurvivorModeling}
                      onCheckedChange={(v) => onChange({ enableSurvivorModeling: v })}
                      className="data-[state=checked]:bg-[#ff99ff]"
                    />
                  </div>
                  {inputs.enableSurvivorModeling ? (
                    <div className="space-y-1.5">
                      <div className="flex justify-between text-[10px] uppercase tracking-wider text-muted-foreground">
                        <span>Survivor spending (% of household)</span>
                        <span className="font-mono text-[#ff99ff] tabular-nums">
                          {inputs.survivorSpendingRatioPercent}%
                        </span>
                      </div>
                      <Slider
                        min={35}
                        max={100}
                        step={1}
                        value={[inputs.survivorSpendingRatioPercent]}
                        onValueChange={([v]) => onChange({ survivorSpendingRatioPercent: v })}
                        aria-label="Survivor spending percent"
                      />
                    </div>
                  ) : null}
                </div>
              </>
            ) : null}
          </div>
        </div>

        {/* ── Tax & RMD ── */}
        <div className="space-y-3">
          <SectionHeading label="Tax & RMD" />
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-1">
                <Label htmlFor="ai-taxWithdrawals" className="text-xs font-medium">
                  Tax on portfolio withdrawals
                </Label>
                <TipIcon tip="Grosses up portfolio draws using a flat marginal rate (not real brackets)" />
              </div>
              <Switch
                id="ai-taxWithdrawals"
                checked={inputs.enableTaxOnWithdrawals}
                onCheckedChange={(v) => onChange({ enableTaxOnWithdrawals: v })}
                className="data-[state=checked]:bg-[#00fff5]"
              />
            </div>
            {inputs.enableTaxOnWithdrawals ? (
              <div className="space-y-1">
                <TipLabel
                  htmlFor="ai-marginalTax"
                  label="Marginal tax rate %"
                  tip="Flat rate used to gross up portfolio withdrawals"
                />
                <div className="flex items-center gap-2">
                  <Input
                    id="ai-marginalTax"
                    type="number"
                    min={0}
                    max={50}
                    step={1}
                    value={inputs.marginalTaxRatePercent}
                    onChange={(e) => onChange({ marginalTaxRatePercent: Number(e.target.value) })}
                    className={inputClass}
                  />
                  <span className="text-xs font-mono text-muted-foreground shrink-0 w-10">
                    {formatPercent(inputs.marginalTaxRatePercent, 0)}
                  </span>
                </div>
              </div>
            ) : null}

            <div className="flex items-center justify-between gap-3 pt-1 border-t border-[#00fff5]/10">
              <div className="flex items-center gap-1">
                <Label htmlFor="ai-enableRmd" className="text-xs font-medium">
                  RMD floor (Uniform Lifetime)
                </Label>
                <TipIcon tip="Minimum annual draw from the tax-deferred share, spread monthly using IRS life expectancy tables" />
              </div>
              <Switch
                id="ai-enableRmd"
                checked={inputs.enableRmd}
                onCheckedChange={(v) => onChange({ enableRmd: v })}
                className="data-[state=checked]:bg-[#00fff5]"
              />
            </div>
            {inputs.enableRmd ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <TipLabel
                    htmlFor="ai-rmdStart"
                    label="RMD start age"
                    tip="Age when required minimum distributions begin (73 under current law)"
                  />
                  <Input
                    id="ai-rmdStart"
                    type="number"
                    min={65}
                    max={80}
                    value={inputs.rmdStartAge}
                    onChange={(e) => onChange({ rmdStartAge: Number(e.target.value) })}
                    className={inputClass}
                  />
                </div>
                <div className="space-y-1">
                  <TipLabel
                    htmlFor="ai-deferredShare"
                    label="Tax-deferred share %"
                    tip="Portion of your portfolio subject to RMD rules (e.g. Traditional IRA / 401k)"
                  />
                  <Input
                    id="ai-deferredShare"
                    type="number"
                    min={0}
                    max={100}
                    value={inputs.taxDeferredSharePercent}
                    onChange={(e) => onChange({ taxDeferredSharePercent: Number(e.target.value) })}
                    className={inputClass}
                  />
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
