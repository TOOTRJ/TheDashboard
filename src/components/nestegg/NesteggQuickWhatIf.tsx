"use client";

import type { NesteggInputs } from "@/lib/nestegg/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Zap } from "lucide-react";

type Props = {
  inputs: NesteggInputs;
  onPatch: (patch: Partial<NesteggInputs>) => void;
};

export function NesteggQuickWhatIf({ inputs, onPatch }: Props) {
  const actions: Array<{ label: string; patch: Partial<NesteggInputs> }> = [
    {
      label: "Retire 2 years later",
      patch: { retirementAge: inputs.retirementAge + 2 },
    },
    {
      label: "Save $250 more / mo",
      patch: { monthlyContribution: inputs.monthlyContribution + 250 },
    },
    {
      label: "Cut spending 10%",
      patch: {
        monthlyRetirementSpending: Math.max(
          0,
          Math.round(inputs.monthlyRetirementSpending * 0.9)
        ),
      },
    },
    {
      label: "Inflation stress +1%",
      patch: {
        inflationPercent: Math.min(8, inputs.inflationPercent + 1),
      },
    },
    {
      label: "Returns −1%",
      patch: {
        annualReturnPercent: Math.max(0.5, inputs.annualReturnPercent - 1),
      },
    },
    {
      label: "SS +$300 / mo",
      patch: {
        socialSecurityMonthly: inputs.socialSecurityMonthly + 300,
      },
    },
    {
      label: "Conservative path",
      patch: {
        annualReturnPercent: Math.max(1, inputs.annualReturnPercent - 2),
        inflationPercent: Math.min(8, inputs.inflationPercent + 0.5),
      },
    },
  ];

  return (
    <Card className="border-[#ffff00]/20 bg-card/80 backdrop-blur-sm">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#ffff00]/10">
            <Zap className="h-4 w-4 text-[#ffff00]" aria-hidden />
          </div>
          <div>
            <h3 className="text-sm font-semibold uppercase tracking-wider text-[#ffff00]">
              Quick what-if
            </h3>
            <p className="text-[11px] text-muted-foreground">
              Apply a one-tap tweak to your workspace — save as a new scenario if you like it
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-wrap gap-2 pt-0">
        {actions.map((a) => (
          <Button
            key={a.label}
            type="button"
            variant="outline"
            size="sm"
            className="h-8 border-[#ffff00]/25 bg-[#ffff00]/5 text-[11px] hover:bg-[#ffff00]/15 hover:text-[#ffff00]"
            onClick={() => onPatch(a.patch)}
          >
            {a.label}
          </Button>
        ))}
      </CardContent>
    </Card>
  );
}
