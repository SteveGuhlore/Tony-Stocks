"use client"

interface Props {
  entry: number
  stop: number
  target: number
  currentPrice: number | null
  triggered: boolean
  dayHigh?: number
  dayLow?: number
}

function clamp(v: number, lo: number, hi: number) {
  return Math.min(hi, Math.max(lo, v))
}

function toPct(value: number, stop: number, range: number) {
  return clamp((value - stop) / range * 100, 0, 100)
}

export function RiskGauge({ entry, stop, target, currentPrice, triggered, dayHigh, dayLow }: Props) {
  const range = target - stop
  if (range <= 0) return null

  const entryPct = toPct(entry, stop, range)
  const pricePct = currentPrice !== null ? toPct(currentPrice, stop, range) : null
  const highPct  = dayHigh !== undefined && dayHigh > stop && dayHigh < target
    ? toPct(dayHigh, stop, range) : null
  const lowPct   = dayLow  !== undefined && dayLow  > stop && dayLow  < target
    ? toPct(dayLow,  stop, range) : null

  const aboveEntry    = currentPrice !== null && currentPrice > entry
  const atOrBelowStop = currentPrice !== null && currentPrice <= stop

  const markerColor = atOrBelowStop ? "var(--red)"
    : aboveEntry ? "var(--green)"
    : "var(--amber)"

  return (
    <div style={{ userSelect: "none", marginBottom: 8 }}>
      {/* bar */}
      <div style={{
        position: "relative",
        height: 8,
        borderRadius: 4,
        background: "rgba(255,255,255,0.04)",
        overflow: "visible",
        marginBottom: 22,
      }}>
        {/* risk zone fill: stop → entry */}
        {triggered && (
          <div style={{
            position: "absolute", left: 0, width: `${entryPct}%`, height: "100%",
            borderRadius: "4px 0 0 4px",
            background: "rgba(255,61,61,0.18)",
          }} />
        )}

        {/* profit zone fill: entry → currentPrice when above entry */}
        {triggered && pricePct !== null && pricePct > entryPct && (
          <div style={{
            position: "absolute",
            left: `${entryPct}%`,
            width: `${pricePct - entryPct}%`,
            height: "100%",
            background: "rgba(0,230,118,0.22)",
          }} />
        )}

        {/* day low tick */}
        {lowPct !== null && (
          <div style={{
            position: "absolute", left: `${lowPct}%`,
            top: -3, bottom: -3, width: 1,
            background: "rgba(255,171,0,0.45)",
            transform: "translateX(-50%)",
          }} />
        )}

        {/* day high tick */}
        {highPct !== null && (
          <div style={{
            position: "absolute", left: `${highPct}%`,
            top: -3, bottom: -3, width: 1,
            background: "rgba(255,171,0,0.45)",
            transform: "translateX(-50%)",
          }} />
        )}

        {/* entry line */}
        <div style={{
          position: "absolute",
          left: `${entryPct}%`,
          top: -4, bottom: -4, width: 2,
          background: triggered ? "var(--cyan)" : "rgba(0,229,255,0.35)",
          borderRadius: 1,
          transform: "translateX(-50%)",
        }} />

        {/* current price marker — glows, transitions as price updates */}
        {pricePct !== null && (
          <div style={{
            position: "absolute",
            left: `${pricePct}%`,
            top: "50%",
            transform: "translate(-50%, -50%)",
            width: 14, height: 14,
            borderRadius: "50%",
            background: markerColor,
            boxShadow: `0 0 8px 2px ${markerColor}55`,
            border: "2px solid var(--bg-base)",
            zIndex: 2,
            transition: "left 0.6s ease",
          }} />
        )}
      </div>

      {/* labels */}
      <div style={{
        position: "relative", height: 12,
        fontSize: 9, fontFamily: "JetBrains Mono, monospace",
        color: "var(--text-secondary)",
      }}>
        <span style={{ position: "absolute", left: 0, whiteSpace: "nowrap" }}>
          STOP ${stop.toFixed(2)}
        </span>
        <span style={{
          position: "absolute",
          left: `${entryPct}%`,
          transform: "translateX(-50%)",
          color: "var(--cyan)",
          whiteSpace: "nowrap",
        }}>
          ${entry.toFixed(2)}
        </span>
        <span style={{ position: "absolute", right: 0, whiteSpace: "nowrap" }}>
          TARGET ${target.toFixed(2)}
        </span>
      </div>
    </div>
  )
}
