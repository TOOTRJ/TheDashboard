import { ApiInputError } from "./errors";
import type { SentimentPayload } from "./types";

export const API_BODY_BYTES = 65_536;
export const API_JSON_DEPTH = 16;
export const API_JSON_NODES = 10_000;
const encoder = new TextEncoder();

function invalid(message: string): never {
  throw new ApiInputError(message);
}

function validString(value: string) {
  for (let i = 0; i < value.length; i++) {
    const code = value.charCodeAt(i);
    if (code === 0) invalid("JSON strings and keys cannot contain NUL");
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(++i);
      if (!(next >= 0xdc00 && next <= 0xdfff)) invalid("JSON strings and keys must contain valid Unicode");
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      invalid("JSON strings and keys must contain valid Unicode");
    }
  }
}

export function validateJsonObject(body: unknown): Record<string, unknown> {
  if (body === null || typeof body !== "object" || Array.isArray(body)) {
    invalid("Request body must be a valid JSON object");
  }
  const stack: Array<{ value: unknown; depth: number }> = [{ value: body, depth: 0 }];
  let nodes = 0;
  while (stack.length) {
    const { value, depth } = stack.pop()!;
    if (++nodes > API_JSON_NODES) invalid("JSON body has too many nodes");
    if (typeof value === "string") validString(value);
    else if (typeof value === "number") {
      if (!Number.isFinite(value)) invalid("JSON numbers must be finite");
    } else if (value !== null && typeof value === "object") {
      if (depth >= API_JSON_DEPTH) invalid("JSON body is too deeply nested");
      if (Array.isArray(value)) {
        for (const item of value) stack.push({ value: item, depth: depth + 1 });
      } else {
        for (const [key, item] of Object.entries(value)) {
          if (++nodes > API_JSON_NODES) invalid("JSON body has too many nodes");
          validString(key);
          stack.push({ value: item, depth: depth + 1 });
        }
      }
      if (nodes + stack.length > API_JSON_NODES) invalid("JSON body has too many nodes");
    } else if (value !== null && typeof value !== "boolean") {
      invalid("Request body contains an unsupported JSON value");
    }
  }
  return body as Record<string, unknown>;
}

export async function readJsonObject(request: Pick<Request, "body">): Promise<Record<string, unknown>> {
  if (!request.body) invalid("Request body must be a valid JSON object");
  const reader = request.body.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      if (!(value instanceof Uint8Array)) invalid("Request body must be UTF-8 JSON");
      if (value.byteLength === 0) continue;
      total += value.byteLength;
      if (total > API_BODY_BYTES) {
        try { void reader.cancel().catch(() => {}); } catch { /* Best-effort cancellation. */ }
        invalid("Request body exceeds 65536 bytes");
      }
      chunks.push(value.slice());
    }
    const raw = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) { raw.set(chunk, offset); offset += chunk.byteLength; }
    const text = new TextDecoder("utf-8", { fatal: true }).decode(raw);
    return validateJsonObject(JSON.parse(text));
  } catch (error) {
    if (error instanceof ApiInputError) throw error;
    return invalid("Request body must be valid UTF-8 JSON");
  } finally {
    try { reader.releaseLock(); } catch { /* Never replace the original validation failure. */ }
  }
}

export function validateLimit(params: URLSearchParams): number {
  const limits = params.getAll("limit");
  if (limits.length === 0) return 50;
  if (limits.length !== 1 || !/^(0|[1-9][0-9]{0,2})$/.test(limits[0])) {
    invalid("limit must be exactly one integer between 0 and 100");
  }
  const limit = Number(limits[0]);
  if (limit > 100) invalid("limit must be exactly one integer between 0 and 100");
  return limit;
}

export function validateSource(value: string | null): string {
  if (value === null || value === "") return "unknown";
  validString(value);
  if (encoder.encode(value).byteLength > 128 || /[\u0000-\u001f\u007f-\u009f]/.test(value)) {
    invalid("source must be at most 128 UTF-8 bytes without control characters");
  }
  return value;
}

export function validCalendarDate(value: string): boolean {
  if (!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(value)) return false;
  const year = Number(value.slice(0, 4)), month = Number(value.slice(5, 7)), day = Number(value.slice(8, 10));
  if (year < 1 || month < 1 || month > 12 || day < 1) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day <= days[month - 1];
}

export function validateSentiment(value: unknown): SentimentPayload {
  const body = validateJsonObject(value);
  const allowed = new Set(["score", "sentiment", "summary", "key_factors", "date"]);
  if (Object.keys(body).some(key => !allowed.has(key))) invalid("Request contains unsupported fields");
  if (typeof body.score !== "number" || !Number.isFinite(body.score) || body.score < 0 || body.score > 100) {
    invalid("score must be a finite number between 0 and 100");
  }
  if (body.sentiment !== "bullish" && body.sentiment !== "bearish" && body.sentiment !== "neutral") {
    invalid("sentiment must be bullish, bearish, or neutral");
  }
  if (typeof body.summary !== "string" || body.summary.trim() === "" || encoder.encode(body.summary).byteLength > 4096) {
    invalid("summary must be nonempty and at most 4096 UTF-8 bytes");
  }
  if (!Array.isArray(body.key_factors) || body.key_factors.length > 64 || body.key_factors.some(
    value => typeof value !== "string" || encoder.encode(value).byteLength > 256)) {
    invalid("key_factors must contain at most 64 strings of at most 256 UTF-8 bytes");
  }
  if (Object.hasOwn(body, "date") && (typeof body.date !== "string" || !validCalendarDate(body.date))) {
    invalid("date must be a valid calendar date in YYYY-MM-DD format");
  }
  return { score: body.score, sentiment: body.sentiment, summary: body.summary,
    key_factors: body.key_factors as string[], ...(Object.hasOwn(body, "date") ? { date: body.date as string } : {}) };
}
