"use client";
import { useEffect, useState } from "react";
import { ApiResult, apiGet } from "../../lib/api";
import type { WardReport } from "../../lib/types";
import { demoWard } from "../../lib/fixtures";
import StatusPill from "../../components/StatusPill";
import DemoBadge from "../../components/DemoBadge";

export default function WardPage() {
  const [ward, setWard] = useState<ApiResult<WardReport> | null>(null);

  useEffect(() => {
    apiGet<WardReport>("/v2/ward/latest", demoWard).then(setWard);
  }, []);

  const w = ward?.data ?? null;

  return (
    <div>
      <div className="page-head">
        <h1>Dual Ward Chamber</h1>
        {ward?.demo && <DemoBadge reason={ward.error} />}
        <p>
          Keeper/Watcher verdict on the current candidate —{" "}
          <code>GET /v2/ward/latest</code>. Four scoring axes, final decision,
          and the full revision history.
        </p>
      </div>

      <div className="grid2">
        <div className="panel">
          <h2>Candidate text</h2>
          <p style={{ whiteSpace: "pre-wrap" }}>{w?.candidate_text ?? "—"}</p>
          <h2 style={{ marginTop: 16 }}>Decision</h2>
          {w ? (
            <p>
              <StatusPill value={w.decision} />{" "}
              <span style={{ color: "var(--text-dim)" }}>{w.decision_detail}</span>
            </p>
          ) : (
            <p className="note">Loading…</p>
          )}
        </div>

        <div className="panel">
          <h2>Four-axis scores</h2>
          {(w?.axes ?? []).map((a) => (
            <div key={a.name}>
              <div className="bar-row">
                <span className="bar-label">{a.name}</span>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${Math.round(a.score * 100)}%` }} />
                </div>
                <span className="bar-val">{a.score.toFixed(2)}</span>
              </div>
              <p className="note" style={{ margin: "2px 0 8px 120px" }}>{a.rationale}</p>
            </div>
          ))}
          {(!w || w.axes.length === 0) && <p className="note">No axis scores.</p>}
        </div>
      </div>

      <div className="panel">
        <h2>Revision history</h2>
        <table>
          <thead><tr><th>At</th><th>Decision</th><th>Note</th></tr></thead>
          <tbody>
            {(w?.revisions ?? []).map((r, i) => (
              <tr key={i}>
                <td style={{ fontFamily: "ui-monospace, monospace", fontSize: 12 }}>{r.at}</td>
                <td><StatusPill value={r.decision} /></td>
                <td>{r.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(w?.revisions ?? []).length === 0 && <p className="note">No revisions recorded.</p>}
      </div>
    </div>
  );
}
