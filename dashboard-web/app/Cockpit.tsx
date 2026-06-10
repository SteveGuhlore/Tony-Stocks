"use client"

import { useEffect, useMemo, useState } from "react"
import { useCockpit, usePaper, usePaperEquityCurve, useFlattenAll, useTriggerScan } from "@/lib/hooks"
import { useEventStream } from "@/lib/useEventStream"
import { seedTicks } from "@/lib/priceStore"
import { autoPhase, type Phase } from "@/lib/phase"
import { TopBar } from "@/components/layout/TopBar"
import { Rail, type RailView } from "@/components/layout/Rail"
import { UniverseField } from "@/components/kinetic/UniverseField"
import { Tape } from "@/components/tape/Tape"
import { SymbolDrawer } from "@/components/drawer/SymbolDrawer"
import { CommandPalette, type PaletteCommand } from "@/components/kinetic/CommandPalette"
import { ConfirmDialog, type ConfirmSpec } from "@/components/kinetic/ConfirmDialog"
import { TrackRecordView } from "@/components/views/TrackRecordView"
import { PaperBookView } from "@/components/views/PaperBookView"
import { ScannerXrayView } from "@/components/views/ScannerXrayView"
import { SystemView } from "@/components/views/SystemView"
import { PrepView } from "@/components/views/PrepView"
import { ReviewView } from "@/components/views/ReviewView"
import { toast } from "sonner"

export default function Cockpit() {
  const { data, isLoading, isError } = useCockpit()
  const paper = usePaper()
  const equityCurve = usePaperEquityCurve()
  // Mark-to-market paper equity for the header: base + realized + open unrealized.
  const _baseEq = equityCurve.data?.base_equity ?? null
  const _pl = (paper.data?.realized_pl ?? 0) + (paper.data?.open_pl ?? 0)
  const headerEquity = _baseEq != null ? _baseEq + _pl : null
  const headerEquityPct = _baseEq ? (_pl / _baseEq) * 100 : null
  const stream = useEventStream((e) => {
    if (e.type === "entry_triggered" && e.symbol) {
      toast.success(`${e.symbol} entry triggered`, { description: e.message })
    }
  })

  const [view, setView] = useState<RailView>("cockpit")
  const [manualPhase, setManualPhase] = useState<Phase | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [confirm, setConfirm] = useState<ConfirmSpec | null>(null)
  // .mutate is referentially stable — safe for the commands memo deps.
  const { mutate: flattenAllMutate } = useFlattenAll()
  const { mutate: triggerScanMutate } = useTriggerScan()

  const rows = useMemo(() => data?.rows ?? [], [data])
  const phase = manualPhase ?? autoPhase(data?.market)

  // seed per-row price store from polled snapshot (SSE/live ticks layer on top)
  useEffect(() => {
    if (rows.length) seedTicks(rows)
  }, [rows])

  // ⌘K
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setPaletteOpen(true)
      }
      if (e.key === "Escape") {
        setPaletteOpen(false)
        setSelected(null)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const selectedRow = rows.find((r) => r.symbol === selected) ?? null
  const selectedPos = paper.data?.positions?.find((p) => p.symbol === selected) ?? null

  const commands: PaletteCommand[] = useMemo(
    () => [
      { id: "v-record", label: "✦ Go to Track Record", kind: "view", run: () => setView("record") },
      { id: "v-paper", label: "▤ Go to Paper Book", kind: "view", run: () => setView("paper") },
      { id: "v-xray", label: "◎ Go to Scanner X-ray", kind: "view", run: () => setView("xray") },
      { id: "v-system", label: "⚙ Go to System", kind: "view", run: () => setView("system") },
      {
        id: "a-flatten",
        label: "💥 Flatten all positions",
        kind: "action",
        danger: true,
        run: () =>
          setConfirm({
            title: "Flatten ALL positions?",
            body: "Closes every open paper position. PIN required. No-op in dev fence.",
            confirmLabel: "Flatten all",
            danger: true,
            requirePin: true,
            onConfirm: (pin) => flattenAllMutate({ pin }),
          }),
      },
      {
        id: "a-scan",
        label: "↻ Trigger scan now",
        kind: "action",
        run: () =>
          setConfirm({
            title: "Trigger a manual scan?",
            body: "Kicks a manual scan cycle. No-op in dev fence.",
            confirmLabel: "Trigger scan",
            onConfirm: (pin) => triggerScanMutate({ pin }),
          }),
      },
    ],
    [flattenAllMutate, triggerScanMutate],
  )

  const counts = data?.counts
  const sessionLabel =
    data?.market?.session_label ??
    (phase === "prep" ? "PRE-OPEN" : phase === "review" ? "CLOSED" : "MARKET OPEN")

  return (
    <div>
      <TopBar
        phase={phase}
        onPhase={(p) => setManualPhase(p)}
        sessionLabel={sessionLabel}
        equity={headerEquity}
        equityPct={headerEquityPct}
        streamState={stream.state}
        onOpenPalette={() => setPaletteOpen(true)}
      />

      <div className="kt-shell">
        <Rail view={view} onView={setView} />

        <main className="kt-main">
          {view === "cockpit" && phase === "live" && (
            <>
              <div
                className="relative kt-panel"
                style={{ overflow: "hidden", padding: "18px 18px", marginBottom: 14 }}
              >
                <UniverseField nodeCount={70} />
                <div style={{ position: "relative" }}>
                  <h2 style={{ fontSize: 22 }}>The Tape</h2>
                  <p className="text-mut" style={{ fontSize: 11, marginTop: 4 }}>
                    {counts
                      ? `${counts.watching} watching · ${counts.near} near · ${counts.triggered} triggered`
                      : "loading scanner…"}
                  </p>
                </div>
              </div>
              {isError ? (
                <ErrorPanel />
              ) : isLoading ? (
                <LoadingPanel />
              ) : (
                <Tape rows={rows} onOpen={setSelected} />
              )}
            </>
          )}
          {view === "cockpit" && phase === "prep" && <PrepView onOpenSymbol={setSelected} />}
          {view === "cockpit" && phase === "review" && <ReviewView />}
          {view === "record" && <TrackRecordView />}
          {view === "paper" && <PaperBookView onConfirm={setConfirm} onOpenSymbol={setSelected} />}
          {view === "xray" && <ScannerXrayView />}
          {view === "system" && <SystemView onConfirm={setConfirm} streamState={stream.state} />}
        </main>
      </div>

      <SymbolDrawer
        row={selectedRow}
        position={selectedPos}
        onClose={() => setSelected(null)}
        onConfirm={setConfirm}
      />
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        rows={rows}
        commands={commands}
        onSymbol={setSelected}
      />
      <ConfirmDialog spec={confirm} onClose={() => setConfirm(null)} />
    </div>
  )
}

function LoadingPanel() {
  return (
    <div className="kt-panel grid place-items-center text-dim" style={{ height: 200, fontSize: 12 }}>
      Loading the tape…
    </div>
  )
}

function ErrorPanel() {
  return (
    <div className="kt-panel grid place-items-center text-mut" style={{ height: 200, fontSize: 12, textAlign: "center" }}>
      <div>
        Cannot reach the API at <span className="num">{process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001"}</span>.
        <br />
        Retrying automatically — start the backend to populate the tape.
      </div>
    </div>
  )
}
