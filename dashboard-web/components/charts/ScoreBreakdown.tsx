"use client"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts"

export function ScoreBreakdown({ scores }: {
  scores: { trend: number; momentum: number; volume: number; risk: number; setup_quality: number }
}) {
  const data = [
    { name: "Trend",   value: +scores.trend.toFixed(1) },
    { name: "Momentum",value: +scores.momentum.toFixed(1) },
    { name: "Volume",  value: +scores.volume.toFixed(1) },
    { name: "Risk",    value: +scores.risk.toFixed(1) },
    { name: "Setup",   value: +scores.setup_quality.toFixed(1) },
  ]
  return (
    <ResponsiveContainer width="100%" height={140}>
      <BarChart data={data} layout="vertical" margin={{ left: 16, right: 8, top: 4, bottom: 4 }}>
        <XAxis type="number" domain={[0, 100]} tick={{ fill: "#666", fontSize: 10 }} />
        <YAxis type="category" dataKey="name" tick={{ fill: "#888", fontSize: 10 }} width={64} />
        <Tooltip contentStyle={{ background: "#0f0f0f", border: "1px solid #1f1f1f", fontSize: 11 }} />
        <Bar dataKey="value" fill="var(--cyan)" radius={[0, 2, 2, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
