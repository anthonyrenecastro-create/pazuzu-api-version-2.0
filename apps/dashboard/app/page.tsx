"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  API_BASE,
  ApiResult,
  apiGet,
  apiPost,
  streamPost,
  GenerateResponse,
  StreamEvent,
} from "../lib/api";
import type { KeeperWatcherStatus } from "../lib/types";
import {
  demoExecution,
  demoStatus,
  demoStreamEvents,
} from "../lib/fixtures";
import StatusPill from "../components/StatusPill";
import DemoBadge from "../components/DemoBadge";

interface ShownEvent extends StreamEvent {
  live: boolean;
}

export default function ConsolePage() {
  const [prompt, setPrompt] = useState("");
  const [gen, setGen] = useState<ApiResult<GenerateResponse> | null>(null);
  const [status, setStatus] = useState<ApiResult<KeeperWatcherStatus> | null>(null);
  const [events, setEvents] = useState<ShownEvent[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<ShownEvent | null>(null);
  const [demoNote, setDemoNote] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    apiGet<KeeperWatcherStatus>("/v2/status", demoStatus).then(setStatus);
  }, []);

  const push = useCallback((e: StreamEvent, live: boolean) => {
    setEvents((prev) => [...prev, { ...e, live }]);
  }, []);

  const playDemoStream = useCallback(
    (requestId: string) => {
      const seq = demoStreamEvents(requestId);
      let i = 0;
      const timer = setInterval(() => {
        if (i >= seq.length) {
          clearInterval(timer);
          setStreaming(false);
          return;
        }
        push(seq[i], false);
        i += 1;
      }, 450);
      abortRef.current = null;
    },
    [push],
  );

  const handleGenerate = async () => {
    if (!prompt.trim() || busy) return;
    setBusy(true);
    setDemoNote(null);
    const res = await apiPost<GenerateResponse>(
      "/v2/generate",
      { prompt },
      demoExecution,
    );
    setGen(res);
    if (res.demo) setDemoNote(res.error ?? "backend unreachable");
    setBusy(false);
  };

  const handleStream = async () => {
    if (!prompt.trim() || streaming) return;
    abortRef.current?.abort();
    const ctl = new AbortController();
    abortRef.current = ctl;
    setEvents([]);
    setSelected(null);
    setStreaming(true);
    setDemoNote(null);
    const requestId = gen?.data.execution.request_id ?? `req-${Date.now()}`;
    try {
      await streamPost("/v2/stream", { prompt }, (e) => push(e, true), ctl.signal);
      setStreaming(false);
    } catch (e) {
      // Backend unreachable: clearly-labeled demo replay.
      setDemoNote(e instanceof Error ? e.message : "stream failed");
      playDemoStream(requestId);
    }
  };

  const stopStream = () => {
    abortRef.current?.abort();
    setStreaming(false);
  };

  const exec = gen?.data.execution ?? null;
  const verification = exec?.verification as
    | { passed?: boolean; checks?: { name: string; passed: boolean }[] }
    | null
    | undefined;

  return (
    <div>
      <div className="page-head">
        <h1>Intelligence Console</h1>
        {(gen?.demo || status?.demo) && <DemoBadge reason={demoNote ?? undefined} />}
        <p>
          Submit a prompt to <code>POST /v2/generate</code>; watch the live
          verdict stream from <code>POST /v2/stream</code>.
        </p>
      </div>

      <div className="toolbar">
        <span className="chip" title="Keeper service status">
          <span className={`dot dot-${status?.data.keeper.status ?? "unknown"}`} />
          Keeper&nbsp;<StatusPill value={status?.data.keeper.status ?? "unknown"} />
          &nbsp;q={status?.data.keeper.queue_depth ?? "–"}
        </span>
        <span className="chip" title="Watcher service status">
          <span className={`dot dot-${status?.data.watcher.status ?? "unknown"}`} />
          Watcher&nbsp;<StatusPill value={status?.data.watcher.status ?? "unknown"} />
          &nbsp;q={status?.data.watcher.queue_depth ?? "–"}
        </span>
        {status?.demo && <span className="note">Keeper/Watcher status is DEMO data.</span>}
      </div>

      <div className="panel">
        <h2>Prompt</h2>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Enter a prompt for the twelve-station pipeline…"
        />
        <div className="toolbar" style={{ marginTop: 10, marginBottom: 0 }}>
          <button className="btn btn-primary" onClick={handleGenerate} disabled={busy || !prompt.trim()}>
            {busy ? "Generating…" : "Generate (POST /v2/generate)"}
          </button>
          <button className="btn" onClick={handleStream} disabled={streaming || !prompt.trim()}>
            {streaming ? "Streaming…" : "Stream verdicts (POST /v2/stream)"}
          </button>
          {streaming && (
            <button className="btn btn-danger" onClick={stopStream}>Stop</button>
          )}
        </div>
      </div>

      <div className="grid2">
        <div className="panel">
          <h2>
            Stream viewer {events.some((e) => !e.live) && <DemoBadge reason="demo replay — backend stream unavailable" />}
          </h2>
          <div className="stream-log">
            {events.length === 0 && (
              <p className="note">No events yet. Submit a prompt and start the stream.</p>
            )}
            {events.map((e, i) => (
              <div
                key={i}
                className={`event event-${e.type}`}
                onClick={() => setSelected(e)}
                style={{ cursor: "pointer" }}
                title="Click to inspect provenance"
              >
                <span className="etype">{e.type}</span>
                {e.segment_index !== undefined && (
                  <span style={{ color: "var(--text-dim)" }}> · seg {e.segment_index}</span>
                )}
                {e.decision && (
                  <span> · <StatusPill value={e.decision} /></span>
                )}
                {!e.live && <span> · <DemoBadge /></span>}
                {e.text && <div style={{ marginTop: 4 }}>{e.text}</div>}
                {e.detail && <pre>{JSON.stringify(e.detail, null, 2)}</pre>}
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="panel">
            <h2>Provenance inspector</h2>
            {selected ? (
              <dl className="kv">
                <dt>event</dt><dd>{selected.type}</dd>
                <dt>request_id</dt><dd>{selected.request_id}</dd>
                <dt>live</dt><dd>{selected.live ? "yes (backend)" : "no — DEMO replay"}</dd>
                <dt>segment</dt><dd>{selected.segment_index ?? "—"}</dd>
                <dt>decision</dt><dd>{selected.decision ?? "—"}</dd>
                <dt>text</dt><dd style={{ fontFamily: "inherit" }}>{selected.text ?? "—"}</dd>
              </dl>
            ) : (
              <p className="note">Click a stream event to inspect its provenance.</p>
            )}
            {exec && (
              <>
                <h2 style={{ marginTop: 16 }}>Execution provenance</h2>
                <dl className="kv">
                  <dt>request_id</dt><dd>{exec.request_id}</dd>
                  <dt>correlation_id</dt><dd>{exec.correlation_id}</dd>
                  <dt>plan_version</dt><dd>{exec.plan_version}</dd>
                  <dt>status</dt><dd><StatusPill value={exec.status} /></dd>
                  <dt>created_at</dt><dd>{exec.created_at}</dd>
                </dl>
              </>
            )}
          </div>

          <div className="panel">
            <h2>Verification results {gen?.demo && <DemoBadge />}</h2>
            {!gen && <p className="note">Run Generate to see verification output.</p>}
            {gen && (
              <>
                <p>
                  Overall:{" "}
                  <StatusPill value={verification?.passed ? "approved" : "rejected"} />
                </p>
                <table>
                  <thead><tr><th>Check</th><th>Result</th></tr></thead>
                  <tbody>
                    {(verification?.checks ?? []).map((c) => (
                      <tr key={c.name}>
                        <td><code>{c.name}</code></td>
                        <td><StatusPill value={c.passed ? "approved" : "rejected"} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {exec?.final_text && (
                  <>
                    <h2 style={{ marginTop: 16 }}>Final text</h2>
                    <p style={{ whiteSpace: "pre-wrap" }}>{exec.final_text}</p>
                  </>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
