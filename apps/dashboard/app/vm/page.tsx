"use client";
import { useEffect, useState } from "react";
import {
  ApiResult,
  apiGet,
  apiPost,
  FormalismEntry,
} from "../../lib/api";
import type { VmCompileResult, VmSimulateResult } from "../../lib/types";
import { demoCompile, demoFormalisms, demoSimulate } from "../../lib/fixtures";
import StatusPill from "../../components/StatusPill";
import DemoBadge from "../../components/DemoBadge";

export default function VmPage() {
  const [source, setSource] = useState("push 1\npush 2\nadd\nhalt\n");
  const [compileRes, setCompileRes] = useState<ApiResult<VmCompileResult> | null>(null);
  const [simRes, setSimRes] = useState<ApiResult<VmSimulateResult> | null>(null);
  const [formalisms, setFormalisms] = useState<ApiResult<FormalismEntry[]> | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    apiGet<FormalismEntry[]>("/v2/formalisms", demoFormalisms).then(setFormalisms);
  }, []);

  const compile = async () => {
    if (busy) return;
    setBusy(true);
    setSimRes(null);
    const res = await apiPost<VmCompileResult>("/v2/vm/compile", { source }, () => demoCompile(source));
    setCompileRes(res);
    setBusy(false);
  };

  const simulate = async () => {
    if (busy) return;
    setBusy(true);
    const res = await apiPost<VmSimulateResult>(
      "/v2/vm/simulate",
      { program: compileRes?.data.ast ?? { source } },
      demoSimulate,
    );
    setSimRes(res);
    setBusy(false);
  };

  return (
    <div>
      <div className="page-head">
        <h1>VM Lab</h1>
        {(compileRes?.demo || simRes?.demo || formalisms?.demo) && (
          <DemoBadge reason={compileRes?.error ?? simRes?.error ?? formalisms?.error} />
        )}
        <p>
          Compile source with <code>POST /v2/vm/compile</code>, simulate with{" "}
          <code>POST /v2/vm/simulate</code>. Formalism registry from{" "}
          <code>GET /v2/formalisms</code>.
        </p>
      </div>

      <div className="grid2">
        <div className="panel">
          <h2>Source editor</h2>
          <textarea
            value={source}
            onChange={(e) => setSource(e.target.value)}
            style={{ minHeight: 160 }}
            spellCheck={false}
          />
          <div className="toolbar" style={{ marginTop: 10, marginBottom: 0 }}>
            <button className="btn btn-primary" onClick={compile} disabled={busy}>
              {busy ? "Working…" : "Compile"}
            </button>
            <button className="btn" onClick={simulate} disabled={busy || !compileRes}>
              Simulate
            </button>
          </div>
        </div>

        <div className="panel">
          <h2>AST &amp; errors {compileRes?.demo && <DemoBadge />}</h2>
          {!compileRes && <p className="note">Compile the source to see the AST.</p>}
          {compileRes && (
            <>
              <pre className="json">{JSON.stringify(compileRes.data.ast, null, 2)}</pre>
              <h2 style={{ marginTop: 12 }}>Errors ({compileRes.data.errors.length})</h2>
              {compileRes.data.errors.length === 0 ? (
                <p className="note">No errors.</p>
              ) : (
                <ul>
                  {compileRes.data.errors.map((e, i) => (
                    <li key={i}>line {e.line}: {e.message}</li>
                  ))}
                </ul>
              )}
              <h2 style={{ marginTop: 12 }}>Symbols</h2>
              <p>{compileRes.data.symbols.map((s) => <code key={s}>{s} </code>)}</p>
            </>
          )}
        </div>
      </div>

      {simRes && (
        <div className="grid2">
          <div className="panel">
            <h2>Simulation events {simRes.demo && <DemoBadge />}</h2>
            <table>
              <thead><tr><th>Step</th><th>Kind</th><th>Detail</th></tr></thead>
              <tbody>
                {simRes.data.events.map((e, i) => (
                  <tr key={i}>
                    <td><code>{e.step}</code></td>
                    <td><code>{e.kind}</code></td>
                    <td>{e.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="panel">
            <h2>Invariant checks</h2>
            <table>
              <thead><tr><th>Invariant</th><th>Result</th><th>Detail</th></tr></thead>
              <tbody>
                {simRes.data.invariant_checks.map((c, i) => (
                  <tr key={i}>
                    <td><code>{c.name}</code></td>
                    <td><StatusPill value={c.passed ? "approved" : "rejected"} /></td>
                    <td>{c.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="panel">
        <h2>Formalism registry {formalisms?.demo && <DemoBadge />}</h2>
        <table>
          <thead>
            <tr><th>ID</th><th>Equation</th><th>Interpretation</th><th>Status</th><th>Impl ref</th></tr>
          </thead>
          <tbody>
            {(formalisms?.data ?? []).map((f) => (
              <tr key={f.id}>
                <td><code>{f.id}</code></td>
                <td style={{ fontFamily: "ui-monospace, monospace", fontSize: 12 }}>{f.source_equation}</td>
                <td>{f.computational_interpretation}</td>
                <td><StatusPill value={f.verification_status} /></td>
                <td><code style={{ fontSize: 11 }}>{f.implementation_ref ?? "—"}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
