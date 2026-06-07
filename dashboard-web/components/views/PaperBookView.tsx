"use client"

import { usePaper, usePaperEquityCurve } from "@/lib/hooks"
import { ViewHeader, Kpis, Panel, Awaiting } from "./shared"
import { MiniLine } from "@/components/kinetic/MiniLine"
import { Button } from "@/components/kinetic/Button"
import { fmtMoney, fmtPrice, fmtPct, changeClass } from "@/lib/format"
import type { ConfirmSpec } from "@/components/kinetic/ConfirmDialog"

export function PaperBookView({
  onConfirm,
  onOpenSymbol,
}: {
  onConfirm: (s: ConfirmSpec) => void
  onOpenSymbol: (s: string) => void
}) {
  const { data, isLoading } = usePaper()
  const curve = usePaperEquityCurve()
  const positions = data?.positions ?? []

  return (
    <div>
      <ViewHeader title="Paper Book" sub="research account · live mark + realized" />
      <Kpis
        items={[
          { label: "Equity", value: fmtMoney(data?.equity ?? null) },
          { label: "Open P/L", value: fmtMoney(data?.open_pl ?? null, true), tone: (data?.open_pl ?? 0) >= 0 ? "pos" : "neg" },
          { label: "Realized", value: fmtMoney(data?.realized_pl ?? null, true) },
          { label: "Open pos.", value: positions.length },
        ]}
      />
      <Panel title="Equity curve">
        {curve.isLoading ? (
          <Awaiting what="equity curve" />
        ) : (
          <MiniLine series={[{ points: curve.data?.points ?? [], color: "var(--lime)", label: "Paper equity" }]} />
        )}
      </Panel>
      <Panel title="Open positions">
        {isLoading ? (
          <Awaiting what="positions" />
        ) : positions.length === 0 ? (
          <div className="text-dim" style={{ fontSize: 11 }}>
            No open positions — entries fire on trigger.
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ color: "var(--dim)", fontSize: 9, textTransform: "uppercase" }}>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Symbol</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Fill</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Qty</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Last</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>P/L</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Protection</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr
                  key={p.symbol}
                  onClick={() => onOpenSymbol(p.symbol)}
                  style={{ borderTop: "1px solid var(--line)", cursor: "pointer" }}
                >
                  <td className="font-display font-semibold" style={{ padding: "7px 6px" }}>
                    {p.symbol}
                  </td>
                  <td className="num" style={{ padding: "7px 6px" }}>
                    {fmtPrice(p.fill_price ?? p.avg_entry_price)}
                  </td>
                  <td className="num" style={{ padding: "7px 6px" }}>
                    {p.qty}
                  </td>
                  <td className="num" style={{ padding: "7px 6px" }}>
                    {fmtPrice(p.last_price)}
                  </td>
                  <td
                    className="num"
                    style={{ padding: "7px 6px", color: changeClass(p.unrealized_pl_pct) === "neg" ? "var(--neg)" : "var(--pos)" }}
                  >
                    {fmtMoney(p.unrealized_pl, true)} ({fmtPct(p.unrealized_pl_pct)})
                  </td>
                  <td className="text-mut" style={{ padding: "7px 6px", fontSize: 10 }}>
                    {p.protection_status ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
      <div className="flex gap-2 flex-wrap">
        <Button
          variant="danger"
          onClick={() =>
            onConfirm({
              title: "Flatten ALL positions?",
              body: "Sends paper SELL orders to close every open position. Double-confirmed with PIN. No-op in dev fence.",
              confirmLabel: "Flatten all",
              danger: true,
              requirePin: true,
              onConfirm: () => {},
            })
          }
        >
          💥 Flatten all
        </Button>
        <Button
          onClick={() =>
            onConfirm({
              title: "Pause paper trading?",
              body: "No new entries until resumed. Open positions keep their brackets.",
              confirmLabel: "Pause paper",
              onConfirm: () => {},
            })
          }
        >
          ⏸ Pause paper
        </Button>
      </div>
    </div>
  )
}
