"use client"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { KPIBar } from "@/components/terminal/KPIBar"

function Field({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
      <span style={{ color: "var(--text-secondary)", fontSize: 11 }}>{label}</span>
      <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>{value ?? "—"}</span>
    </div>
  )
}

export default function SystemPage() {
  const { data, isLoading } = useQuery({ queryKey: ["system"], queryFn: api.systemHealth, refetchInterval: 30_000 })
  if (isLoading) return <div style={{ color: "var(--text-secondary)" }}>Loading...</div>
  if (!data) return null
  const { watch, last_scan_run, open_snapshots, triggered_snapshots, tony_events_total, unacknowledged_warnings } = data
  const ageMin = watch.last_scan_age_seconds !== null ? Math.round(watch.last_scan_age_seconds / 60) : null

  return (
    <div>
      <h1 style={{ fontSize: 13, fontWeight: 600, marginBottom: 16, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
        ⚙ System
      </h1>
      <KPIBar items={[
        { label: "Watch Status",   value: watch.status ?? "—" },
        { label: "Open Snapshots", value: open_snapshots },
        { label: "Triggered",      value: triggered_snapshots },
        { label: "Tony Events",    value: tony_events_total },
        { label: "Unacked Warn",   value: unacknowledged_warnings },
      ]} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className="card">
          <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--text-secondary)", letterSpacing: "0.08em", marginBottom: 8 }}>Watch Run</div>
          <Field label="Status"         value={watch.status} />
          <Field label="Started"        value={watch.started_at?.slice(0, 19) ?? null} />
          <Field label="Last Heartbeat" value={watch.last_heartbeat_at?.slice(0, 19) ?? null} />
          <Field label="Cycles"         value={watch.cycles_completed} />
          <Field label="API Requests"   value={watch.api_requests} />
          <Field label="Symbols Scored" value={watch.symbols_scanned} />
          <Field label="Last Scan Age"  value={ageMin !== null ? `${ageMin}m` : null} />
        </div>
        <div className="card">
          <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--text-secondary)", letterSpacing: "0.08em", marginBottom: 8 }}>Last Scan Run</div>
          {last_scan_run ? (
            <>
              <Field label="ID"         value={last_scan_run.id} />
              <Field label="Provider"   value={last_scan_run.provider} />
              <Field label="Universe"   value={last_scan_run.universe_count} />
              <Field label="Created"    value={last_scan_run.created_at.slice(0, 19)} />
            </>
          ) : <p style={{ color: "var(--text-secondary)", fontSize: 11 }}>No scan runs yet</p>}
        </div>
      </div>
      {unacknowledged_warnings > 0 && (
        <div style={{ marginTop: 16, padding: "10px 14px", background: "rgba(255,171,0,0.08)", border: "1px solid var(--amber)", borderRadius: 4 }}>
          <span style={{ color: "var(--amber)", fontSize: 12 }}>⚠ {unacknowledged_warnings} unacknowledged warning(s)</span>
        </div>
      )}
    </div>
  )
}
