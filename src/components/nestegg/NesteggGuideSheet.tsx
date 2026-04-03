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
              Nestegg projects your portfolio from today through a planning horizon, including
              working years, retirement spending, inflation, and optional income like Social
              Security. Monte Carlo adds randomized returns so you can see a range of outcomes, not
              just one straight line.
            </p>
          </section>
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              Step 1 — Baseline assumptions
            </h4>
            <p>
              Set ages, savings, contributions, spending, and income in the left column. Advanced
              settings let you tune inflation, taxes, and household details.
            </p>
          </section>
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              Step 2 — Projected nest egg
            </h4>
            <p>
              The summary cards show deterministic projections and probability-weighted results.
              “Chance of success” is the share of Monte Carlo paths that stay funded through your
              horizon.
            </p>
          </section>
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              Step 3 — Compare success probability
            </h4>
            <p>
              Use the scenario comparison table to see how Base, Conservative, and Aggressive
              presets compare on the same inputs. Toggle “Compare all scenarios on chart” to overlay
              deterministic curves.
            </p>
          </section>
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              Step 4 — Test alternates
            </h4>
            <p>
              Quick what-if buttons apply small changes instantly. If you like a variant, use{" "}
              <span className="text-foreground">Saved scenarios</span> to store it under a new
              name.
            </p>
          </section>
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              Step 5 — Saved scenarios
            </h4>
            <p>
              Signed-in users can save named plans to the cloud. Your latest saved plan loads on
              return visits. Duplicate or rename from the saved list when you iterate.
            </p>
          </section>
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              What the charts mean
            </h4>
            <p>
              The main chart shows either a single deterministic path, three overlaid presets, or a
              median path with 10th–90th percentile rails from Monte Carlo. The retirement marker is
              when contributions stop; a depletion marker appears if the balance is modeled to hit
              zero.
            </p>
          </section>
          <section>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-2">
              What “Monte Carlo” means here
            </h4>
            <p>
              We run many paths with randomized monthly returns around your expected return and a
              volatility that matches your risk profile. It illustrates uncertainty — not a
              guarantee — and helps compare plans on similar footing.
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
