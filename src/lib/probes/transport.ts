import type { WsMessage } from "./types";

export interface WorkerEndpoints {
  apiUrl: string | null;
  wsUrl: string | null;
  error: string | null;
}

/** Validate at the feature boundary so missing worker setup cannot crash other pages. */
export function resolveWorkerEndpoints(input: {
  environment: string | undefined;
  apiUrl?: string;
  wsUrl?: string;
}): WorkerEndpoints {
  const development = input.environment === "development";
  const api = input.apiUrl?.trim() || (development ? "http://localhost:8765" : "");
  const ws = input.wsUrl?.trim() || (development ? "ws://localhost:8765/ws" : "");
  try {
    if (!api || !ws) throw new Error("missing");
    const apiUrl = new URL(api);
    const wsUrl = new URL(ws);
    for (const [url, secure, insecure] of [
      [apiUrl, "https:", "http:"],
      [wsUrl, "wss:", "ws:"],
    ] as const) {
      const loopback = url.hostname === "localhost" || url.hostname.endsWith(".localhost") ||
        /^127\./.test(url.hostname) || url.hostname === "[::1]";
      if (url.username || url.password || url.search || url.hash ||
        (url.protocol !== secure && !(development && loopback && url.protocol === insecure)) ||
        (!development && loopback)) throw new Error("invalid");
    }
    return { apiUrl: apiUrl.href.replace(/\/$/, ""), wsUrl: wsUrl.href, error: null };
  } catch {
    return {
      apiUrl: null,
      wsUrl: null,
      error: "Configure NEXT_PUBLIC_VN_API_URL and NEXT_PUBLIC_VN_WS_URL with valid HTTPS/WSS worker endpoints. Localhost HTTP/WS is available only in development.",
    };
  }
}

export class WorkerRequestError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "WorkerRequestError";
    this.status = status;
  }
}

/** Shared UI limits mirror server/models.py; server validation remains authoritative. */
export const START_LIMITS = {
  gen0_count: { min: 2, max: 50, integer: true, label: "Initial probes" },
  max_probes: { min: 2, max: 100, integer: true, label: "Maximum probes" },
  max_capital: { min: 10, max: 1_000_000_000, integer: false, label: "Maximum capital" },
  seed_capital: { min: 10, max: 1_000_000_000, integer: false, label: "Capital per probe" },
  tick_interval_ms: { min: 100, max: 60_000, integer: true, label: "Tick interval (ms)" },
  mutation_rate: { min: 0, max: 0.5, integer: false, label: "Mutation rate" },
  reproduction_interval: { min: 1, max: 1_000_000, integer: true, label: "Reproduction interval" },
  max_lifespan_ticks: { min: 0, max: 10_000_000, integer: true, label: "Maximum lifespan" },
} as const;

const VALIDATION_FIELDS: Record<string, string> = {
  mode: "Trading mode", strategy: "Strategy", preset: "Preset", colony_config: "Colony configuration",
  gene_overrides: "Gene overrides", enabled_genes: "Enabled genes", available_assets: "Trading pairs",
  rsi_period: "RSI period", rsi_oversold: "RSI oversold", rsi_overbought: "RSI overbought",
  ema_fast: "EMA fast", ema_slow: "EMA slow", volume_threshold: "Volume threshold",
  position_size_pct: "Position size", stop_loss_pct: "Stop loss", take_profit_pct: "Take profit",
  max_open_positions: "Maximum positions", timeframe_minutes: "Timeframe",
  benchmark_target_pct: "Reproduction ROI", reproduce_target_dollars: "Reproduction profit",
  death_drawdown_pct: "Death drawdown", num_assets: "Asset count",
  min: "minimum", max: "maximum", fixed: "fixed value", default: "default value",
};

export function formatColonyFailure(code: unknown): string {
  const messages: Record<string, string> = {
    startup_failed: "Colony preparation failed. Review configuration and worker readiness before retrying.",
    startup_timeout: "Colony preparation exceeded its deadline.",
    startup_cancelled: "Colony preparation was cancelled.",
    persistence_failed: "Saving colony state failed. Execution stopped and reconciliation may be required.",
    execution_failed: "Colony execution failed and stopped. Reconciliation may be required.",
    feed_unavailable: "Current market data is unavailable. Execution stopped; verify the price and volume feeds before starting another run.",
    cleanup_failed: "Colony cleanup failed. Execution stopped; review worker diagnostics.",
  };
  return typeof code === "string" && Object.hasOwn(messages, code) ? messages[code] :
    "The colony failed. Review its saved history and worker diagnostics before launching another run.";
}

/** Render only known field paths and local messages, never arbitrary server text/input. */
export function formatWorkerValidation(body: unknown): string {
  const fallback = "Invalid colony configuration. Check capital, population, gene ranges, and selected assets.";
  if (!body || typeof body !== "object" || !("detail" in body) || !Array.isArray(body.detail)) return fallback;
  const messages = body.detail.slice(0, 12).flatMap((issue: unknown) => {
    if (!issue || typeof issue !== "object" || !("loc" in issue) || !Array.isArray(issue.loc)) return [];
    const path = issue.loc.filter((part: unknown) => part !== "body" && typeof part !== "number");
    if (path.length === 0 || !path.every((part: unknown) => typeof part === "string" &&
      (Object.hasOwn(START_LIMITS, part) || Object.hasOwn(VALIDATION_FIELDS, part)))) return [];
    const last = path.at(-1) as string;
    const limit = START_LIMITS[last as keyof typeof START_LIMITS];
    const label = path.map((part: string) => START_LIMITS[part as keyof typeof START_LIMITS]?.label ?? VALIDATION_FIELDS[part]).join(" / ");
    if (limit) return [`${label}: enter ${limit.integer ? "a whole number" : "a finite number"} from ${limit.min} to ${limit.max}.`];
    return [`${label}: review the selected value and related configuration limits.`];
  });
  return messages.length ? [...new Set(messages)].join(" ") : fallback;
}

export function colonyPath(colonyId: string, action?: "pause" | "resume" | "stop"): string {
  if (!colonyId.trim()) throw new Error("Select a colony first.");
  return `/api/v1/colonies/${encodeURIComponent(colonyId)}${action ? `/${action}` : ""}`;
}

export async function requestWorker<T>(
  endpoints: WorkerEndpoints,
  accessToken: string | null,
  path: string,
  options: { method?: "GET" | "POST"; body?: unknown; signal?: AbortSignal } = {},
  fetcher: typeof fetch = fetch,
): Promise<T> {
  if (endpoints.error || !endpoints.apiUrl) throw new Error(endpoints.error || "Worker is not configured.");
  if (!accessToken) throw new WorkerRequestError(401, "Sign in to access your colonies.");
  if (!path.startsWith("/api/v1/") || path.includes("?") || path.includes("#")) {
    throw new Error("Invalid worker request path.");
  }
  const response = await fetcher(`${endpoints.apiUrl}${path}`, {
    method: options.method ?? "GET",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: options.signal,
    credentials: "omit",
    redirect: "error",
    cache: "no-store",
  });
  if (!response.ok) {
    if (response.status === 422) {
      const body: unknown = await response.json().catch(() => null);
      throw new WorkerRequestError(422, formatWorkerValidation(body));
    }
    const message = response.status === 401 ? "Your session has expired. Sign in again." :
      response.status === 404 ? "This colony is no longer available." :
      response.status === 409 ? "The colony cannot perform this action in its current state. Refresh its status and try again." :
      response.status === 503 ? "The worker could not complete the operation. Refresh colony status before retrying; do not assume it started or stopped." :
      `Worker request failed (${response.status}).`;
    // Never echo response bodies that might contain credentials or private data.
    throw new WorkerRequestError(response.status, message);
  }
  return response.json() as Promise<T>;
}

/** Selection generations reject stale work, including an A -> B -> A round trip. */
export function createSelectionScope() {
  let generation = 0;
  let selected: string | null = null;
  let active = true;
  const requests = new Map<string, number>();
  return {
    select(colonyId: string | null) { selected = colonyId; generation += 1; },
    current() { return selected; },
    activate() { active = true; generation += 1; },
    dispose() { active = false; generation += 1; },
    begin(channel: string) {
      const request = (requests.get(channel) ?? 0) + 1;
      requests.set(channel, request);
      return { generation, channel, request, colonyId: selected };
    },
    isCurrent(ticket: { generation: number; channel: string; request: number }) {
      return active && ticket.generation === generation && requests.get(ticket.channel) === ticket.request;
    },
  };
}

export function belongsToSelectedColony(message: WsMessage, selected: string | null): boolean {
  return selected !== null && message.colony_id === selected;
}

type Socket = Pick<WebSocket, "onopen" | "onmessage" | "onclose" | "onerror" | "send" | "close">;
export interface SocketStatus { connected: boolean; error: string | null }

/** Disposable read-only session. The token is sent in the first frame, never the URL. */
export function openAuthenticatedSocket(options: {
  url: string;
  accessToken: string;
  userId: string;
  onMessage: (message: WsMessage) => void;
  onStatus: (status: SocketStatus) => void;
  createSocket?: (url: string) => Socket;
  schedule?: (callback: () => void, delay: number) => ReturnType<typeof setTimeout>;
  cancel?: (timer: ReturnType<typeof setTimeout>) => void;
  now?: () => number;
}) {
  const makeSocket = options.createSocket ?? ((url) => new WebSocket(url));
  const schedule = options.schedule ?? setTimeout;
  const cancel = options.cancel ?? clearTimeout;
  const now = options.now ?? Date.now;
  let socket: Socket | null = null;
  let disposed = false;
  let retries = 0;
  let reconnect: ReturnType<typeof setTimeout> | undefined;
  let deadline: ReturnType<typeof setTimeout> | undefined;

  function clearDeadline() { if (deadline !== undefined) cancel(deadline); deadline = undefined; }
  function retry() {
    if (disposed) return;
    if (retries >= 6) {
      options.onStatus({ connected: false, error: "Worker connection could not be restored. Reload to retry." });
      return;
    }
    const delay = Math.min(1000 * 2 ** retries++, 15000);
    reconnect = schedule(connect, delay);
  }
  function connect() {
    if (disposed) return;
    options.onStatus({ connected: false, error: null });
    let current: Socket;
    try { current = makeSocket(options.url); } catch { retry(); return; }
    socket = current;
    let authenticated = false;
    let permanentFailure = false;
    const isCurrent = () => !disposed && socket === current;
    deadline = schedule(() => { if (isCurrent()) current.close(4408, "Authentication timed out"); }, 7500);
    current.onopen = () => {
      if (!isCurrent() || permanentFailure) return;
      try { current.send(JSON.stringify({ type: "auth", access_token: options.accessToken })); }
      catch { current.close(); }
    };
    current.onmessage = (event) => {
      if (!isCurrent() || permanentFailure) return;
      let message: WsMessage;
      try { message = JSON.parse(String(event.data)); } catch { return; }
      if (!message || typeof message !== "object") return;
      if (!authenticated) {
        const expiresAt = message.data?.expires_at;
        if (message.type !== "auth_ok" || message.data?.user_id !== options.userId ||
          typeof expiresAt !== "number" || !Number.isFinite(expiresAt) || expiresAt * 1000 <= now()) {
          permanentFailure = true;
          options.onStatus({ connected: false, error: "Worker authentication failed. Sign in again." });
          current.close(4401, "Authentication failed");
          return;
        }
        authenticated = true;
        retries = 0;
        clearDeadline();
        options.onStatus({ connected: true, error: null });
        deadline = schedule(() => {
          if (!isCurrent()) return;
          permanentFailure = true;
          options.onStatus({ connected: false, error: "Your session has expired. Waiting for a refreshed session." });
          current.close(4401, "Session expired");
        }, Math.min(expiresAt * 1000 - now(), 2_147_483_647));
        return;
      }
      if (message.type === "auth_ok" || !message.data || typeof message.data !== "object") return;
      options.onMessage(message);
    };
    current.onclose = (event) => {
      if (!isCurrent()) return;
      socket = null;
      clearDeadline();
      const rejected = permanentFailure || [4400, 4401, 4403].includes(event.code);
      options.onStatus({ connected: false, error: rejected ? "Worker access was rejected. Check your session and the allowed dashboard origin." : "Worker disconnected. Reconnecting…" });
      if (!rejected) retry();
    };
    current.onerror = () => { if (isCurrent()) current.close(); };
  }
  connect();
  return () => {
    disposed = true;
    if (reconnect !== undefined) cancel(reconnect);
    clearDeadline();
    const retired = socket;
    socket = null;
    if (retired) {
      retired.onopen = retired.onmessage = retired.onclose = retired.onerror = null;
      retired.close();
    }
  };
}
