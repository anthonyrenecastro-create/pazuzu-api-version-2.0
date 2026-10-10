"use client";

/** Visible marker for any data that came from a local fixture, not the backend. */
export default function DemoBadge({ reason }: { reason?: string }) {
  const title = reason
    ? `Demonstration data — ${reason}. Not live backend data.`
    : "Demonstration data — backend unreachable. Not live backend data.";
  return (
    <span className="demo-badge" title={title}>
      DEMO
    </span>
  );
}
