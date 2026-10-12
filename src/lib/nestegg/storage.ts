import type { NesteggDraftV1 } from "./types";
import { DEFAULT_NESTEGG_INPUTS, normalizeNesteggInputs } from "./constants";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
function draftKey(ownerId: string): string | null {
  return typeof ownerId === "string" && UUID.test(ownerId) ? `nestegg-draft-v2:${ownerId}` : null;
}

/** Unowned v1 drafts are deliberately never read, claimed, migrated or deleted. */
export function loadNesteggDraft(ownerId: string): { draft: NesteggDraftV1 | null; unavailable: boolean } {
  const key = draftKey(ownerId);
  if (!key || typeof window === "undefined") return { draft: null, unavailable: false };
  let raw: string | null;
  try { raw = window.localStorage.getItem(key); }
  catch { return { draft: null, unavailable: true }; }
  if (!raw || raw.length > 262144) return { draft: null, unavailable: false };
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || parsed.version !== 2 || parsed.ownerId !== ownerId
      || !parsed.inputs || typeof parsed.inputs !== "object" || Array.isArray(parsed.inputs)
      || !["base", "conservative", "aggressive"].includes(parsed.marketScenario)
      || typeof parsed.compareOverlay !== "boolean" || typeof parsed.updatedAt !== "string") {
      return { draft: null, unavailable: false };
    }
    return { draft: { inputs: normalizeNesteggInputs(parsed.inputs),
      marketScenario: parsed.marketScenario, compareOverlay: parsed.compareOverlay,
      updatedAt: parsed.updatedAt }, unavailable: false };
  } catch { return { draft: null, unavailable: false }; }
}

export function saveNesteggDraft(ownerId: string, draft: Omit<NesteggDraftV1, "updatedAt">): boolean {
  const key = draftKey(ownerId);
  if (!key || typeof window === "undefined") return false;
  try {
    window.localStorage.setItem(key, JSON.stringify({ ...draft, version: 2, ownerId,
      updatedAt: new Date().toISOString() }));
    return true;
  } catch { return false; }
}

export function clearNesteggDraft(ownerId: string): boolean {
  const key = draftKey(ownerId);
  if (!key || typeof window === "undefined") return false;
  try { window.localStorage.removeItem(key); return true; } catch { return false; }
}

export function defaultDraftState(): Omit<NesteggDraftV1, "updatedAt"> {
  return { inputs: { ...DEFAULT_NESTEGG_INPUTS }, marketScenario: "base", compareOverlay: false };
}
