"use client";

import { useState } from "react";
import { useAuth } from "@/components/auth/AuthProvider";
import { TradeLog } from "@/components/probes/TradeLog";
import { Button } from "@/components/ui/button";

export default function TradeHistoryFixturePage() {
  const { user, session, loading } = useAuth();
  if (loading) return <p>Checking fixture account…</p>;
  if (!user || !session) return <p>Sign in to use the synthetic trade fixture.</p>;
  return <OwnerTradeHistory key={user.id} owner={user.id} />;
}

function OwnerTradeHistory({ owner }: { owner: string }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="space-y-4">
      <h1 className="text-xl font-semibold">Synthetic trade history fixture</h1>
      <p>Fixture rows only. No live worker or real trades.</p>
      <Button type="button" onClick={() => setOpen(value => !value)}>
        {open ? "Close trade history" : "Load trade history"}
      </Button>
      {open ? <TradeLog probeId={owner} /> : null}
    </section>
  );
}
