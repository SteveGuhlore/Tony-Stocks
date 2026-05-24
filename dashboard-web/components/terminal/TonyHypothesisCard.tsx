import type { CandidateSnapshot } from "@/lib/types"
import { TickerSymbol } from "./TickerSymbol"

const PRIORITY_COLOR: Record<string, string> = {
  high: "var(--red)", medium: "var(--amber)", low: "var(--text-secondary)"
}

export function TonyHypothesisCard({ snap }: { snap: CandidateSnapshot }) {
  if (!snap.tony_hypothesis && !snap.tony_setup_read) return null
  const pc = PRIORITY_COLOR[snap.tony_priority_label?.toLowerCase() ?? "low"] ?? "var(--text-secondary)"
  return (
    <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderLeft: "3px solid var(--cyan)", borderRadius: 4, padding: "10px 14px", marginBottom: 8 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        <span style={{ fontSize: 10, color: pc, fontWeight: 700, textTransform: "uppercase" }}>{snap.tony_priority_label ?? "—"}</span>
        <TickerSymbol symbol={snap.symbol} />
        {snap.tony_recommended_action && (
          <span style={{ fontSize: 11, color: "var(--cyan)" }}>{snap.tony_recommended_action}</span>
        )}
      </div>
      {snap.tony_setup_read && <p style={{ fontSize: 11, color: "var(--text-secondary)", margin: "0 0 6px" }}>{snap.tony_setup_read}</p>}
      {snap.tony_hypothesis && <p style={{ fontSize: 11, color: "var(--text-primary)", margin: 0, fontStyle: "italic" }}>{snap.tony_hypothesis}</p>}
    </div>
  )
}
