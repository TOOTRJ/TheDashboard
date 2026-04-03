"use client";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { BookOpen, RotateCcw } from "lucide-react";

type Props = {
  onReplayTour?: () => void;
};

export function NesteggGuideSheet({ onReplayTour }: Props) {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-9 border-[#00fff5]/25 bg-[#00fff5]/5 text-xs hover:bg-[#00fff5]/15 hover:text-[#00fff5]"
        >
          <BookOpen className="mr-2 h-4 w-4" />
          How it works
        </Button>
      </SheetTrigger>
      <SheetContent
        side="right"
        className="w-full overflow-y-auto border-[#00fff5]/20 bg-card/95 backdrop-blur-xl sm:max-w-md"
      >
        <SheetHeader>
          <SheetTitle className="text-[#00fff5] uppercase tracking-wider text-sm">
            How to use Nestegg
          </SheetTitle>
          <SheetDescription className="text-left text-xs leading-relaxed">
            A quick, practical guide — nothing here is financial advice.
          </SheetDescription>
        </SheetHeader>
        <div className="mt-4 space-y-6 px-1 pb-8 text-sm text-muted-foreground leading-relaxed">
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              What Nestegg does
            </h4>
            <p>
              Nestegg projects your portfolio from today through your planning horizon: working
              years, retirement spending, inflation, and optional income like Social Security. Monte
              Carlo adds randomized returns so you see a range of outcomes, not just one line.
            </p>
          </section>
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              Step 1 — Review the story first
            </h4>
            <p>
              The top of the page shows headline results and your main chart. When you are ready to
              tune details, scroll to <span className="text-foreground">Your plan inputs</span> for
              ages, savings, spending, and presets. Advanced assumptions cover inflation, income, and
              household options.
            </p>
          </section>
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              Step 2 — Chance of success
            </h4>
            <p>
              “Chance of success” is the share of simulated paths that stay funded through your
              horizon. It complements the straight-line snapshot, not a guarantee — use it to
              compare ideas on similar footing.
            </p>
          </section>
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              Step 3 — Compare presets
            </h4>
            <p>
              Use the comparison table for Base, Conservative, and Aggressive on the same inputs.
              Turn on <span className="text-foreground">Compare all scenarios on chart</span> to
              overlay three deterministic curves on the main chart.
            </p>
          </section>
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              Step 4 — Try quick changes
            </h4>
            <p>
              Use <span className="text-foreground">Try a different plan</span> for one-tap tweaks.
              If you like a variant, open <span className="text-foreground">Saved scenarios</span>{" "}
              to store it under a new name.
            </p>
          </section>
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              Step 5 — Saved plans
            </h4>
            <p>
              Signed-in users can save named plans to the cloud. Your latest saved plan can load on
              return visits. Duplicate or rename from the saved list when you iterate.
            </p>
          </section>
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              What the main chart shows
            </h4>
            <p>
              Either one deterministic path, three overlaid presets, or a median path with softer and
              tougher outcome bands. The retirement marker is when contributions stop; a depletion
              marker appears if the balance is modeled to hit zero.
            </p>
          </section>
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              What “Monte Carlo” means here
            </h4>
            <p>
              Many paths with randomized monthly returns around your expected return and a volatility
              tied to your risk profile. It illustrates uncertainty — not a promise — and helps
              compare plans fairly.
            </p>
          </section>
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              Tips
            </h4>
            <ul className="list-disc pl-4 space-y-1">
              <li>Stress-test spending and late-career returns before locking a date.</li>
              <li>Compare conservative vs aggressive presets when decisions feel borderline.</li>
              <li>Revisit after big life events — the model is only as current as your inputs.</li>
            </ul>
          </section>
          {onReplayTour ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full border-[#ff00ff]/25 text-xs"
              onClick={onReplayTour}
            >
              <RotateCcw className="mr-2 h-3.5 w-3.5" />
              Replay welcome tour
            </Button>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
