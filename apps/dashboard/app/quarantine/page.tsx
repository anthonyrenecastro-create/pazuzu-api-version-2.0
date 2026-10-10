"use client";
import { useEffect, useState } from "react";
import { ApiResult, apiGet, apiPost, QuarantineRecord } from "../../lib/api";
import { demoQuarantine } from "../../lib/fixtures";
import StatusPill from "../../components/StatusPill";
import DemoBadge from "../../components/DemoBadge";

const ACTIONS = ["release", "destroy", "keep_quarantined"] as const;

export default function QuarantinePage() {
  const [list, setList] = useState<ApiResult<QuarantineRecord[]> | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [action, setAction] = useState<(typeof ACTIONS)[number]>("release");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => {
    apiGet<QuarantineRecord[]>("/v2/quarantine", demoQuarantine).then(setList);
  };
  useEffect(load, []);

  const selected = (list?.data ?? []).find((r) => r.id === selectedId) ?? null;

  const submitReview = async () => {
    if (!selected || !reason.trim() || busy) return;
    setBusy(true);
    setMsg(null);
    const body = { action, reason };
    const res = await apiPost<QuarantineRecord>(
      `/v2/quarantine/${selected.id}/review`,
      body,
      () => ({
        ...selected,
        status: (action === "release" ? "released" : action === "destroy" ? "destroyed" : "under_review") as QuarantineRecord["status"],
        history: [...selected.history, { at: new Date().toISOString(), event: `DEMO review: ${action} — ${reason}` }],
      }),
    );
    if (res.demo) {
      setList((prev) =>
        prev ? { ...prev, data: prev.data.map((r) => (r.id === selected.id ? res.data : r)) } : prev,
      );
      setMsg(`DEMO: review simulated locally — ${action}. Backend unreachable.`);
    } else {
      setMsg(`Review submitted: ${action}.`);
      load();
    }
    setReason("");
    setBusy(false);
  };

  return (
    <div>
      <div className="page-head">
        <h1>Quarantine Chamber</h1>
        {list?.demo && <DemoBadge reason={list.error} />}
        <p>
          Held patterns from <code>GET /v2/quarantine</code>. Reviews go to{" "}
          <code>POST /v2/quarantine/{"{id}"}/review</code>.
        </p>
      </div>

      <div className="demo-panel" style={{ borderStyle: "solid" }}>
        <strong>Admin note.</strong> Quarantine reviews are privileged: the
        backend requires an admin-role credential for{" "}
        <code>POST /v2/quarantine/{"{id}"}/review</code>. Actions taken while the
        backend is unreachable are simulated against the local fixture and
        change nothing server-side.
      </div>

      <div className="grid2">
        <div className="panel">
          <h2>Held records ({(list?.data ?? []).length})</h2>
          <table>
            <thead>
              <tr><th>ID</th><th>Reason</th><th>Risk</th><th>Status</th><th>Station</th></tr>
            </thead>
            <tbody>
              {(list?.data ?? []).map((r) => (
                <tr
                  key={r.id}
                  onClick={() => setSelectedId(r.id)}
                  style={{ cursor: "pointer", background: r.id === selectedId ? "rgba(201,138,61,0.1)" : undefined }}
                >
                  <td><code>{r.id}</code></td>
                  <td><code style={{ fontSize: 11 }}>{r.reason_code}</code></td>
                  <td><StatusPill value={r.risk_class} /></td>
                  <td><StatusPill value={r.status} /></td>
                  <td><code>{r.station_id}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="panel">
          <h2>Review</h2>
          {!selected && <p className="note">Select a record to review it.</p>}
          {selected && (
            <>
              <dl className="kv">
                <dt>record</dt><dd>{selected.id}</dd>
                <dt>request</dt><dd>{selected.request_id}</dd>
                <dt>risk</dt><dd><StatusPill value={selected.risk_class} /></dd>
                <dt>status</dt><dd><StatusPill value={selected.status} /></dd>
                <dt>created</dt><dd>{selected.created_at}</dd>
              </dl>
              <h2>History</h2>
              <ul>
                {selected.history.map((h, i) => (
                  <li key={i} style={{ fontSize: 12, color: "var(--text-dim)" }}>
                    <code>{JSON.stringify(h)}</code>
                  </li>
                ))}
              </ul>
              <label>Action</label>
              <select value={action} onChange={(e) => setAction(e.target.value as typeof action)}>
                {ACTIONS.map((a) => (
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
              <label>Reason (required)</label>
              <input
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="justification for the review decision"
              />
              <div className="toolbar" style={{ marginTop: 10, marginBottom: 0 }}>
                <button className="btn btn-primary" onClick={submitReview} disabled={busy || !reason.trim()}>
                  {busy ? "Submitting…" : "Submit review"}
                </button>
              </div>
              {msg && <p className="note">{msg}</p>}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
