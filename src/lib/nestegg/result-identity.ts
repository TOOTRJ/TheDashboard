import type { NesteggInputs, NesteggScenarioId } from "./types";

/** Publication ordering only. Account and token authorization remains in session-scope. */
export type NesteggPublication = { generation: number; isCurrent: () => boolean };

export function createNesteggPublicationClock() {
  let generation = 0;
  const capture = (): NesteggPublication => {
    const captured = generation;
    return { generation: captured, isCurrent: () => captured === generation };
  };
  return {
    generation: () => generation,
    capture,
    next() { generation += 1; return capture(); },
    invalidate() { generation += 1; },
  };
}

export type NesteggCalculationSource = {
  workspaceKey: string;
  inputKey: string;
  inputGeneration: number;
  scenario: NesteggScenarioId;
  inputs: NesteggInputs;
};

export type NesteggCalculationIdentity = Omit<NesteggCalculationSource, "inputs"> & {
  modelVersion: string;
  seedPolicy: string;
  purpose: "light" | "full-bundle" | "saved-comparison";
  pathCount: number;
  requestGeneration: number;
};

export type NesteggCalculationEnvelope<T> = { identity: NesteggCalculationIdentity; value: T };

export function captureNesteggCalculationSource(
  workspaceKey: string, inputs: NesteggInputs, scenario: NesteggScenarioId, inputGeneration: number
): NesteggCalculationSource {
  // All fields are scalar. Preserve their existing insertion order for the unchanged seed policy.
  const snapshot = Object.freeze({ ...inputs });
  return { workspaceKey, inputs: snapshot, scenario, inputGeneration,
    inputKey: JSON.stringify({ inputs: snapshot, scenario }) };
}

export function nesteggCalculationIdentity(
  source: NesteggCalculationSource,
  policy: Pick<NesteggCalculationIdentity, "modelVersion" | "seedPolicy" | "purpose" | "pathCount">,
  requestGeneration: number
): NesteggCalculationIdentity {
  const { workspaceKey, inputKey, inputGeneration, scenario } = source;
  return { workspaceKey, inputKey, inputGeneration, scenario, ...policy, requestGeneration };
}

export function currentNesteggCalculation<T>(
  envelope: NesteggCalculationEnvelope<T> | null,
  source: NesteggCalculationSource,
  policy: Pick<NesteggCalculationIdentity, "modelVersion" | "seedPolicy" | "purpose" | "pathCount">,
  requestGeneration: number
): T | null {
  const id = envelope?.identity;
  return id && id.workspaceKey === source.workspaceKey && id.inputKey === source.inputKey &&
    id.inputGeneration === source.inputGeneration && id.scenario === source.scenario &&
    id.modelVersion === policy.modelVersion && id.seedPolicy === policy.seedPolicy &&
    id.purpose === policy.purpose && id.pathCount === policy.pathCount &&
    id.requestGeneration === requestGeneration ? envelope.value : null;
}
