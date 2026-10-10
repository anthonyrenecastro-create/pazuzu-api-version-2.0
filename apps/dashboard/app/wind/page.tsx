"use client";
import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ApiResult, apiGet, GenerateResponse } from "../../lib/api";
import type { WindField } from "../../lib/types";
import { demoExecution, demoWind } from "../../lib/fixtures";
import DemoBadge from "../../components/DemoBadge";

const tooltipStyle = {
  backgroundColor: "#1e1712",
  border: "1px solid #3a2c1e",
  color: "#e8ddd0",
  fontSize: 12,
};

export default function WindPage() {
  const [wind, setWind] = useState<ApiResult<WindField> | null>(null);

  useEffect(() => {
    // S05 output data lives on the latest execution record; /v2/wind is a
    // convenience alias the backend may expose. Try the record first.
    apiGet<GenerateResponse>("/v2/executions/latest", demoExecution).then(
      (res) => {
        const s05 = res.data.execution.station_outputs["S05"];
        const data = s05?.data as unknown as Partial<WindField> | undefined;
        if (!res.demo && data?.drift_series) {
          setWind({ data: data as WindField, demo: false });
        } else {
          apiGet<WindField>("/v2/wind", demoWind).then(setWind);
        }
      },
    );
  }, []);

  const w = wind?.data ?? null;
  const branchData = w
    ? w.drift_series.map((p) => {
        const row: Record<string, number> = { t: p.t, drift: p.drift, baseline: p.baseline };
        for (const b of w.branches) {
          const bp = b.points.find((q) => q.t === p.t);
          if (bp) row[b.name] = bp.drift;
        }
        return row;
      })
    : [];

  return (
    <div>
      <div className="page-head">
        <h1>Wind Field Observatory</h1>
        {wind?.demo && <DemoBadge reason={wind.error} />}
        <p>
          Drift trajectory from S05 (Vector Current) output — via{" "}
          <code>GET /v2/executions/latest</code> with <code>GET /v2/wind</code>{" "}
          fallback — plus contradiction markers and branch comparison.
        </p>
      </div>

      <div className="panel">
        <h2>Drift trajectory vs baseline</h2>
        <div style={{ height: 320 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={branchData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="#3a2c1e" strokeDasharray="3 3" />
              <XAxis dataKey="t" stroke="#a89680" fontSize={11} label={{ value: "breath t", fill: "#a89680", fontSize: 11, position: "insideBottomRight" }} />
              <YAxis stroke="#a89680" fontSize={11} />
              <Tooltip contentStyle={tooltipStyle} />
              <Legend />
              <Line type="monotone" dataKey="drift" stroke="#e8b04b" dot={false} strokeWidth={2} name="drift" />
              <Line type="monotone" dataKey="baseline" stroke="#5b7a99" dot={false} strokeDasharray="5 5" name="baseline" />
              {(w?.contradictions ?? []).map((c, i) => (
                <ReferenceDot
                  key={i}
                  x={c.t}
                  y={branchData[c.t]?.drift ?? 0}
                  r={7}
                  fill="#c8553d"
                  stroke="#e8ddd0"
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="legend">
          <span><span className="sw" style={{ background: "#c8553d" }} />contradiction marker</span>
        </div>
      </div>

      <div className="grid2">
        <div className="panel">
          <h2>Branch comparison</h2>
          <div style={{ height: 280 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={branchData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
                <CartesianGrid stroke="#3a2c1e" strokeDasharray="3 3" />
                <XAxis dataKey="t" stroke="#a89680" fontSize={11} />
                <YAxis stroke="#a89680" fontSize={11} />
                <Tooltip contentStyle={tooltipStyle} />
                <Legend />
                {(w?.branches ?? []).map((b, i) => (
                  <Line
                    key={b.name}
                    type="monotone"
                    dataKey={b.name}
                    stroke={["#e8b04b", "#6fa8a0", "#c8553d"][i % 3]}
                    dot={false}
                    strokeWidth={2}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="panel">
          <h2>Contradiction indicators</h2>
          {(w?.contradictions ?? []).length === 0 && (
            <p className="note">No contradictions recorded.</p>
          )}
          <table>
            <thead><tr><th>t</th><th>Magnitude</th><th>Note</th></tr></thead>
            <tbody>
              {(w?.contradictions ?? []).map((c, i) => (
                <tr key={i}>
                  <td><code>{c.t}</code></td>
                  <td style={{ fontFamily: "ui-monospace, monospace" }}>{c.magnitude}</td>
                  <td>{c.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
