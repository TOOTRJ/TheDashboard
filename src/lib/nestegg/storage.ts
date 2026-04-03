import type { NesteggDraftV1, NesteggScenarioId } from "./types";
import { DEFAULT_NESTEGG_INPUTS, normalizeNesteggInputs } from "./constants";

const DRAFT_KEY = "nestegg-draft-v1";

function safeParse<T>(raw: string | null): T | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export function loadNesteggDraft(): NesteggDraftV1 | null {
  if (typeof window === "undefined") return null;
  const parsed = safeParse<NesteggDraftV1>(localStorage.getItem(DRAFT_KEY));
  if (!parsed?.inputs) return null;
  return {
    inputs: normalizeNesteggInputs(parsed.inputs),
    marketScenario:
      parsed.marketScenario === "conservative" || parsed.marketScenario === "aggressive"
        ? parsed.marketScenario
        : "base",
    compareOverlay: Boolean(parsed.compareOverlay),
    updatedAt: parsed.updatedAt ?? new Date().toISOString(),
  };
}

export function saveNesteggDraft(draft: Omit<NesteggDraftV1, "updatedAt">): void {
  if (typeof window === "undefined") return;
  const payload: NesteggDraftV1 = {
    ...draft,
    updatedAt: new Date().toISOString(),
  };
  localStorage.setItem(DRAFT_KEY, JSON.stringify(payload));
}

export function clearNesteggDraft(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(DRAFT_KEY);
}

/** Export full defaults as JSON-friendly snapshot (e.g. reset). */
export function defaultDraftState(): Omit<NesteggDraftV1, "updatedAt"> {
  return {
    inputs: { ...DEFAULT_NESTEGG_INPUTS },
    marketScenario: "base",
    compareOverlay: false,
  };
}
