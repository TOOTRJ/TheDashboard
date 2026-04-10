import type { ProbeState } from "./types";

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

export const VN_API_URL =
  process.env.NEXT_PUBLIC_VN_API_URL || "http://localhost:8765";
export const VN_WS_URL =
  process.env.NEXT_PUBLIC_VN_WS_URL || "ws://localhost:8765/ws";
export const VN_API_KEY =
  process.env.VN_API_KEY || "vn-dev-key-8be90a19744ac928";

export const STRATEGY_LABELS: Record<string, string> = {
  genetic_algorithm: "Genetic Algorithm",
  differential_evolution: "Differential Evolution",
  particle_swarm: "Particle Swarm Optimization",
  cma_es: "CMA-ES",
};

export const STRATEGY_DESCRIPTIONS: Record<string, string> = {
  genetic_algorithm: "Classic GA with tournament selection, uniform crossover, and Gaussian mutation.",
  differential_evolution: "DE/rand/1/bin -- differential mutation with binomial crossover.",
  particle_swarm: "PSO with inertia weight, cognitive and social components.",
  cma_es: "Covariance Matrix Adaptation Evolution Strategy.",
};
