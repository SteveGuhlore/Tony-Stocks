"use client"

import { useEffect, useRef } from "react"
import type { ChartResponse } from "@/lib/types"

/**
 * lightweight-charts candles + plan lines. Honors status: unavailable/stale show
 * a labeled empty state — never a broken axis.
 */
export function SymbolChart({ data, loading }: { data: ChartResponse | undefined; loading: boolean }) {
  const hostRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const host = hostRef.current
    if (!host || !data || data.status === "unavailable" || data.bars.length === 0) return

    let destroyed = false
    let cleanup: (() => void) | null = null

    ;(async () => {
      try {
        const lib = await import("lightweight-charts")
        if (destroyed || !host) return
        host.innerHTML = ""
        const chart = lib.createChart(host, {
          width: host.clientWidth,
          height: 200,
          layout: { background: { color: "transparent" }, textColor: "#7e8a82", fontFamily: "Space Mono" },
          grid: { vertLines: { visible: false }, horzLines: { color: "rgba(255,255,255,.05)" } },
          rightPriceScale: { borderColor: "rgba(255,255,255,.08)" },
          timeScale: { borderColor: "rgba(255,255,255,.08)" },
          crosshair: { mode: 0 },
        })
        // v5 API: addSeries(CandlestickSeries, opts)
        const series = chart.addSeries(lib.CandlestickSeries, {
          upColor: "#46d39a",
          downColor: "#ff5d73",
          wickUpColor: "#46d39a",
          wickDownColor: "#ff5d73",
          borderVisible: false,
        })
        series.setData(
          data.bars.map((b) => ({
            time: (typeof b.t === "number" ? b.t : Math.floor(new Date(b.t).getTime() / 1000)) as never,
            open: b.o,
            high: b.h,
            low: b.l,
            close: b.c,
          })),
        )
        const { entry, stop, target } = data.plan
        const lines: { price: number; color: string; title: string }[] = []
        if (entry != null) lines.push({ price: entry, color: "#37e0ff", title: "entry" })
        if (stop != null) lines.push({ price: stop, color: "#ff5d73", title: "stop" })
        if (target != null) lines.push({ price: target, color: "#46d39a", title: "target" })
        for (const l of lines) {
          series.createPriceLine({ price: l.price, color: l.color, lineStyle: 2, lineWidth: 1, title: l.title })
        }
        chart.timeScale().fitContent()
        const onResize = () => chart.applyOptions({ width: host.clientWidth })
        window.addEventListener("resize", onResize)
        cleanup = () => {
          window.removeEventListener("resize", onResize)
          chart.remove()
        }
      } catch {
        /* fall through to empty state below */
      }
    })()

    return () => {
      destroyed = true
      cleanup?.()
    }
  }, [data])

  if (loading) {
    return <EmptyChart label="Loading chart…" />
  }
  if (!data || data.status === "unavailable" || data.bars.length === 0) {
    return <EmptyChart label="Chart unavailable — no stored bars for this symbol yet." />
  }
  return (
    <div>
      {data.status === "stale" && (
        <div className="text-warn" style={{ fontSize: 9, marginBottom: 6 }}>
          ⚠ stale bars — last stored {data.timeframe}
        </div>
      )}
      <div ref={hostRef} className="kt-spark" style={{ width: "100%", height: 200 }} aria-label={`${data.symbol} candlestick chart`} />
    </div>
  )
}

function EmptyChart({ label }: { label: string }) {
  return (
    <div
      className="grid place-items-center text-dim"
      style={{ height: 200, border: "1px dashed var(--line)", borderRadius: 10, fontSize: 11 }}
    >
      {label}
    </div>
  )
}
