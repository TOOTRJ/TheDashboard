"use client";

import * as React from "react";
import { ChevronDown, Users, Receipt } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { HouseholdMode, NesteggInputs } from "@/lib/nestegg/types";
import { formatPercent } from "@/lib/formatters";
import { cn } from "@/lib/utils";

type Props = {
  inputs: NesteggInputs;
  onChange: (patch: Partial<NesteggInputs>) => void;
};

const inputClass =
  "border-[#00fff5]/20 bg-[#00fff5]/5 focus:border-[#00fff5]/40 font-mono text-sm";

export function NesteggFidelitySettings({ inputs, onChange }: Props) {
  const [open, setOpen] = React.useState(false);

  return (
    <Card className="border-[#ff00ff]/15 bg-card/60 backdrop-blur-sm">
      <CardContent className="pt-4 pb-4">
        <Button
          type="button"
          variant="ghost"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="flex h-auto w-full items-center justify-between rounded-lg px-3 py-3 text-left hover:bg-[#ff00ff]/5"
        >
          <span className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-[#ff00ff]">
            <Users className="h-4 w-4" aria-hidden />
            Household, tax &amp; RMD
          </span>
          <ChevronDown
            className={cn(
              "h-4 w-4 text-muted-foreground transition-transform duration-200",
              open && "rotate-180"
            )}
            aria-hidden
          />
        </Button>
        {open ? (
          <div className="mt-4 space-y-6 border-t border-[#ff00ff]/10 pt-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2 sm:col-span-2">
                <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">
                  Household profile
                </Label>
                <Select
                  value={inputs.householdMode}
                  onValueChange={(v) => onChange({ householdMode: v as HouseholdMode })}
                >
                  <SelectTrigger className="border-[#ff00ff]/20 bg-[#ff00ff]/5 focus:border-[#ff00ff]/40">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="border-[#ff00ff]/20 bg-card/95 backdrop-blur-xl">
                    <SelectItem value="single">Single</SelectItem>
                    <SelectItem value="couple">Couple (two earners / two SS)</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-[10px] text-muted-foreground">
                  Couple mode extends the plan to the later life expectancy and adds a second
                  contribution stream until the partner retires, plus partner Social Security.
                </p>
              </div>

              {inputs.householdMode === "couple" ? (
                <>
                  <div className="space-y-2">
                    <Label
                      htmlFor="spouseAge"
                      className="text-[10px] uppercase tracking-wider text-muted-foreground"
                    >
                      Partner current age
                    </Label>
                    <Input
                      id="spouseAge"
                      type="number"
                      min={18}
                      max={100}
                      value={inputs.spouseCurrentAge}
                      onChange={(e) =>
                        onChange({ spouseCurrentAge: Number(e.target.value) })
                      }
                      className={inputClass}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label
                      htmlFor="spouseRetAge"
                      className="text-[10px] uppercase tracking-wider text-muted-foreground"
                    >
                      Partner retirement age
                    </Label>
                    <Input
                      id="spouseRetAge"
                      type="number"
                      min={40}
                      max={85}
                      value={inputs.spouseRetirementAge}
                      onChange={(e) =>
                        onChange({ spouseRetirementAge: Number(e.target.value) })
                      }
                      className={inputClass}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label
                      htmlFor="spouseLife"
                      className="text-[10px] uppercase tracking-wider text-muted-foreground"
                    >
                      Partner life expectancy
                    </Label>
                    <Input
                      id="spouseLife"
                      type="number"
                      min={inputs.spouseRetirementAge + 1}
                      max={110}
                      value={inputs.spouseLifeExpectancy}
                      onChange={(e) =>
                        onChange({ spouseLifeExpectancy: Number(e.target.value) })
                      }
                      className={inputClass}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label
                      htmlFor="spouseContrib"
                      className="text-[10px] uppercase tracking-wider text-muted-foreground"
                    >
                      Partner monthly contribution
                    </Label>
                    <Input
                      id="spouseContrib"
                      type="number"
                      min={0}
                      step={50}
                      value={inputs.spouseMonthlyContribution}
                      onChange={(e) =>
                        onChange({ spouseMonthlyContribution: Number(e.target.value) })
                      }
                      className={inputClass}
                    />
                  </div>
                  <div className="space-y-2 sm:col-span-2">
                    <Label
                      htmlFor="spouseSS"
                      className="text-[10px] uppercase tracking-wider text-muted-foreground"
                    >
                      Partner Social Security (monthly, at their retirement)
                    </Label>
                    <Input
                      id="spouseSS"
                      type="number"
                      min={0}
                      step={50}
                      value={inputs.spouseSocialSecurityMonthly}
                      onChange={(e) =>
                        onChange({ spouseSocialSecurityMonthly: Number(e.target.value) })
                      }
                      className={inputClass}
                    />
                  </div>
                  <div className="sm:col-span-2 rounded-lg border border-[#ff99ff]/20 bg-gradient-to-br from-[#ff99ff]/8 to-transparent p-3 space-y-3">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <Label
                          htmlFor="survivor-model"
                          className="text-xs font-medium text-[#ff99ff]"
                        >
                          Survivor transition
                        </Label>
                        <p className="text-[10px] text-muted-foreground mt-0.5 leading-snug">
                          After the first modeled death, spending scales down and Social Security
                          follows a simplified survivor benefit (larger of the two benefits).
                        </p>
                      </div>
                      <Switch
                        id="survivor-model"
                        checked={inputs.enableSurvivorModeling}
                        onCheckedChange={(v) => onChange({ enableSurvivorModeling: v })}
                        className="data-[state=checked]:bg-[#ff99ff]"
                      />
                    </div>
                    {inputs.enableSurvivorModeling ? (
                      <div className="space-y-2 pt-1">
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
                          onValueChange={([v]) =>
                            onChange({ survivorSpendingRatioPercent: v })
                          }
                          aria-label="Survivor spending as percent of household retirement spending"
                        />
                      </div>
                    ) : null}
                  </div>
                </>
              ) : null}
            </div>

            <div className="rounded-lg border border-[#00fff5]/10 bg-card/40 p-3 space-y-3">
              <div className="flex items-center gap-2 text-[#00fff5]">
                <Receipt className="h-4 w-4" aria-hidden />
                <span className="text-xs font-bold uppercase tracking-wider">
                  Taxes &amp; RMD (simplified)
                </span>
              </div>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <Label htmlFor="tax-withdrawals" className="text-xs font-medium">
                    Tax on portfolio withdrawals
                  </Label>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    Grosses up draws using a flat marginal rate (not real brackets).
                  </p>
                </div>
                <Switch
                  id="tax-withdrawals"
                  checked={inputs.enableTaxOnWithdrawals}
                  onCheckedChange={(v) => onChange({ enableTaxOnWithdrawals: v })}
                  className="data-[state=checked]:bg-[#00fff5]"
                />
              </div>
              {inputs.enableTaxOnWithdrawals ? (
                <div className="space-y-2">
                  <Label
                    htmlFor="marginalTax"
                    className="text-[10px] uppercase tracking-wider text-muted-foreground"
                  >
                    Marginal tax rate (%)
                  </Label>
                  <div className="flex items-center gap-2">
                    <Input
                      id="marginalTax"
                      type="number"
                      min={0}
                      max={50}
                      step={1}
                      value={inputs.marginalTaxRatePercent}
                      onChange={(e) =>
                        onChange({ marginalTaxRatePercent: Number(e.target.value) })
                      }
                      className={inputClass}
                    />
                    <span className="text-xs font-mono text-muted-foreground w-14">
                      {formatPercent(inputs.marginalTaxRatePercent, 0)}
                    </span>
                  </div>
                </div>
              ) : null}

              <div className="flex items-center justify-between gap-3 pt-2 border-t border-[#00fff5]/10">
                <div>
                  <Label htmlFor="enable-rmd" className="text-xs font-medium">
                    RMD floor (Uniform Lifetime)
                  </Label>
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    Minimum annual draw from the tax-deferred share, spread monthly.
                  </p>
                </div>
                <Switch
                  id="enable-rmd"
                  checked={inputs.enableRmd}
                  onCheckedChange={(v) => onChange({ enableRmd: v })}
                  className="data-[state=checked]:bg-[#00fff5]"
                />
              </div>
              {inputs.enableRmd ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label
                      htmlFor="rmdStart"
                      className="text-[10px] uppercase tracking-wider text-muted-foreground"
                    >
                      RMD start age
                    </Label>
                    <Input
                      id="rmdStart"
                      type="number"
                      min={65}
                      max={80}
                      value={inputs.rmdStartAge}
                      onChange={(e) =>
                        onChange({ rmdStartAge: Number(e.target.value) })
                      }
                      className={inputClass}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label
                      htmlFor="deferredShare"
                      className="text-[10px] uppercase tracking-wider text-muted-foreground"
                    >
                      Tax-deferred share of balance (%)
                    </Label>
                    <Input
                      id="deferredShare"
                      type="number"
                      min={0}
                      max={100}
                      value={inputs.taxDeferredSharePercent}
                      onChange={(e) =>
                        onChange({ taxDeferredSharePercent: Number(e.target.value) })
                      }
                      className={inputClass}
                    />
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
