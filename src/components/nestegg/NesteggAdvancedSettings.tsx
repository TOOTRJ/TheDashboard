"use client";

import * as React from "react";
import { ChevronDown, Settings2 } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { NesteggInputs, RiskProfile } from "@/lib/nestegg/types";
import { formatPercent } from "@/lib/formatters";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type Props = {
  inputs: NesteggInputs;
  onChange: (patch: Partial<NesteggInputs>) => void;
};

const inputClass =
  "border-[#00fff5]/20 bg-[#00fff5]/5 focus:border-[#00fff5]/40 font-mono text-sm";

export function NesteggAdvancedSettings({ inputs, onChange }: Props) {
  const [open, setOpen] = React.useState(false);

  return (
    <Card className="border-[#00fff5]/15 bg-card/60 backdrop-blur-sm">
      <CardContent className="pt-4 pb-4">
        <Button
          type="button"
          variant="ghost"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="flex h-auto w-full items-center justify-between rounded-lg px-3 py-3 text-left hover:bg-[#00fff5]/5"
        >
          <span className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-[#00fff5]">
            <Settings2 className="h-4 w-4" aria-hidden />
            Advanced settings
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
          <div className="mt-4 grid gap-4 border-t border-[#00fff5]/10 pt-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label
                htmlFor="inflation"
                className="text-[10px] uppercase tracking-wider text-muted-foreground"
              >
                Inflation rate
              </Label>
              <div className="flex items-center gap-2">
                <Input
                  id="inflation"
                  type="number"
                  min={0}
                  max={8}
                  step={0.1}
                  value={inputs.inflationPercent}
                  onChange={(e) =>
                    onChange({ inflationPercent: Number(e.target.value) })
                  }
                  className={inputClass}
                />
                <span className="text-xs font-mono text-muted-foreground w-12">
                  {formatPercent(inputs.inflationPercent, 1)}
                </span>
              </div>
            </div>
            <div className="space-y-2">
              <Label
                htmlFor="salaryGrowth"
                className="text-[10px] uppercase tracking-wider text-muted-foreground"
              >
                Annual salary growth
              </Label>
              <div className="flex items-center gap-2">
                <Input
                  id="salaryGrowth"
                  type="number"
                  min={0}
                  max={10}
                  step={0.1}
                  value={inputs.salaryGrowthPercent}
                  onChange={(e) =>
                    onChange({ salaryGrowthPercent: Number(e.target.value) })
                  }
                  className={inputClass}
                />
                <span className="text-xs font-mono text-muted-foreground w-12">
                  {formatPercent(inputs.salaryGrowthPercent, 1)}
                </span>
              </div>
            </div>
            <div className="space-y-2">
              <Label
                htmlFor="ss"
                className="text-[10px] uppercase tracking-wider text-muted-foreground"
              >
                Social Security (monthly)
              </Label>
              <Input
                id="ss"
                type="number"
                min={0}
                step={50}
                value={inputs.socialSecurityMonthly}
                onChange={(e) =>
                  onChange({ socialSecurityMonthly: Number(e.target.value) })
                }
                className={inputClass}
              />
            </div>
            <div className="space-y-2">
              <Label
                htmlFor="otherIncome"
                className="text-[10px] uppercase tracking-wider text-muted-foreground"
              >
                Other monthly retirement income
              </Label>
              <Input
                id="otherIncome"
                type="number"
                min={0}
                step={50}
                value={inputs.otherRetirementIncomeMonthly}
                onChange={(e) =>
                  onChange({ otherRetirementIncomeMonthly: Number(e.target.value) })
                }
                className={inputClass}
              />
            </div>
            <div className="space-y-2">
              <Label
                htmlFor="oneTimeIncome"
                className="text-[10px] uppercase tracking-wider text-muted-foreground"
              >
                One-time income at retirement
              </Label>
              <Input
                id="oneTimeIncome"
                type="number"
                step={500}
                value={inputs.oneTimeIncome}
                onChange={(e) =>
                  onChange({ oneTimeIncome: Number(e.target.value) })
                }
                className={inputClass}
              />
            </div>
            <div className="space-y-2">
              <Label
                htmlFor="oneTimeExpense"
                className="text-[10px] uppercase tracking-wider text-muted-foreground"
              >
                One-time expense at retirement
              </Label>
              <Input
                id="oneTimeExpense"
                type="number"
                step={500}
                value={inputs.oneTimeExpense}
                onChange={(e) =>
                  onChange({ oneTimeExpense: Number(e.target.value) })
                }
                className={inputClass}
              />
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Risk profile
              </Label>
              <p className="text-[10px] text-muted-foreground mb-1">
                Fine-tunes modeled return slightly (separate from scenario tabs).
              </p>
              <Select
                value={inputs.riskProfile}
                onValueChange={(v) => onChange({ riskProfile: v as RiskProfile })}
              >
                <SelectTrigger className="border-[#00fff5]/20 bg-[#00fff5]/5 focus:border-[#00fff5]/40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-[#00fff5]/20 bg-card/95 backdrop-blur-xl">
                  <SelectItem value="conservative">Conservative</SelectItem>
                  <SelectItem value="moderate">Moderate</SelectItem>
                  <SelectItem value="aggressive">Aggressive</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
