import type { TonyEvent } from "@/lib/types"

const SEV_COLOR: Record<string, string> = {
  error: "var(--red)", warning: "var(--amber)", info: "var(--blue)", high: "var(--red)"
}

function relativeTime(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

export function ActivityFeed({ events }: { events: TonyEvent[] }) {
  if (!events.length) return <p style={{ color: "var(--text-secondary)", fontSize: 11 }}>No recent events</p>
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {events.map(e => (
        <div key={e.id} style={{
          display: "flex", gap: 10, padding: "6px 10px",
          background: "var(--bg-elevated)", borderRadius: 3,
          borderLeft: `2px solid ${SEV_COLOR[e.severity] ?? "var(--border)"}`,
        }}>
          <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "var(--text-secondary)", whiteSpace: "nowrap", paddingTop: 1 }}>
            {relativeTime(e.created_at)}
          </span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {e.symbol && <span style={{ color: "var(--cyan)", marginRight: 6 }}>{e.symbol}</span>}
              {e.title}
            </div>
            <div style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 2 }}>{e.message}</div>
          </div>
        </div>
      ))}
    </div>
  )
}
