/**
 * Typed API client for PAZUZU-API v2.0.
 * Every helper attempts the real backend endpoint FIRST. Only when the fetch
 * fails (backend down / route missing / non-2xx) does it fall back to the
 * supplied fixture — and the result is flagged `demo: true` so the UI MUST
 * render a visible DEMO badge. Never invent live statistics.
 */
import type {
  AuditRecord,
  ExecutionRecord,
  FormalismEntry,
  QuarantineRecord,
  StationManifest,
  StreamEvent,
} from "../../../packages/contracts/typescript";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ApiResult<T> {
  data: T;
  /** true when the data came from a local fixture instead of the backend */
  demo: boolean;
  error?: string;
}

type Fixture<T> = T | (() => T);
const resolve = <T>(f: Fixture<T>): T =>
  typeof f === "function" ? (f as () => T)() : f;

async function readJson(res: Response): Promise<unknown> {
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`non-JSON response (HTTP ${res.status})`);
  }
}

export async function apiGet<T>(
  path: string,
  fixture: Fixture<T>,
): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "GET",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status} from ${path}`);
    return { data: (await readJson(res)) as T, demo: false };
  } catch (e) {
    return {
      data: resolve(fixture),
      demo: true,
      error: e instanceof Error ? e.message : "fetch failed",
    };
  }
}

export async function apiPost<T>(
  path: string,
  body: unknown,
  fixture: Fixture<T>,
): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status} from ${path}`);
    return { data: (await readJson(res)) as T, demo: false };
  } catch (e) {
    return {
      data: resolve(fixture),
      demo: true,
      error: e instanceof Error ? e.message : "fetch failed",
    };
  }
}

export async function apiDelete<T>(
  path: string,
  fixture: Fixture<T>,
): Promise<ApiResult<T>> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "DELETE",
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`HTTP ${res.status} from ${path}`);
    return { data: (await readJson(res)) as T, demo: false };
  } catch (e) {
    return {
      data: resolve(fixture),
      demo: true,
      error: e instanceof Error ? e.message : "fetch failed",
    };
  }
}

/** Result of one SSE push; `live: false` means the event is a demo replay. */
export interface PushedEvent {
  event: StreamEvent;
  live: boolean;
}

/**
 * POSTs to an SSE endpoint and pushes parsed `data:` payloads to `onEvent`.
 * Throws when the live stream cannot be established — the caller may then run
 * a clearly-labeled demo replay.
 */
export async function streamPost(
  path: string,
  body: unknown,
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`HTTP ${res.status} from ${path}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop() ?? "";
    for (const frame of frames) {
      for (const line of frame.split("\n")) {
        const m = line.match(/^data:\s*(.*)$/);
        if (!m) continue;
        const trimmed = m[1].trim();
        if (trimmed === "[DONE]") return;
        try {
          onEvent(JSON.parse(trimmed) as StreamEvent);
        } catch {
          /* ignore malformed frame */
        }
      }
    }
  }
}

// Re-exported contract types for convenient page imports.
export type {
  AuditRecord,
  Decision,
  ExecutionRecord,
  FormalismEntry,
  Provenance,
  QuarantineRecord,
  StationManifest,
  StationOutput,
  StationStatus,
  StreamEvent,
  Telemetry,
} from "../../../packages/contracts/typescript";

// Dashboard-side shapes (backend-defined) for convenient page imports.
export type {
  AuditResponse,
  GenerateResponse,
  KeeperWatcherStatus,
  MemoryCell,
  MemoryRetrieval,
  MetricsReport,
  SwarmReport,
  VmCompileResult,
  VmSimulateResult,
  WardReport,
  WindField,
} from "./types";
