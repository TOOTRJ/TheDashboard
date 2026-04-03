"use client";

import { Info, Save, SlidersHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { NesteggInputs } from "@/lib/nestegg/types";

type Props = {
  inputs: NesteggInputs;
  onChange: (patch: Partial<NesteggInputs>) => void;
  canSave?: boolean;
  dirty?: boolean;
  saving?: boolean;
  onSave?: () => void;
};

const inputClass =
  "h-8 border-[#00fff5]/20 bg-[#00fff5]/5 focus:border-[#00fff5]/40 font-mono text-xs tabular-nums";

type FieldDef = {
  id: string;
  label: string;
  tip: string;
  key: keyof NesteggInputs;
  min?: number;
  max?: number;
  step?: number;
};

const FIELDS: FieldDef[] = [
  {
    id: "qa-currentAge",
    label: "Current age",
    tip: "Your age today — sets how many years of saving remain",
    key: "currentAge",
    min: 18,
    max: 80,
    step: 1,
  },
  {
    id: "qa-retirementAge",
    label: "Retire age",
    tip: "When you stop contributing and start drawing down",
    key: "retirementAge",
    min: 40,
    max: 85,
    step: 1,
  },
  {
    id: "qa-lifeExpectancy",
    label: "Life expectancy",
    tip: "Planning horizon — the model runs until this age",
    key: "lifeExpectancy",
    min: 50,
    max: 105,
    step: 1,
  },
  {
    id: "qa-currentSavings",
    label: "Current savings",
    tip: "Total invested portfolio balance today",
    key: "currentSavings",
    min: 0,
    step: 500,
  },
  {
    id: "qa-monthlyContrib",
    label: "Monthly contribution",
    tip: "How much you add each month while working",
    key: "monthlyContribution",
    min: 0,
    step: 50,
  },
  {
    id: "qa-monthlySpend",
    label: "Monthly spending",
    tip: "Target monthly spending in retirement (today's dollars, inflated automatically)",
    key: "monthlyRetirementSpending",
    min: 0,
    step: 100,
  },
  {
    id: "qa-annualReturn",
    label: "Return %",
    tip: "Expected average annual investment return before inflation",
    key: "annualReturnPercent",
    min: 1,
    max: 12,
    step: 0.25,
  },
  {
    id: "qa-inflation",
    label: "Inflation %",
    tip: "Annual price increase — spending and income step up by this rate each year",
    key: "inflationPercent",
    min: 0,
    max: 8,
    step: 0.1,
  },
];

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
        className="max-w-[220px] border border-[#00fff5]/20 bg-card/95 text-foreground backdrop-blur-xl"
      >
        {tip}
      </TooltipContent>
    </Tooltip>
  );
}

export function NesteggQuickInputsPanel({
  inputs,
  onChange,
  canSave = false,
  dirty = false,
  saving = false,
  onSave,
}: Props) {
  return (
    <TooltipProvider delayDuration={250}>
      <Card className="border-[#00fff5]/25 bg-card/85 backdrop-blur-sm h-full flex flex-col shadow-[0_0_32px_-8px_rgba(0,255,245,0.12)]">
        <CardHeader className="pb-2 pt-4 px-4">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#00fff5]/12 ring-1 ring-[#00fff5]/20">
              <SlidersHorizontal className="h-4 w-4 text-[#00fff5]" aria-hidden />
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="text-[11px] font-semibold uppercase tracking-wider text-[#00fff5]">
                Quick inputs
              </h3>
              <p className="text-[10px] text-muted-foreground leading-tight">
                Adjust key numbers — chart updates live
              </p>
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex-1 px-4 pb-4 pt-1 space-y-2.5 overflow-y-auto">
          {/* Ages — 2-col row */}
          <div className="grid grid-cols-2 gap-2">
            {FIELDS.slice(0, 2).map((f) => (
              <QuickField
                key={f.id}
                field={f}
                value={inputs[f.key] as number}
                onChange={(v) => onChange({ [f.key]: v })}
              />
            ))}
          </div>

          {/* Life expectancy through monthly spending — single col */}
          {FIELDS.slice(2, 6).map((f) => (
            <QuickField
              key={f.id}
              field={f}
              value={inputs[f.key] as number}
              onChange={(v) => onChange({ [f.key]: v })}
            />
          ))}

          {/* Return % and Inflation % — 2-col row */}
          <div className="grid grid-cols-2 gap-2">
            {FIELDS.slice(6, 8).map((f) => (
              <QuickField
                key={f.id}
                field={f}
                value={inputs[f.key] as number}
                onChange={(v) => onChange({ [f.key]: v })}
              />
            ))}
          </div>

          {/* Save button */}
          {canSave ? (
            <Button
              type="button"
              onClick={onSave}
              disabled={saving || !dirty}
              className="w-full h-8 mt-1 border border-[#ff00ff]/30 bg-[#ff00ff]/10 text-[#ff99ff] hover:bg-[#ff00ff]/20 hover:text-[#ff99ff] text-xs disabled:opacity-40"
            >
              <Save className="mr-1.5 h-3.5 w-3.5" aria-hidden />
              {saving ? "Saving…" : dirty ? "Save to plan" : "Saved"}
            </Button>
          ) : null}
        </CardContent>
      </Card>
    </TooltipProvider>
  );
}

function QuickField({
  field,
  value,
  onChange,
}: {
  field: FieldDef;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="space-y-0.5">
      <div className="flex items-center gap-1">
        <label
          htmlFor={field.id}
          className="text-[10px] uppercase tracking-wider text-muted-foreground leading-tight"
        >
          {field.label}
        </label>
        <TipIcon tip={field.tip} />
      </div>
      <Input
        id={field.id}
        type="number"
        min={field.min}
        max={field.max}
        step={field.step}
        value={Number.isFinite(value) ? value : 0}
        onChange={(e) => onChange(Number(e.target.value))}
        className={inputClass}
      />
    </div>
  );
}
