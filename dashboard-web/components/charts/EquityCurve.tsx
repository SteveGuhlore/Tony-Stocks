"use client"
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from "recharts"

export function EquityCurve({ curve }: { curve: number[] }) {
  if (!curve.length) return <p style={{ color: "var(--text-secondary)", fontSize: 11 }}>No equity data</p>
  const data = curve.map((v, i) => ({ trade: i + 1, value: +(v * 100).toFixed(2) }))
  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <XAxis dataKey="trade" tick={{ fill: "#666", fontSize: 10 }} />
        <YAxis tick={{ fill: "#666", fontSize: 10 }} unit="%" />
        <Tooltip contentStyle={{ background: "#0f0f0f", border: "1px solid #1f1f1f", fontSize: 11 }}
          formatter={(v) => [typeof v === "number" ? `${v}%` : String(v), "Equity"]} />
        <ReferenceLine y={100} stroke="#1f1f1f" />
        <Line type="monotone" dataKey="value" stroke="var(--cyan)" dot={false} strokeWidth={1.5} />
      </LineChart>
    </ResponsiveContainer>
  )
}

