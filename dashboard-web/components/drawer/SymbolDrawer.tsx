"use client"

import { AnimatePresence, motion } from "motion/react"
import { useState } from "react"
import type { CockpitRow, PaperPosition } from "@/lib/types"
import {
  useSymbolChart,
  usePins,
  useNotes,
  useSetPin,
  useAddNote,
  useAddPriceAlert,
  useFlattenOne,
} from "@/lib/hooks"
import { SymbolChart } from "./SymbolChart"
import { Button } from "@/components/kinetic/Button"
import type { ConfirmSpec } from "@/components/kinetic/ConfirmDialog"
import { normalizeVerdict } from "@/lib/verdict"
import { fmtPrice, fmtPct, fmtScore, fmtMoney, fmtRvol, changeClass } from "@/lib/format"
import { subScoreArray, statusBadge, effectivePrice, scoreDelta } from "@/lib/rows"
import { SUB_SCORE_LABELS, SUB_SCORE_KEYS } from "@/lib/tokens"
import { duration, easing } from "@/lib/motion-tokens"

/** Dual-source symbol deep-dive (mockup 11): bot vs Tony, both scores. */
export function SymbolDrawer({
  row,
  position,
  onClose,
  onConfirm,
}: {
  row: CockpitRow | null
  position: PaperPosition | null
  onClose: () => void
  onConfirm: (s: ConfirmSpec) => void
}) {
  return (
    <AnimatePresence>
      {row && (
        <DrawerInner key={row.symbol} row={row} position={position} onClose={onClose} onConfirm={onConfirm} />
      )}
    </AnimatePresence>
  )
}

function DrawerInner({
  row,
  position,
  onClose,
  onConfirm,
}: {
  row: CockpitRow
  position: PaperPosition | null
  onClose: () => void
  onConfirm: (s: ConfirmSpec) => void
}) {
  const chart = useSymbolChart(row.symbol)
  const price = effectivePrice(row)
  const chg = row.day_change_pct
  const chgCls = changeClass(chg)
  const chgColor = chgCls === "pos" ? "var(--pos)" : chgCls === "neg" ? "var(--neg)" : "var(--mut)"
  const subs = subScoreArray(row.sub_scores)
  const tonyV = normalizeVerdict(row.tony?.verdict)
  const delta = scoreDelta(row)
  const badge = statusBadge(row)

  // personalize state (pins / notes / price alerts) + flatten-one
  const pins = usePins()
  const notes = useNotes(row.symbol)
  const setPin = useSetPin()
  const addNote = useAddNote()
  const addAlert = useAddPriceAlert()
  const flattenOne = useFlattenOne()
  const pinned = (pins.data?.pins ?? []).some(
    (p) => (p.symbol ?? "").toUpperCase() === row.symbol.toUpperCase(),
  )
  const [panel, setPanel] = useState<"note" | "alert" | null>(null)
  const [noteText, setNoteText] = useState("")
  const [alertPrice, setAlertPrice] = useState(() => (price != null ? String(price) : ""))
  const [alertDir, setAlertDir] = useState<"above" | "below">("above")
  const alertPriceNum = Number(alertPrice)
  const alertOk = alertPrice.trim() !== "" && Number.isFinite(alertPriceNum) && alertPriceNum > 0
  const symbolNotes = notes.data?.notes ?? []

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: duration.fast }}
        onClick={onClose}
        className="fixed inset-0 z-40"
        style={{ background: "rgba(0,0,0,.5)" }}
      />
      <motion.aside
        role="dialog"
        aria-label={`${row.symbol} detail`}
        initial={{ x: 40, opacity: 0.4 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: 40, opacity: 0 }}
        transition={{ duration: duration.normal, ease: easing.drawer }}
        className="fixed top-0 right-0 z-50 h-full overflow-y-auto"
        style={{
          width: 560,
          maxWidth: "96vw",
          background: "var(--bg2)",
          borderLeft: "1px solid rgba(55,224,255,.22)",
          boxShadow: "-30px 0 80px rgba(0,0,0,.6)",
        }}
      >
        {/* header */}
        <div
          className="sticky top-0 z-10"
          style={{
            background: "linear-gradient(180deg,#10160f,var(--bg2))",
            borderBottom: "1px solid var(--line)",
            padding: "16px 18px",
          }}
        >
          <div className="flex items-center gap-[11px]">
            <h1 style={{ fontSize: 32 }}>{row.symbol}</h1>
            <div className="flex flex-col">
              <span className="num" style={{ fontSize: 17, lineHeight: 1.1, color: chgColor }}>
                {fmtPrice(price)} &nbsp;{fmtPct(chg)}
              </span>
              <span className="text-dim" style={{ fontSize: 8.5 }}>
                last · day change vs prev close
              </span>
            </div>
            <button
              onClick={onClose}
              aria-label="Close"
              className="ml-auto grid place-items-center text-mut"
              style={{ width: 30, height: 30, borderRadius: 8, border: "1px solid var(--line)", fontSize: 18, cursor: "pointer", background: "transparent" }}
            >
              ✕
            </button>
          </div>
          <div className="flex flex-wrap gap-[7px]" style={{ marginTop: 9 }}>
            {row.sector && <Tag>{row.sector}</Tag>}
            {row.setup_category && <Tag>{row.setup_category}</Tag>}
            {badge.kind === "near" && <Tag near>{badge.label}</Tag>}
            {row.rvol != null && <Tag>RVOL {fmtRvol(row.rvol)}</Tag>}
          </div>
        </div>

        {/* chart */}
        <Section cap="Price & plan" gate="◎ full chart — gated here">
          <SymbolChart data={chart.data} loading={chart.isLoading} />
          <div className="flex gap-[14px]" style={{ marginTop: 8, fontSize: 11 }}>
            <span>
              R:R <b className="font-display">{row.rr != null ? row.rr.toFixed(1) : "—"}</b>
            </span>
            <span style={{ color: "var(--cyan)" }}>
              entry <b className="font-display">{fmtPrice(row.entry)}</b>
            </span>
            <span style={{ color: "var(--neg)" }}>
              stop <b className="font-display">{fmtPrice(row.stop)}</b>
            </span>
            <span style={{ color: "var(--pos)" }}>
              target <b className="font-display">{fmtPrice(row.target)}</b>
            </span>
          </div>
        </Section>

        {/* dual score */}
        <Section cap="Two reads on this name · scores compared">
          <div
            className="flex items-center gap-[12px]"
            style={{
              marginBottom: 12,
              padding: "11px 14px",
              border: "1px solid var(--line)",
              borderRadius: 11,
              background: "linear-gradient(90deg,rgba(55,224,255,.07),rgba(255,158,44,.07))",
            }}
          >
            <div className="flex-1 text-center">
              <div className="font-display font-bold" style={{ fontSize: 30, lineHeight: 1, color: "var(--cyan)" }}>
                {fmtScore(row.score)}
              </div>
              <div className="text-dim" style={{ fontSize: 8.5, textTransform: "uppercase", letterSpacing: ".08em", marginTop: 3 }}>
                This scanner
              </div>
            </div>
            <div className="text-center text-mut" style={{ fontSize: 11 }}>
              vs
              <b className="block font-display text-ink" style={{ fontSize: 14 }}>
                {delta == null ? "—" : `${delta >= 0 ? "+" : ""}${delta}`}
              </b>
              <span className="text-dim" style={{ fontSize: 8.5 }}>
                {delta == null ? "awaiting" : delta >= 0 ? "bot higher" : "Tony higher"}
              </span>
            </div>
            <div className="flex-1 text-center">
              <div className="font-display font-bold" style={{ fontSize: 30, lineHeight: 1, color: "var(--amber)" }}>
                {fmtScore(row.tony?.score ?? null)}
              </div>
              <div className="text-dim" style={{ fontSize: 8.5, textTransform: "uppercase", letterSpacing: ".08em", marginTop: 3 }}>
                Tony · 2nd pass
              </div>
            </div>
          </div>

          <div
            className="grid"
            style={{ gridTemplateColumns: "1fr 1fr", border: "1px solid var(--line)", borderRadius: 12, overflow: "hidden" }}
          >
            {/* bot pane */}
            <div style={{ padding: 14, background: "linear-gradient(180deg,rgba(55,224,255,.06),transparent)", borderRight: "1px solid var(--line)" }}>
              <Who color="var(--cyan)" name="This scanner" tag="1st pass" />
              <div className="flex items-baseline gap-[7px]" style={{ marginBottom: 9 }}>
                <span className="font-display font-bold" style={{ fontSize: 26, color: "var(--cyan)" }}>
                  {fmtScore(row.score)}
                </span>
                <span className="text-mut" style={{ fontSize: 10 }}>
                  /100
                </span>
              </div>
              {SUB_SCORE_KEYS.map((k, i) => (
                <SubBar key={k} label={SUB_SCORE_LABELS[k]} value={subs[i]} risk={k === "risk"} />
              ))}
            </div>
            {/* tony pane */}
            <div style={{ padding: 14, background: "linear-gradient(180deg,rgba(255,158,44,.06),transparent)" }}>
              <Who color="var(--amber)" name="Tony · deep agent" tag="2nd pass" />
              <div className="flex items-baseline gap-[7px]" style={{ marginBottom: 9 }}>
                <span className="font-display font-bold" style={{ fontSize: 26, color: "var(--amber)" }}>
                  {fmtScore(row.tony?.score ?? null)}
                </span>
                <span className="text-mut" style={{ fontSize: 10 }}>
                  /100
                </span>
                <span className={`kt-pill ${tonyV.className}`} style={{ marginLeft: "auto" }}>
                  {tonyV.label}
                </span>
              </div>
              <div className="text-mut" style={{ fontSize: 11, lineHeight: 1.6 }}>
                {row.tony?.reasoning ? (
                  <>
                    <b className="text-ink">Verdict:</b> {row.tony.reasoning}
                  </>
                ) : (
                  <span className="text-dim">Awaiting Tony&apos;s second-pass read.</span>
                )}
              </div>
              {row.tony?.returned_at && (
                <div className="text-dim" style={{ fontSize: 9, marginTop: 8 }}>
                  returned {row.tony.returned_at}
                </div>
              )}
            </div>
          </div>
        </Section>

        {/* paper position (marked-to-live, separate from day change) */}
        <Section cap="Paper position" gate="(separate from day change)">
          {position ? (
            <div style={{ fontSize: 11, lineHeight: 1.7 }}>
              <Line k="Filled" v={`${fmtPrice(position.fill_price ?? position.avg_entry_price)} × ${position.qty}`} />
              <Line k="Last" v={fmtPrice(position.last_price)} />
              <Line
                k="P/L since fill"
                v={`${fmtMoney(position.unrealized_pl, true)} (${fmtPct(position.unrealized_pl_pct)})`}
                color={changeClass(position.unrealized_pl_pct) === "neg" ? "var(--neg)" : "var(--pos)"}
              />
              <Line k="Protection" v={position.protection_status ?? "—"} />
            </div>
          ) : (
            <div style={{ fontSize: 11 }}>
              <span className="text-mut">No open position — fires on entry trigger.</span>
            </div>
          )}
        </Section>

        {/* actions */}
        <div className="flex flex-wrap gap-2" style={{ padding: "15px 18px 0" }}>
          <Button
            style={{
              flex: 1,
              minWidth: 96,
              ...(pinned
                ? { background: "rgba(255,206,74,.16)", border: "1px solid var(--warn)", color: "var(--warn)" }
                : {}),
            }}
            disabled={setPin.isPending}
            aria-pressed={pinned}
            onClick={() => setPin.mutate({ symbol: row.symbol, pinned: !pinned })}
          >
            {setPin.isPending ? "★ …" : pinned ? "★ Pinned" : "☆ Pin"}
          </Button>
          <Button
            style={{ flex: 1, minWidth: 96, ...(panel === "note" ? { border: "1px solid var(--cyan)" } : {}) }}
            onClick={() => setPanel(panel === "note" ? null : "note")}
          >
            ✎ Note{symbolNotes.length ? ` (${symbolNotes.length})` : ""}
          </Button>
          <Button
            style={{ flex: 1, minWidth: 96, ...(panel === "alert" ? { border: "1px solid var(--cyan)" } : {}) }}
            onClick={() => setPanel(panel === "alert" ? null : "alert")}
          >
            🔔 Alert
          </Button>
          {position && (
            <Button
              variant="danger"
              style={{ flex: 1, minWidth: 96 }}
              disabled={flattenOne.isPending}
              onClick={() =>
                onConfirm({
                  title: `Flatten ${row.symbol}?`,
                  body: `Closes the open paper position in ${row.symbol} (${position.qty} shares). PIN required.`,
                  confirmLabel: `Flatten ${row.symbol}`,
                  danger: true,
                  requirePin: true,
                  onConfirm: (pin) => flattenOne.mutate({ pin, symbol: row.symbol }),
                })
              }
            >
              {flattenOne.isPending ? "💥 Flattening…" : "💥 Flatten"}
            </Button>
          )}
        </div>

        {/* inline note editor */}
        {panel === "note" && (
          <div style={{ padding: "12px 18px" }}>
            <div style={{ border: "1px solid var(--line)", borderRadius: 11, padding: 12 }}>
              <div
                style={{ fontSize: 9, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--dim)", marginBottom: 8 }}
              >
                Note on {row.symbol}
              </div>
              <textarea
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                rows={3}
                placeholder="What are you seeing?"
                aria-label={`Note on ${row.symbol}`}
                style={{
                  width: "100%",
                  resize: "vertical",
                  background: "rgba(255,255,255,.04)",
                  border: "1px solid var(--line)",
                  borderRadius: 8,
                  color: "var(--ink)",
                  padding: "8px 12px",
                  fontSize: 12,
                  outline: "none",
                }}
              />
              <div className="flex gap-2 justify-end" style={{ marginTop: 8 }}>
                <Button onClick={() => setPanel(null)}>Cancel</Button>
                <Button
                  variant="primary"
                  disabled={!noteText.trim() || addNote.isPending}
                  style={{ opacity: noteText.trim() && !addNote.isPending ? 1 : 0.5 }}
                  onClick={() =>
                    addNote.mutate(
                      { symbol: row.symbol, body: noteText.trim() },
                      {
                        onSuccess: () => {
                          setNoteText("")
                          setPanel(null)
                        },
                      },
                    )
                  }
                >
                  {addNote.isPending ? "Saving…" : "Save note"}
                </Button>
              </div>
              {symbolNotes.length > 0 && (
                <div style={{ marginTop: 10, borderTop: "1px solid var(--line)", paddingTop: 8 }}>
                  {symbolNotes.slice(0, 3).map((n, i) => (
                    <div key={n.id ?? i} className="text-mut" style={{ fontSize: 11, lineHeight: 1.6 }}>
                      <span className="text-dim" style={{ fontSize: 9 }}>
                        {n.created_at ?? ""}
                      </span>{" "}
                      {n.body}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* inline price-alert editor */}
        {panel === "alert" && (
          <div style={{ padding: "12px 18px" }}>
            <div style={{ border: "1px solid var(--line)", borderRadius: 11, padding: 12 }}>
              <div
                style={{ fontSize: 9, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--dim)", marginBottom: 8 }}
              >
                Price alert on {row.symbol}
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                <input
                  value={alertPrice}
                  onChange={(e) => setAlertPrice(e.target.value)}
                  type="number"
                  step="0.01"
                  min="0"
                  inputMode="decimal"
                  placeholder="target price"
                  aria-label="Alert target price"
                  className="num"
                  style={{
                    width: 110,
                    background: "rgba(255,255,255,.04)",
                    border: "1px solid var(--line)",
                    borderRadius: 8,
                    color: "var(--ink)",
                    padding: "7px 10px",
                    fontSize: 12,
                    outline: "none",
                  }}
                />
                <div className="flex" style={{ border: "1px solid var(--line)", borderRadius: 8, overflow: "hidden" }}>
                  {(["above", "below"] as const).map((d) => (
                    <button
                      key={d}
                      onClick={() => setAlertDir(d)}
                      aria-pressed={alertDir === d}
                      style={{
                        padding: "7px 12px",
                        fontSize: 11,
                        cursor: "pointer",
                        border: "none",
                        background: alertDir === d ? "rgba(55,224,255,.14)" : "transparent",
                        color: alertDir === d ? "var(--cyan)" : "var(--mut)",
                        fontWeight: alertDir === d ? 700 : 400,
                      }}
                    >
                      {d === "above" ? "▲ above" : "▼ below"}
                    </button>
                  ))}
                </div>
                <Button
                  variant="primary"
                  className="ml-auto"
                  disabled={!alertOk || addAlert.isPending}
                  style={{ opacity: alertOk && !addAlert.isPending ? 1 : 0.5 }}
                  onClick={() =>
                    addAlert.mutate(
                      { symbol: row.symbol, target_price: alertPriceNum, direction: alertDir },
                      { onSuccess: () => setPanel(null) },
                    )
                  }
                >
                  {addAlert.isPending ? "Setting…" : "Set alert"}
                </Button>
              </div>
              <div className="text-dim" style={{ fontSize: 9, marginTop: 7 }}>
                fires when last trades {alertDir} {alertOk ? fmtPrice(alertPriceNum) : "—"} · defaults to last price
              </div>
            </div>
          </div>
        )}

        <div style={{ height: 15 }} />
      </motion.aside>
    </>
  )
}

function Section({ cap, gate, children }: { cap: string; gate?: string; children: React.ReactNode }) {
  return (
    <div style={{ padding: "15px 18px", borderBottom: "1px solid var(--line)" }}>
      <div
        className="flex items-center gap-2"
        style={{ fontSize: 9, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--dim)", marginBottom: 11 }}
      >
        {cap}
        {gate && <span className="ml-auto" style={{ color: "var(--cyan)" }}>{gate}</span>}
      </div>
      {children}
    </div>
  )
}

function Who({ color, name, tag }: { color: string; name: string; tag: string }) {
  return (
    <div className="flex items-center gap-2" style={{ marginBottom: 11 }}>
      <span style={{ width: 9, height: 9, borderRadius: "50%", background: color, boxShadow: `0 0 8px ${color}` }} />
      <b className="font-display" style={{ fontSize: 13 }}>
        {name}
      </b>
      <span className="ml-auto text-dim" style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: ".08em" }}>
        {tag}
      </span>
    </div>
  )
}

function SubBar({ label, value, risk }: { label: string; value: number; risk?: boolean }) {
  const weak = risk && value < 50
  return (
    <div className="flex items-center gap-[7px]" style={{ margin: "4px 0", fontSize: 10 }}>
      <span className="text-mut" style={{ width: 58 }}>
        {label}
      </span>
      <div style={{ flex: 1, height: 5, background: "rgba(255,255,255,.07)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${Math.min(100, Math.max(0, value))}%`, background: weak ? "var(--warn)" : "var(--cyan)", borderRadius: 3 }} />
      </div>
      <span>{value}</span>
    </div>
  )
}

function Line({ k, v, color }: { k: string; v: string; color?: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-mut" style={{ width: 110 }}>
        {k}
      </span>
      <span className="ml-auto font-display" style={{ color }}>
        {v}
      </span>
    </div>
  )
}

function Tag({ children, near }: { children: React.ReactNode; near?: boolean }) {
  return (
    <span
      style={{
        fontSize: 10,
        padding: "3px 9px",
        borderRadius: 6,
        background: near ? "rgba(255,206,74,.16)" : "rgba(255,255,255,.05)",
        border: near ? "none" : "1px solid var(--line)",
        color: near ? "var(--warn)" : "var(--mut)",
        fontWeight: near ? 700 : 400,
      }}
    >
      {children}
    </span>
  )
}
