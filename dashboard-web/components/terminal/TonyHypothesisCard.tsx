import type { CandidateSnapshot } from "@/lib/types"
import { TickerSymbol } from "./TickerSymbol"

export function TonyHypothesisCard({ snap }: { snap: CandidateSnapshot }) {
  if (!snap.tony_hypothesis && !snap.tony_setup_read) return null
  return (
    <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 4, padding: "10px 14px", marginBottom: 8 }}>
      <div style={{ fontSize: 10, color: "var(--cyan)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6, fontFamily: "JetBrains Mono, monospace" }}>
        {["TONY", snap.tony_priority_label, snap.tony_recommended_action].filter(Boolean).join(" · ")}
      </div>
      <div style={{ marginBottom: 6 }}>
        <TickerSymbol symbol={snap.symbol} />
      </div>
      {snap.tony_setup_read && <p style={{ fontSize: 11, color: "var(--text-secondary)", margin: "0 0 6px" }}>{snap.tony_setup_read}</p>}
      {snap.tony_hypothesis && <p style={{ fontSize: 11, color: "var(--text-primary)", margin: 0, fontStyle: "italic" }}>{snap.tony_hypothesis}</p>}
    </div>
  )
}
