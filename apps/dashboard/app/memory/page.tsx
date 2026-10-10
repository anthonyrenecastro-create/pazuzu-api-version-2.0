"use client";
import { useEffect, useMemo, useState } from "react";
import { ApiResult, apiDelete, apiGet, apiPost } from "../../lib/api";
import type { MemoryCell, MemoryRetrieval } from "../../lib/types";
import { demoCells, demoRetrievals } from "../../lib/fixtures";
import DemoBadge from "../../components/DemoBadge";

const TEMP_COLOR: Record<MemoryCell["temperature"], string> = {
  hot: "#e8b04b",
  warm: "#c98a3d",
  cold: "#5b7a99",
};

const R = 150;
const CX = 170;
const CY = 170;

function arcPath(index: number): string {
  const a0 = (index / 60) * Math.PI * 2 - Math.PI / 2;
  const a1 = ((index + 0.92) / 60) * Math.PI * 2 - Math.PI / 2;
  const x0 = CX + R * Math.cos(a0), y0 = CY + R * Math.sin(a0);
  const x1 = CX + R * Math.cos(a1), y1 = CY + R * Math.sin(a1);
  return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${R} ${R} 0 0 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

export default function MemoryPage() {
  const [cells, setCells] = useState<ApiResult<MemoryCell[]> | null>(null);
  const [retrievals, setRetrievals] = useState<ApiResult<MemoryRetrieval[]> | null>(null);
  const [selected, setSelected] = useState<MemoryCell | null>(null);
  const [label, setLabel] = useState("");
  const [temp, setTemp] = useState<MemoryCell["temperature"]>("warm");
  const [busy, setBusy] = useState(false);

  const load = () => {
    apiGet<MemoryCell[]>("/v2/memory", demoCells).then(setCells);
    apiGet<MemoryRetrieval[]>("/v2/memory/retrievals", demoRetrievals).then(setRetrievals);
  };
  useEffect(load, []);

  const counts = useMemo(() => {
    const c = { hot: 0, warm: 0, cold: 0, pinned: 0 };
    for (const cell of cells?.data ?? []) {
      c[cell.temperature] += 1;
      if (cell.pinned) c.pinned += 1;
    }
    return c;
  }, [cells]);

  const demo = cells?.demo || retrievals?.demo;

  const createCell = async () => {
    if (busy) return;
    setBusy(true);
    const body = { label: label || "untitled", temperature: temp };
    const res = await apiPost<MemoryCell>("/v2/memory", body, () => ({
      id: `cell-demo-${Date.now()}`,
      index: (cells?.data.length ?? 0) % 60,
      temperature: temp,
      pinned: false,
      label: body.label,
      updated_at: new Date().toISOString(),
    }));
    if (res.demo) {
      // Simulate the create locally so the demo stays interactive.
      setCells((prev) =>
        prev ? { ...prev, data: [...prev.data, res.data] } : prev,
      );
    } else {
      load();
    }
    setLabel("");
    setBusy(false);
  };

  const togglePin = async (cell: MemoryCell) => {
    if (busy) return;
    setBusy(true);
    const res = await apiPost<MemoryCell>(
      `/v2/memory/${cell.id}/pin`,
      { pinned: !cell.pinned },
      () => ({ ...cell, pinned: !cell.pinned }),
    );
    if (res.demo) {
      setCells((prev) =>
        prev
          ? { ...prev, data: prev.data.map((c) => (c.id === cell.id ? res.data : c)) }
          : prev,
      );
      if (selected?.id === cell.id) setSelected(res.data);
    } else {
      load();
    }
    setBusy(false);
  };

  const removeCell = async (cell: MemoryCell) => {
    if (busy) return;
    setBusy(true);
    const res = await apiDelete<{ ok: boolean }>(`/v2/memory/${cell.id}`, () => ({ ok: true }));
    if (res.demo) {
      setCells((prev) =>
        prev ? { ...prev, data: prev.data.filter((c) => c.id !== cell.id) } : prev,
      );
      if (selected?.id === cell.id) setSelected(null);
    } else {
      load();
    }
    setBusy(false);
  };

  return (
    <div>
      <div className="page-head">
        <h1>Sexagesimal Memory Ring</h1>
        {demo && <DemoBadge reason={cells?.error ?? retrievals?.error} />}
        <p>
          Sixty cells around the ring, colored by temperature. CRUD via{" "}
          <code>/v2/memory</code>. Pinned cells are marked with a gold dot.
        </p>
      </div>

      <div className="grid2">
        <div className="panel">
          <h2>Ring · 60 segments</h2>
          <div className="ring-wrap">
            <svg width={CX * 2} height={CY * 2} role="img" aria-label="60-segment memory ring">
              <circle cx={CX} cy={CY} r={R - 14} fill="none" stroke="#3a2c1e" strokeWidth={1} />
              {(cells?.data ?? []).slice(0, 60).map((cell) => (
                <g key={cell.id}>
                  <path
                    d={arcPath(cell.index % 60)}
                    stroke={TEMP_COLOR[cell.temperature]}
                    strokeWidth={selected?.id === cell.id ? 14 : 9}
                    fill="none"
                    opacity={selected?.id === cell.id ? 1 : 0.85}
                    style={{ cursor: "pointer" }}
                    onClick={() => setSelected(cell)}
                  >
                    <title>{`${cell.id} · ${cell.temperature}${cell.pinned ? " · pinned" : ""}`}</title>
                  </path>
                  {cell.pinned && (
                    <circle
                      cx={CX + (R + 16) * Math.cos(((cell.index % 60) / 60) * Math.PI * 2 - Math.PI / 2)}
                      cy={CY + (R + 16) * Math.sin(((cell.index % 60) / 60) * Math.PI * 2 - Math.PI / 2)}
                      r={4}
                      fill="#e8b04b"
                    />
                  )}
                </g>
              ))}
            </svg>
            <div>
              <div className="legend">
                <span><span className="sw" style={{ background: TEMP_COLOR.hot }} />hot ({counts.hot})</span>
                <span><span className="sw" style={{ background: TEMP_COLOR.warm }} />warm ({counts.warm})</span>
                <span><span className="sw" style={{ background: TEMP_COLOR.cold }} />cold ({counts.cold})</span>
                <span><span className="sw" style={{ background: "#e8b04b", borderRadius: "50%" }} />pinned ({counts.pinned})</span>
              </div>
              {selected && (
                <div className="card" style={{ marginTop: 12 }}>
                  <h3>{selected.id}</h3>
                  <dl className="kv">
                    <dt>label</dt><dd style={{ fontFamily: "inherit" }}>{selected.label}</dd>
                    <dt>temperature</dt><dd>{selected.temperature}</dd>
                    <dt>pinned</dt><dd>{selected.pinned ? "yes" : "no"}</dd>
                    <dt>updated</dt><dd>{selected.updated_at}</dd>
                  </dl>
                  <div className="toolbar" style={{ marginBottom: 0 }}>
                    <button className="btn" onClick={() => togglePin(selected)} disabled={busy}>
                      {selected.pinned ? "Unpin" : "Pin"}
                    </button>
                    <button className="btn btn-danger" onClick={() => removeCell(selected)} disabled={busy}>
                      Delete
                    </button>
                  </div>
                  {demo && <p className="note">Demo mode: pin/delete mutate the local fixture only.</p>}
                </div>
              )}
            </div>
          </div>
        </div>

        <div>
          <div className="panel">
            <h2>Write a cell (POST /v2/memory)</h2>
            <label>Label</label>
            <input type="text" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="cell label" />
            <label>Temperature</label>
            <select value={temp} onChange={(e) => setTemp(e.target.value as MemoryCell["temperature"])}>
              <option value="hot">hot</option>
              <option value="warm">warm</option>
              <option value="cold">cold</option>
            </select>
            <div className="toolbar" style={{ marginTop: 10, marginBottom: 0 }}>
              <button className="btn btn-primary" onClick={createCell} disabled={busy}>Create cell</button>
            </div>
          </div>

          <div className="panel">
            <h2>Retrieval events</h2>
            <table>
              <thead><tr><th>At</th><th>Cell</th><th>Query</th><th>Hit</th></tr></thead>
              <tbody>
                {(retrievals?.data ?? []).map((r, i) => (
                  <tr key={i}>
                    <td style={{ fontFamily: "ui-monospace, monospace", fontSize: 12 }}>{r.at}</td>
                    <td><code>{r.cell_id}</code></td>
                    <td>{r.query}</td>
                    <td>{r.hit ? <span className="pill pill-ok">hit</span> : <span className="pill pill-muted">miss</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
