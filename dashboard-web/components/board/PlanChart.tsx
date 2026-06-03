"use client"
import { useRef, useState } from "react"
import { priceBounds, scaleY, priceTicks, type Bar } from "@/lib/chart"

const VBW = 600
const VBH = 180
const AXW = 46

export function PlanChart({
  bars, stop, entry, target,
}: {
  bars: Bar[]
  stop: number | null
  entry: number | null
  target: number | null
}) {
  const [mode, setMode] = useState<"candles" | "line">("candles")
  const [hover, setHover] = useState<number | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)

  const bounds = priceBounds(bars, [stop, entry, target])
  if (!bounds || bars.length === 0) {
    return <p style={{ color: "var(--text-tertiary)", fontSize: 11, padding: "8px 0" }}>No price history available.</p>
  }
  const { min, max } = bounds
  const n = bars.length
  const slot = VBW / n
  const cw = Math.max(1.5, Math.min(slot * 0.6, 10))
  const y = (v: number) => scaleY(v, min, max, VBH)
  const maxVol = Math.max(...bars.map((b) => b.volume), 1)

  const onMove = (e: React.MouseEvent) => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    const i = Math.floor(((e.clientX - rect.left) / rect.width) * n)
    setHover(Math.max(0, Math.min(n - 1, i)))
  }

  const planLine = (v: number | null, color: string, label: string) =>
    v == null ? null : (
      <line key={label} x1={0} x2={VBW} y1={y(v)} y2={y(v)} stroke={color} strokeWidth={1} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" opacity={0.55} />
    )

  const hb = hover != null ? bars[hover] : null
  const hx = hover != null ? hover * slot + slot / 2 : 0

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
        <span style={{ fontSize: 9, letterSpacing: "0.08em", color: "var(--text-tertiary)" }}>PRICE · {n}D · plan lines drawn</span>
        <button
          onClick={() => setMode((m) => (m === "candles" ? "line" : "candles"))}
          style={{ fontSize: 10, color: "var(--text-secondary)", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 5, padding: "2px 8px", cursor: "pointer" }}
        >{mode === "candles" ? "→ line" : "→ candles"}</button>
      </div>

      <div style={{ display: "flex" }}>
        <div style={{ flex: 1, position: "relative" }}>
          <svg
            ref={svgRef}
            viewBox={`0 0 ${VBW} ${VBH}`}
            preserveAspectRatio="none"
            width="100%" height={VBH}
            onMouseMove={onMove}
            onMouseLeave={() => setHover(null)}
            style={{ display: "block", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: "6px 0 0 6px" }}
          >
            {planLine(target, "var(--green)", "tgt")}
            {planLine(entry, "var(--text-secondary)", "entry")}
            {planLine(stop, "var(--red)", "stop")}

            {mode === "candles"
              ? bars.map((b, i) => {
                  const x = i * slot + slot / 2
                  const up = b.close >= b.open
                  const color = up ? "var(--green)" : "var(--red)"
                  return (
                    <g key={i} stroke={color} fill={color}>
                      <line x1={x} x2={x} y1={y(b.high)} y2={y(b.low)} strokeWidth={1} vectorEffect="non-scaling-stroke" />
                      <rect x={x - cw / 2} y={Math.min(y(b.open), y(b.close))} width={cw} height={Math.max(1, Math.abs(y(b.open) - y(b.close)))} />
                    </g>
                  )
                })
              : (
                <polyline
                  points={bars.map((b, i) => `${i * slot + slot / 2},${y(b.close)}`).join(" ")}
                  fill="none" stroke="var(--accent)" strokeWidth={1.5} vectorEffect="non-scaling-stroke"
                />
              )}

            {hb && (
              <g>
                <line x1={hx} x2={hx} y1={0} y2={VBH} stroke="var(--accent)" strokeWidth={1} strokeDasharray="2 2" vectorEffect="non-scaling-stroke" opacity={0.6} />
                <circle cx={hx} cy={y(hb.close)} r={3} fill="var(--accent)" />
              </g>
            )}
          </svg>

          {hb && (
            <div className="mono" style={{
              position: "absolute", top: 6, left: hx / VBW > 0.6 ? 6 : undefined, right: hx / VBW > 0.6 ? undefined : 6,
              background: "var(--bg-surface)", border: "1px solid var(--border-focus)", borderRadius: 5, padding: "4px 7px",
              fontSize: 9, color: "var(--text-secondary)", lineHeight: 1.5, pointerEvents: "none",
            }}>
              {hb.date.slice(5)}<br />O {hb.open.toFixed(2)} H {hb.high.toFixed(2)}<br />L {hb.low.toFixed(2)} <b style={{ color: "var(--text-primary)" }}>C {hb.close.toFixed(2)}</b>
            </div>
          )}
        </div>

        {/* price axis */}
        <div className="mono" style={{ width: AXW, height: VBH, border: "1px solid var(--border)", borderLeft: "none", borderRadius: "0 6px 6px 0", display: "flex", flexDirection: "column", justifyContent: "space-between", padding: "4px 5px", fontSize: 8.5, color: "var(--text-tertiary)" }}>
          {priceTicks(min, max, 4).slice().reverse().map((t, i) => <span key={i}>{t.toFixed(2)}</span>)}
        </div>
      </div>

      {/* volume strip */}
      <div style={{ display: "flex", alignItems: "flex-end", gap: 1, height: 22, marginTop: 3, paddingRight: AXW }}>
        {bars.map((b, i) => (
          <div key={i} title={`${b.date} vol ${b.volume}`} style={{
            flex: 1, height: `${(b.volume / maxVol) * 100}%`,
            background: b.close >= b.open ? "rgba(54,211,153,0.4)" : "rgba(255,99,99,0.4)",
          }} />
        ))}
      </div>

      {/* date axis */}
      <div className="mono" style={{ display: "flex", justifyContent: "space-between", paddingRight: AXW, marginTop: 5, fontSize: 8.5, color: "var(--text-tertiary)" }}>
        {[0, Math.floor(n / 2), n - 1].map((i) => <span key={i}>{bars[i]?.date.slice(5)}</span>)}
      </div>
    </div>
  )
}
