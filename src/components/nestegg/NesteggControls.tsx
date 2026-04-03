"use client";

import type { ReactNode } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import type { NesteggInputs } from "@/lib/nestegg/types";
import { formatCurrency, formatPercent } from "@/lib/formatters";
import { SlidersHorizontal } from "lucide-react";

type Props = {
  inputs: NesteggInputs;
  onChange: (patch: Partial<NesteggInputs>) => void;
};

const inputClass =
  "border-[#00fff5]/20 bg-[#00fff5]/5 focus:border-[#00fff5]/40 font-mono text-sm";

function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string;
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <Label
          htmlFor={id}
          className="text-[10px] uppercase tracking-wider text-muted-foreground"
        >
          {label}
        </Label>
        {hint ? (
          <span className="text-[10px] text-muted-foreground/80">{hint}</span>
        ) : null}
      </div>
      {children}
    </div>
  );
}

function RangeWithNumber({
  id,
  label,
  hint,
  value,
  onChange,
  min,
  max,
  step,
  format,
}: {
  id: string;
  label: string;
  hint?: string;
  value: number;
  onChange: (n: number) => void;
  min: number;
  max: number;
  step: number;
  format: (n: number) => string;
}) {
  const clamped = Math.min(max, Math.max(min, value));
  return (
    <Field id={id} label={label} hint={hint}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <Slider
          id={`${id}-slider`}
          min={min}
          max={max}
          step={step}
          value={[clamped]}
          onValueChange={(v) => {
            const n = v[0];
            if (n !== undefined) onChange(step >= 1 ? Math.round(n) : n);
          }}
          className="w-full sm:max-w-[180px] py-2"
          aria-label={label}
        />
        <div className="flex flex-1 items-center gap-2">
          <Input
            id={id}
            type="number"
            min={min}
            max={max}
            step={step}
            value={Number.isFinite(value) ? value : 0}
            onChange={(e) => onChange(Number(e.target.value))}
            className={inputClass}
          />
          <span className="shrink-0 text-xs font-mono text-[#00fff5]/90">
            {format(value)}
          </span>
        </div>
      </div>
    </Field>
  );
}

export function NesteggControls({ inputs, onChange }: Props) {
  return (
    <Card className="border-[#00fff5]/20 bg-card/80 backdrop-blur-sm">
      <CardHeader className="pb-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-[#00fff5]/10">
            <SlidersHorizontal className="h-5 w-5 text-[#00fff5]" aria-hidden />
          </div>
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wider text-[#00fff5]">
              Plan inputs
            </h2>
            <p className="text-xs text-muted-foreground">
              Core assumptions update projections instantly
            </p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-4">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-[#00fff5]/90">
              You &amp; timeline
            </p>
            <p className="text-[11px] text-muted-foreground mt-1">
              Ages set how long you save and how long the plan needs to last.
            </p>
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
        <RangeWithNumber
          id="currentAge"
          label="Current age"
          value={inputs.currentAge}
          onChange={(n) => onChange({ currentAge: Math.round(n) })}
          min={18}
          max={80}
          step={1}
          format={(n) => `${n} yrs`}
        />
        <RangeWithNumber
          id="retirementAge"
          label="Retirement age"
          value={inputs.retirementAge}
          onChange={(n) => onChange({ retirementAge: Math.round(n) })}
          min={Math.max(40, inputs.currentAge)}
          max={85}
          step={1}
          format={(n) => `${n} yrs`}
        />
        <RangeWithNumber
          id="lifeExpectancy"
          label="Life expectancy"
          hint="Planning horizon"
          value={inputs.lifeExpectancy}
          onChange={(n) => onChange({ lifeExpectancy: Math.round(n) })}
          min={Math.max(inputs.retirementAge + 1, inputs.currentAge + 1)}
          max={105}
          step={1}
          format={(n) => `${n} yrs`}
        />
          </div>
        </div>

        <div className="space-y-4 border-t border-[#00fff5]/10 pt-5">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-[#00fff5]/90">
              Savings &amp; growth
            </p>
            <p className="text-[11px] text-muted-foreground mt-1">
              What you have today, what you add, and the return you expect before retiring.
            </p>
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
        <Field id="currentSavings" label="Current savings">
          <Input
            id="currentSavings"
            type="number"
            min={0}
            step={500}
            value={inputs.currentSavings}
            onChange={(e) => onChange({ currentSavings: Number(e.target.value) })}
            className={inputClass}
          />
          <p className="text-[10px] text-muted-foreground mt-1">
            {formatCurrency(inputs.currentSavings)} today
          </p>
        </Field>
        <Field id="monthlyContribution" label="Monthly contribution">
          <Input
            id="monthlyContribution"
            type="number"
            min={0}
            step={50}
            value={inputs.monthlyContribution}
            onChange={(e) =>
              onChange({ monthlyContribution: Number(e.target.value) })
            }
            className={inputClass}
          />
        </Field>
        <RangeWithNumber
          id="annualReturn"
          label="Expected annual return"
          value={inputs.annualReturnPercent}
          onChange={(n) => onChange({ annualReturnPercent: n })}
          min={1}
          max={12}
          step={0.25}
          format={(n) => formatPercent(n, 2)}
        />
          </div>
        </div>

        <div className="space-y-4 border-t border-[#00fff5]/10 pt-5">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-[#00fff5]/90">
              Retirement spending
            </p>
            <p className="text-[11px] text-muted-foreground mt-1">
              A monthly spending target in today&apos;s dollars; the model steps it up with inflation.
            </p>
          </div>
        <div className="grid gap-5 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field id="monthlyRetirementSpending" label="Monthly retirement spending">
            <Input
              id="monthlyRetirementSpending"
              type="number"
              min={0}
              step={100}
              value={inputs.monthlyRetirementSpending}
              onChange={(e) =>
                onChange({ monthlyRetirementSpending: Number(e.target.value) })
              }
              className={inputClass}
            />
            <p className="text-[10px] text-muted-foreground mt-1">
              In today&apos;s dollars; spending steps up with inflation in retirement
            </p>
          </Field>
        </div>
        </div>
        </div>
      </CardContent>
    </Card>
  );
}
