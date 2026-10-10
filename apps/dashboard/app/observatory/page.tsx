"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import ReactFlow, {
  Background,
  Controls,
  Edge,
  Node,
  NodeMouseHandler,
} from "reactflow";
import "reactflow/dist/style.css";
import {
  ApiResult,
  apiGet,
  GenerateResponse,
  StationManifest,
  StationOutput,
} from "../../lib/api";
import { demoExecution, demoStations } from "../../lib/fixtures";
import StatusPill from "../../components/StatusPill";
import DemoBadge from "../../components/DemoBadge";

const COLS = 6;
const DX = 215;
const DY = 175;

export default function ObservatoryPage() {
  const [manifests, setManifests] = useState<ApiResult<StationManifest[]> | null>(null);
  const [execRes, setExecRes] = useState<ApiResult<GenerateResponse> | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    apiGet<StationManifest[]>("/v2/stations", demoStations).then(setManifests);
    apiGet<GenerateResponse>("/v2/executions/latest", demoExecution).then(setExecRes);
  }, []);

  const list = manifests?.data ?? [];
  const outputs = execRes?.data.execution.station_outputs ?? {};

  const nodes: Node[] = useMemo(
    () =>
      list.map((m, i) => {
        const out: StationOutput | undefined = outputs[m.id];
        const status = out?.status ?? "skipped";
        const critical = m.critical_path;
        return {
          id: m.id,
          position: { x: (i % COLS) * DX, y: Math.floor(i / COLS) * DY },
          data: { label: `${m.id} · ${m.name}` },
          style: {
            background: "#241b13",
            border: `2px solid ${critical ? "#e8b04b" : "#3a2c1e"}`,
            borderRadius: 8,
            color: "#e8ddd0",
            fontSize: 12,
            padding: 10,
            width: 190,
            boxShadow: critical ? "0 0 12px rgba(232,176,75,0.35)" : undefined,
          },
        };
      }),
    [list, outputs],
  );

  const edges: Edge[] = useMemo(
    () =>
      list.slice(0, -1).map((m, i) => {
        const next = list[i + 1];
        const hot = m.critical_path && next.critical_path;
        return {
          id: `e-${m.id}-${next.id}`,
          source: m.id,
          target: next.id,
          animated: hot,
          style: {
            stroke: hot ? "#e8b04b" : "#3a2c1e",
            strokeWidth: hot ? 3 : 1.5,
          },
        };
      }),
    [list],
  );

  const onNodeClick: NodeMouseHandler = useCallback((_, node) => {
    setSelected(node.id);
  }, []);

  const selManifest = list.find((m) => m.id === selected) ?? null;
  const selOutput: StationOutput | undefined = selected ? outputs[selected] : undefined;
  const demo = manifests?.demo || execRes?.demo;

  return (
    <div>
      <div className="page-head">
        <h1>Twelve-Station Observatory</h1>
        {demo && <DemoBadge reason={execRes?.error ?? manifests?.error} />}
        <p>
          Live station graph from <code>GET /v2/stations</code> and execution
          records from <code>GET /v2/executions/latest</code>. Gold edges trace
          the critical path.
        </p>
      </div>

      <div className="panel" style={{ height: 520, padding: 0 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodeClick={onNodeClick}
          fitView
        >
          <Background color="#3a2c1e" />
          <Controls />
        </ReactFlow>
      </div>

      <div className="panel">
        <h2>Station ledger</h2>
        <table>
          <thead>
            <tr>
              <th>Station</th><th>Name</th><th>Status</th>
              <th>Duration</th><th>Critical</th><th>Warnings</th>
            </tr>
          </thead>
          <tbody>
            {list.map((m) => {
              const out = outputs[m.id];
              return (
                <tr key={m.id} onClick={() => setSelected(m.id)} style={{ cursor: "pointer" }}>
                  <td><code>{m.id}</code></td>
                  <td>{m.name}</td>
                  <td>{out ? <StatusPill value={out.status} /> : <StatusPill value="skipped" />}</td>
                  <td style={{ fontFamily: "ui-monospace, monospace" }}>
                    {out ? `${out.telemetry.duration_ms} ms` : "—"}
                  </td>
                  <td>{m.critical_path ? "★" : "—"}</td>
                  <td>{out?.warnings.length ? out.warnings.join("; ") : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {selManifest && (
        <div className="drawer">
          <div className="toolbar">
            <h2 style={{ margin: 0 }}>{selManifest.id} · {selManifest.name}</h2>
            <button className="btn" onClick={() => setSelected(null)}>Close</button>
          </div>
          {demo && <DemoBadge />}
          <dl className="kv">
            <dt>version</dt><dd>{selManifest.version}</dd>
            <dt>critical path</dt><dd>{selManifest.critical_path ? "yes" : "no"}</dd>
            <dt>description</dt><dd style={{ fontFamily: "inherit" }}>{selManifest.description}</dd>
            <dt>status</dt><dd>{selOutput ? <StatusPill value={selOutput.status} /> : "no record"}</dd>
          </dl>
          {selOutput && (
            <>
              <h2>Inputs / outputs</h2>
              <pre className="json">{JSON.stringify(selOutput.data, null, 2)}</pre>
              <h2>Telemetry</h2>
              <dl className="kv">
                <dt>duration</dt><dd>{selOutput.telemetry.duration_ms} ms</dd>
                <dt>tokens in/out</dt><dd>{selOutput.telemetry.tokens_in} / {selOutput.telemetry.tokens_out}</dd>
                <dt>cost</dt><dd>${selOutput.telemetry.cost_usd.toFixed(4)}</dd>
                <dt>input hash</dt><dd>{selOutput.provenance.input_hash}</dd>
                <dt>actor</dt><dd>{selOutput.provenance.actor}</dd>
                <dt>created</dt><dd>{selOutput.provenance.created_at}</dd>
              </dl>
              <h2>Warnings</h2>
              {selOutput.warnings.length ? (
                <ul>{selOutput.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
              ) : (
                <p className="note">None.</p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
