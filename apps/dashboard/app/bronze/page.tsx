"use client";
import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ApiResult, apiGet } from "../../lib/api";
import type { MetricsReport } from "../../lib/types";
import { demoMetrics } from "../../lib/fixtures";
import DemoBadge from "../../components/DemoBadge";

const tooltipStyle = {
  backgroundColor: "#1e1712",
  border: "1px solid #3a2c1e",
  color: "#e8ddd0",
  fontSize: 12,
};

function ChartPanel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="panel">
      <h2>{title}</h2>
      <div style={{ height: 280 }}>{children}</div>
    </div>
  );
}

export default function BronzePage() {
  const [metrics, setMetrics] = useState<ApiResult<MetricsReport> | null>(null);

  useEffect(() => {
    apiGet<MetricsReport>("/v2/metrics", demoMetrics).then(setMetrics);
  }, []);

  const m = metrics?.data ?? null;

  return (
    <div>
      <div className="page-head">
        <h1>Bronze Reduction Lab</h1>
        {metrics?.demo && <DemoBadge reason={metrics.error} />}
        <p>
          Latency, resource, and quality numbers from <code>GET /v2/metrics</code>{" "}
          (or execution records). Anything synthetic is DEMO-badged.
        </p>
      </div>

      <div className="grid2">
        <ChartPanel title="Latency by config (ms)">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={m?.latency ?? []} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="#3a2c1e" strokeDasharray="3 3" />
              <XAxis dataKey="config" stroke="#a89680" fontSize={11} />
              <YAxis stroke="#a89680" fontSize={11} />
              <Tooltip contentStyle={tooltipStyle} />
              <Legend />
              <Bar dataKey="p50_ms" fill="#c98a3d" name="p50" />
              <Bar dataKey="p95_ms" fill="#e8b04b" name="p95" />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel title="Resources by config">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={m?.resources ?? []} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="#3a2c1e" strokeDasharray="3 3" />
              <XAxis dataKey="config" stroke="#a89680" fontSize={11} />
              <YAxis stroke="#a89680" fontSize={11} />
              <Tooltip contentStyle={tooltipStyle} />
              <Legend />
              <Bar dataKey="cpu_ms" fill="#6fa8a0" name="cpu ms" />
              <Bar dataKey="mem_mb" fill="#5b7a99" name="mem MB" />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <ChartPanel title="Quality comparison (score)">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={m?.quality ?? []} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="#3a2c1e" strokeDasharray="3 3" />
              <XAxis dataKey="config" stroke="#a89680" fontSize={11} />
              <YAxis stroke="#a89680" fontSize={11} domain={[0, 1]} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="score" fill="#e8b04b" name="quality score" />
            </BarChart>
          </ResponsiveContainer>
        </ChartPanel>

        <div className="panel">
          <h2>Optimization configs</h2>
          <table>
            <thead><tr><th>ID</th><th>Description</th><th>Params</th></tr></thead>
            <tbody>
              {(m?.configs ?? []).map((c) => (
                <tr key={c.id}>
                  <td><code>{c.id}</code></td>
                  <td>{c.description}</td>
                  <td><code style={{ fontSize: 11 }}>{JSON.stringify(c.params)}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
