"use client"

import { useSystemHealth } from "@/lib/hooks"
import { ViewHeader, Kpis, Panel, Awaiting } from "./shared"
import { Button } from "@/components/kinetic/Button"
import type { ConfirmSpec } from "@/components/kinetic/ConfirmDialog"
import type { StreamState } from "@/lib/useEventStream"

const SEV_COLOR: Record<string, string> = {
  info: "var(--pos)",
  ok: "var(--pos)",
  warn: "var(--warn)",
  warning: "var(--warn)",
  error: "var(--neg)",
  critical: "var(--neg)",
}

export function SystemView({ onConfirm, streamState }: { onConfirm: (s: ConfirmSpec) => void; streamState: StreamState }) {
  const { data, isLoading } = useSystemHealth()
  const events = data?.events ?? []
  const w = data?.watch
  const hb = w?.last_heartbeat_at
  const hbSecs = hb ? Math.max(0, Math.round((Date.now() - Date.parse(hb)) / 1000)) : null

  return (
    <div>
      <ViewHeader title="System" sub="health & controls" />
      <Kpis
        items={[
          { label: "Watch", value: w?.status ?? "—", tone: w?.status === "running" ? "pos" : undefined },
          { label: "Heartbeat", value: hbSecs != null ? `${hbSecs}s ago` : "—", tone: hbSecs != null && hbSecs < 600 ? "pos" : undefined },
          { label: "Cycle", value: w?.cycles_completed ?? "—" },
          { label: "API calls", value: w?.api_requests ?? "—" },
        ]}
      />
      <Panel title="Stream">
        <div className="text-mut" style={{ fontSize: 12 }}>
          SSE: <b className="text-ink">{streamState}</b> · polling is source of truth (8s)
        </div>
      </Panel>
      <Panel title="Controls">
        <div className="flex gap-2 flex-wrap">
          <Button
            onClick={() =>
              onConfirm({
                title: "Stop the watch loop?",
                body: "Writes data/STOP_WATCH_MODE on the VM — the scanner halts until restarted. No-op in dev fence.",
                confirmLabel: "Stop watch",
                onConfirm: () => {},
              })
            }
          >
            🛑 Stop watch loop
          </Button>
          <Button
            onClick={() =>
              onConfirm({
                title: "Pause paper trading?",
                body: "Writes data/STOP_PAPER_TRADING — no new entries until resumed. No-op in dev fence.",
                confirmLabel: "Pause paper",
                onConfirm: () => {},
              })
            }
          >
            ⏸ Pause paper trading
          </Button>
          <Button
            variant="danger"
            onClick={() =>
              onConfirm({
                title: "Flatten all positions?",
                body: "Closes every open paper position. PIN required. No-op in dev fence.",
                confirmLabel: "Flatten all",
                danger: true,
                requirePin: true,
                onConfirm: () => {},
              })
            }
          >
            💥 Flatten all positions
          </Button>
          <Button
            onClick={() =>
              onConfirm({
                title: "Trigger a manual scan?",
                body: "Kicks a manual scan cycle (409s if one is already running). No-op in dev fence.",
                confirmLabel: "Trigger scan",
                onConfirm: () => {},
              })
            }
          >
            ↻ Trigger scan now
          </Button>
        </div>
      </Panel>
      <Panel title="Recent events">
        {isLoading ? (
          <Awaiting what="events" />
        ) : events.length === 0 ? (
          <div className="text-dim" style={{ fontSize: 11 }}>
            No recent events.
          </div>
        ) : (
          <div style={{ lineHeight: 1.9, fontSize: 12 }}>
            {events.slice(0, 12).map((e, i) => (
              <div key={i}>
                <span style={{ color: SEV_COLOR[e.severity?.toLowerCase()] ?? "var(--mut)" }}>●</span>{" "}
                <span className="text-mut">{e.ts}</span> {e.message}
              </div>
            ))}
          </div>
        )}
      </Panel>
      <div className="flex gap-3 text-dim" style={{ fontSize: 10, marginTop: 6, flexWrap: "wrap" }}>
        <span>● {data?.last_scan_run?.provider ?? "data source —"}</span>
        <span>
          {data?.last_scan_run
            ? `scan #${data.last_scan_run.id} · ${data.last_scan_run.universe_count ?? "—"} symbols`
            : "scan —"}
        </span>
        <span>
          open {data?.open_snapshots ?? "—"} · triggered {data?.triggered_snapshots ?? "—"}
        </span>
        {data?.unacknowledged_warnings ? (
          <span className="text-warn">⚑ {data.unacknowledged_warnings} warnings</span>
        ) : null}
        <span className="text-warn">⚑ research only</span>
      </div>
    </div>
  )
}
