"use client"

import { toast } from "sonner"
import { useSystemHealth } from "@/lib/hooks"
import { api } from "@/lib/api"
import { ViewHeader, Kpis, Panel, Awaiting } from "./shared"
import { Button } from "@/components/kinetic/Button"
import type { ConfirmSpec } from "@/components/kinetic/ConfirmDialog"
import type { StreamState } from "@/lib/useEventStream"

/** Fire a control action and surface the outcome. The backend stays the real guard
 * (env fence + PIN); a failure (e.g. 403 in dev, or 409 precondition) is shown, never
 * silently swallowed, so the operator never thinks a no-op succeeded. */
async function runControl(label: string, fn: () => Promise<unknown>) {
  try {
    await fn()
    toast.success(`${label} requested`)
  } catch (e) {
    toast.error(`${label} failed`, { description: e instanceof Error ? e.message : String(e) })
  }
}

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

  return (
    <div>
      <ViewHeader title="System" sub="health & controls" />
      <Kpis
        items={[
          { label: "Watch", value: data?.watch_status ?? "—", tone: data?.watch_status === "running" ? "pos" : undefined },
          { label: "Heartbeat", value: data?.heartbeat_seconds != null ? `${data.heartbeat_seconds}s` : "—" },
          { label: "Cycle", value: data?.cycle ?? "—" },
          {
            label: "API budget",
            value:
              data?.api_budget_used != null && data?.api_budget_total != null
                ? `${data.api_budget_used}/${data.api_budget_total}`
                : "—",
          },
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
                requirePin: true,
                onConfirm: (pin) => runControl("Stop watch", () => api.control.stopWatch({ pin })),
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
                requirePin: true,
                onConfirm: (pin) => runControl("Pause paper", () => api.control.pausePaper({ pin })),
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
                onConfirm: (pin) => runControl("Flatten all", () => api.control.flattenAll({ pin })),
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
                requirePin: true,
                onConfirm: (pin) => runControl("Trigger scan", () => api.control.triggerScan({ pin })),
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
        <span>● {data?.data_source ?? "data source —"}</span>
        <span>{data?.last_scan_label ?? "scan —"}</span>
        <span className="text-warn">⚑ research only</span>
      </div>
    </div>
  )
}
