"use client";

import * as React from "react";
import { ChevronDown, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import type { NesteggInputs } from "@/lib/nestegg/types";
import { ANNUAL_VOLATILITY_BY_RISK, effectiveAnnualVolatilityPercent } from "@/lib/nestegg/monte-carlo";
import { cn } from "@/lib/utils";

type Props = {
  inputs: NesteggInputs;
  onChange: (patch: Partial<NesteggInputs>) => void;
};

export function NesteggMonteCarloSettings({ inputs, onChange }: Props) {
  const [open, setOpen] = React.useState(false);
  const custom = inputs.monteCarloVolatilityPercent !== null;
  const effective = effectiveAnnualVolatilityPercent(inputs);
  const sliderVal = custom ? inputs.monteCarloVolatilityPercent! : effective;

  return (
    <Card className="border-[#39ff14]/15 bg-card/60 backdrop-blur-sm">
      <CardContent className="pt-4 pb-4">
        <Button
          type="button"
          variant="ghost"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="flex h-auto w-full items-center justify-between rounded-lg px-3 py-3 text-left hover:bg-[#39ff14]/5"
        >
          <span className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-[#39ff14]">
            <Sparkles className="h-4 w-4" aria-hidden />
            Monte Carlo volatility
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
          <div className="mt-4 space-y-4 border-t border-[#39ff14]/10 pt-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <Label htmlFor="mc-vol-custom" className="text-xs font-medium">
                  Custom annual volatility
                </Label>
                <p className="text-[10px] text-muted-foreground mt-0.5">
                  Off = use risk profile default ({ANNUAL_VOLATILITY_BY_RISK[inputs.riskProfile]}%
                  for {inputs.riskProfile}).
                </p>
              </div>
              <Switch
                id="mc-vol-custom"
                checked={custom}
                onCheckedChange={(v) =>
                  onChange({
                    monteCarloVolatilityPercent: v ? ANNUAL_VOLATILITY_BY_RISK[inputs.riskProfile] : null,
                  })
                }
                className="data-[state=checked]:bg-[#39ff14]"
              />
            </div>
            {custom ? (
              <div className="space-y-3 rounded-lg border border-[#39ff14]/15 bg-[#39ff14]/5 p-3">
                <div className="flex justify-between text-[10px] uppercase tracking-wider text-muted-foreground">
                  <span>4% (calm)</span>
                  <span className="font-mono text-[#39ff14]">{sliderVal.toFixed(1)}% annual</span>
                  <span>45% (stress)</span>
                </div>
                <Slider
                  min={4}
                  max={45}
                  step={0.5}
                  value={[sliderVal]}
                  onValueChange={([v]) =>
                    onChange({ monteCarloVolatilityPercent: v })
                  }
                  aria-label="Annual volatility percent"
                />
              </div>
            ) : (
              <p className="text-[11px] text-muted-foreground leading-relaxed">
                Effective volatility for simulations:{" "}
                <span className="font-mono text-[#39ff14]">{effective.toFixed(1)}%</span> annual.
              </p>
            )}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
