"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

const STORAGE_KEY = "nestegg-onboarding-v1";

const STEPS = [
  {
    title: "See your headline results first",
    body: "The top of Nestegg shows your snapshot, key odds, and the main chart. Scroll down when you are ready to change inputs.",
  },
  {
    title: "Presets & saved plans",
    body: "Pick Base, Conservative, or Aggressive to stress-test the same plan. Sign in to save named scenarios you can reload later.",
  },
  {
    title: "Probability & the chart",
    body: "Success rate and bands summarize uncertainty. The big chart shows growth, retirement, and drawdown — toggle compare mode to overlay presets.",
  },
  {
    title: "Play with ideas",
    body: "Use Try a different plan for one-tap tests. Open How it works anytime — replay this tour from the guide.",
  },
];

type Props = {
  /** Increment to reopen the tour (e.g. “Replay welcome tour”). */
  replayKey?: number;
};

export function NesteggWalkthrough({ replayKey = 0 }: Props) {
  const [open, setOpen] = React.useState(false);
  const [step, setStep] = React.useState(0);

  React.useEffect(() => {
    try {
      if (typeof window === "undefined") return;
      if (!window.localStorage.getItem(STORAGE_KEY)) {
        setOpen(true);
      }
    } catch {
      setOpen(true);
    }
  }, []);

  React.useEffect(() => {
    if (replayKey > 0) {
      setStep(0);
      setOpen(true);
    }
  }, [replayKey]);

  const finish = React.useCallback(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      /* ignore */
    }
    setOpen(false);
  }, []);

  const next = () => {
    if (step >= STEPS.length - 1) {
      finish();
      return;
    }
    setStep((s) => s + 1);
  };

  const s = STEPS[step]!;

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) finish();
        else setOpen(v);
      }}
    >
      <DialogContent className="border-[#00fff5]/20 bg-card/95 backdrop-blur-xl sm:max-w-md">
        <DialogHeader>
          <p className="text-[10px] font-bold uppercase tracking-widest text-[#00fff5]">
            Welcome · {step + 1} / {STEPS.length}
          </p>
          <DialogTitle className="text-base leading-snug">{s.title}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground leading-relaxed">{s.body}</p>
        <DialogFooter className="flex-row justify-between gap-2 sm:justify-between">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            onClick={finish}
          >
            Skip
          </Button>
          <Button
            type="button"
            size="sm"
            className="bg-[#00fff5]/15 hover:bg-[#00fff5]/25 text-foreground border border-[#00fff5]/30"
            onClick={next}
          >
            {step >= STEPS.length - 1 ? "Done" : "Next"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
