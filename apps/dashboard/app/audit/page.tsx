"use client";
import { useEffect, useState } from "react";
import { ApiResult, apiGet } from "../../lib/api";
import type { AuditResponse } from "../../lib/types";
import { demoAudit } from "../../lib/fixtures";
import StatusPill from "../../components/StatusPill";
import DemoBadge from "../../components/DemoBadge";

export default function AuditPage() {
  const [audit, setAudit] = useState<ApiResult<AuditResponse> | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    apiGet<AuditResponse>("/v2/audit", demoAudit).then(setAudit);
  }, []);

  const records = (audit?.data.records ?? []).filter(
    (r) =>
      !filter ||
      r.id.toLowerCase().includes(filter.toLowerCase()) ||
      r.title.toLowerCase().includes(filter.toLowerCase()) ||
      r.subsystem.toLowerCase().includes(filter.toLowerCase()) ||
      r.status.toLowerCase().includes(filter.toLowerCase()),
  );
  const gap = audit?.data.gap ?? null;
  const enhancements = audit?.data.enhancements ?? null;

  return (
    <div>
      <div className="page-head">
        <h1>Audit &amp; Enhancement Observatory</h1>
        {audit?.demo && <DemoBadge reason={audit.error} />}
        <p>
          Audit records from <code>GET /v2/audit</code>. Anything the backend
          did not supply is shown as <em>not supplied</em> — never invented.
        </p>
      </div>

      <div className="toolbar">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by id, subsystem, status…"
          style={{ maxWidth: 320 }}
        />
        <span className="note" style={{ margin: 0 }}>
          Showing {records.length} of {(audit?.data.records ?? []).length} records
        </span>
      </div>

      <div className="panel">
        <h2>Records S001–S078</h2>
        <table>
          <thead>
            <tr><th>ID</th><th>Title</th><th>Subsystem</th><th>Severity</th><th>Status</th></tr>
          </thead>
          <tbody>
            {records.map((r) => (
              <tr key={r.id} title={r.description}>
                <td><code>{r.id}</code></td>
                <td>{r.title}</td>
                <td><code style={{ fontSize: 11 }}>{r.subsystem}</code></td>
                <td><StatusPill value={r.severity} /></td>
                <td><StatusPill value={r.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid2">
        <div className="panel">
          <h2>GAP · records #{gap ? `${gap.from}–${gap.to}` : "79–144"}</h2>
          {gap ? (
            <p className="note">{gap.note}</p>
          ) : (
            <p className="note">Backend did not report a gap range.</p>
          )}
          {audit && !audit.demo && !gap && (
            <p className="note">No gap reported by the backend.</p>
          )}
          {gap && (
            <table>
              <thead><tr><th>Record</th><th>Data</th></tr></thead>
              <tbody>
                <tr>
                  <td><code>S079–S144</code></td>
                  <td><span className="pill pill-muted">not supplied</span></td>
                </tr>
              </tbody>
            </table>
          )}
        </div>

        <div className="panel">
          <h2>Enhancements</h2>
          {enhancements ? (
            <p className="note">{enhancements.note}</p>
          ) : (
            <p>
              <span className="pill pill-muted">not supplied</span>
            </p>
          )}
          <p className="note">
            The enhancement registry was not supplied by the backend, so no
            enhancements are listed. This panel will populate once{" "}
            <code>/v2/audit</code> includes enhancement data.
          </p>
        </div>
      </div>
    </div>
  );
}
