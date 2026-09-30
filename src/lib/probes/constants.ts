import type { ProbeState } from "./types";
import { resolveWorkerEndpoints } from "./transport";

// Re-export gene definitions from the registry (single source of truth)
export { GENE_BOUNDS, GENE_LABELS, GENE_DEFINITIONS, ALL_ASSETS } from "./gene-registry";

export const STATE_COLORS: Record<ProbeState, string> = {
  BORN: "#00fff5",
  FUNDED: "#ffff00",
  OBSERVING: "#bf00ff",
  TRADING: "#39ff14",
  REPRODUCING: "#ff00ff",
  DYING: "#ff6600",
  DEAD: "#7a7a8c",
};

export const STATE_LABELS: Record<ProbeState, string> = {
  BORN: "Born",
  FUNDED: "Funded",
  OBSERVING: "Observing",
  TRADING: "Trading",
  REPRODUCING: "Reproducing",
  DYING: "Dying",
  DEAD: "Dead",
};

export const VN_ENDPOINTS = resolveWorkerEndpoints({
  environment: process.env.NODE_ENV,
  apiUrl: process.env.NEXT_PUBLIC_VN_API_URL,
  wsUrl: process.env.NEXT_PUBLIC_VN_WS_URL,
});

export const STRATEGY_LABELS: Record<string, string> = {
  genetic_algorithm: "Genetic Algorithm",
  differential_evolution: "Differential Evolution",
  particle_swarm: "Window-reset Swarm (PSO variant)",
  cma_es: "CMA-ES",
};

export const STRATEGY_DESCRIPTIONS: Record<string, string> = {
  genetic_algorithm: "Classic GA with tournament selection, uniform crossover, and Gaussian mutation.",
  differential_evolution: "Paired DE/rand/1/bin: targets and trials compete over the same market window.",
  particle_swarm: "Normalized social swarm with inertia and best scores reset each market window.",
  cma_es: "CMA-ES over normalized active genes with exact sampled-candidate evaluation.",
};
