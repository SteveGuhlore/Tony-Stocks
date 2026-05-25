"use client"

function formatDuration(ms: number): string {
  const totalMinutes = Math.floor(ms / 60000)
  const totalHours = Math.floor(totalMinutes / 60)
  const days = Math.floor(totalHours / 24)
  if (days >= 1) return `${days}d ${totalHours % 24}h`
  if (totalHours >= 1) return `${totalHours}h ${totalMinutes % 60}m`
  return `${totalMinutes}m`
}

interface Props {
  since: string | null
  label: "in trade" | "watching"
}

export function TimeInTrade({ since, label }: Props) {
  if (!since) return <span style={{ color: "var(--text-secondary)", fontSize: 11 }}>—</span>
  const ms = Date.now() - new Date(since).getTime()
  if (ms < 0) return null
  const dur = formatDuration(ms)
  return (
    <span style={{ color: "var(--text-secondary)", fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}>
      {label === "watching" ? `watching ${dur}` : `${dur} in trade`}
    </span>
  )
}
