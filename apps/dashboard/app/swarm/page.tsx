"use client";
import { useEffect, useState } from "react";
import { ApiResult, apiGet } from "../../lib/api";
import type { SwarmReport } from "../../lib/types";
import { demoSwarm } from "../../lib/fixtures";
import DemoBadge from "../../components/DemoBadge";

const CLUSTER_COLOR: Record<string, string> = {
  alpha: "#e8b04b",
  beta: "#6fa8a0",
  gamma: "#c8553d",
};

function BranchTree({ tree }: { tree: SwarmReport["provenance_tree"] }) {
  const childrenOf = (parent: string | null) =>
    tree.filter((n) => n.parent === parent);
  const render = (parent: string | null): React.ReactNode => (
    <ul>
      {childrenOf(parent).map((n) => (
        <li key={n.branch}>
          <strong style={{ color: "var(--gold)" }}>{n.branch}</strong>
          <span> · {n.station}</span>
          {render(n.branch)}
        </li>
      ))}
    </ul>
  );
  return <div className="tree">{render(null)}</div>;
}

export default function SwarmPage() {
  const [swarm, setSwarm] = useState<ApiResult<SwarmReport> | null>(null);

  useEffect(() => {
    apiGet<SwarmReport>("/v2/swarm/latest", demoSwarm).then(setSwarm);
  }, []);

  const s = swarm?.data ?? null;

  return (
    <div>
      <div className="page-head">
        <h1>Swarm &amp; Parallel Paths</h1>
        {swarm?.demo && <DemoBadge reason={swarm.error} />}
        <p>
          Candidate swarm from <code>GET /v2/swarm/latest</code> — candidate
          cards, consensus clusters, and the branch provenance tree.
        </p>
      </div>

      <div className="grid2">
        <div className="panel">
          <h2>Candidates ({(s?.candidates ?? []).length})</h2>
          {(s?.candidates ?? []).map((c) => (
            <div className="card" key={c.id}>
              <h3>
                <code>{c.id}</code>{" "}
                <span
                  className="pill"
                  style={{
                    borderColor: CLUSTER_COLOR[c.cluster] ?? "var(--text-dim)",
                    color: CLUSTER_COLOR[c.cluster] ?? "var(--text-dim)",
                  }}
                >
                  {c.cluster}
                </span>
              </h3>
              <p>{c.text}</p>
              <div className="bar-row">
                <span className="bar-label">score</span>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${Math.round(c.score * 100)}%` }} />
                </div>
                <span className="bar-val">{c.score.toFixed(2)}</span>
              </div>
              <p className="note" style={{ marginBottom: 0 }}>branch: <code>{c.branch}</code></p>
            </div>
          ))}
        </div>

        <div>
          <div className="panel">
            <h2>Consensus clusters</h2>
            {(s?.clusters ?? []).map((cl) => (
              <div className="card" key={cl.name}>
                <h3>
                  <span
                    className="pill"
                    style={{
                      borderColor: CLUSTER_COLOR[cl.name] ?? "var(--text-dim)",
                      color: CLUSTER_COLOR[cl.name] ?? "var(--text-dim)",
                    }}
                  >
                    {cl.name}
                  </span>{" "}
                  centroid {cl.centroid_score.toFixed(3)}
                </h3>
                <p className="note" style={{ margin: 0 }}>
                  members: {cl.members.map((m) => <code key={m}>{m} </code>)}
                </p>
              </div>
            ))}
          </div>
          <div className="panel">
            <h2>Branch provenance tree</h2>
            {s ? <BranchTree tree={s.provenance_tree} /> : <p className="note">Loading…</p>}
          </div>
        </div>
      </div>
    </div>
  );
}
