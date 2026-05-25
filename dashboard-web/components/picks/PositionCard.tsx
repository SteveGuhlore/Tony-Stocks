"use client"

import { StatusBadge } from "@/components/terminal/StatusBadge"
import { TickerSymbol } from "@/components/terminal/TickerSymbol"
import { TimeInTrade } from "./TimeInTrade"
import { PLBadge } from "./PLBadge"
import { RiskGauge } from "./RiskGauge"
import type { LiveQuote } from "@/lib/types"

export interface PositionCardProps {
  symbol: string
  status: string
  setupCategory: string | null
  entry: number | null
  stop: number | null
  target: number | null
  rr: number | null
  score: number | null
  triggeredAt: string | null
  watchingSince: string | null
  triggered: boolean
  thesis: string | null
  thesisLabel: string | null
  thesisAction: string | null
  quote: LiveQuote | undefined
}

export function PositionCard({
  symbol, status, setupCategory, entry, stop, target, rr, score,
  triggeredAt, watchingSince, triggered,
  thesis, thesisLabel, thesisAction, quote,
}: PositionCardProps) {
  const price = quote?.price ?? null
  const hasLevels = entry !== null && stop !== null && target !== null
  const since = triggered ? triggeredAt : watchingSince

  const distPct = (entry !== null && price !== null && entry !== 0)
    ? ((price - entry) / entry) * 100
    : null

  const borderColor = triggered
    ? (price !== null && entry !== null && price >= entry ? "var(--green)" : "var(--amber)")
    : "var(--border)"

  const lbl: React.CSSProperties = {
    fontSize: 9, textTransform: "uppercase", letterSpacing: "0.06em",
    color: "var(--text-secondary)", marginBottom: 2,
  }
  const priceNum: React.CSSProperties = {
    fontFamily: "JetBrains Mono, monospace", fontSize: 17, fontWeight: 600,
  }

  return (
    <div style={{
      background: "var(--bg-surface)",
      border: "1px solid var(--border)",
      borderLeft: `3px solid ${borderColor}`,
      borderRadius: 6,
      padding: "14px 16px",
      marginBottom: 10,
      transition: "border-left-color 0.6s ease",
    }}>

      {/* Header */}
      <div style={{
        display: "flex", alignItems: "flex-start",
        justifyContent: "space-between", marginBottom: 14,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <TickerSymbol symbol={symbol} />
          <StatusBadge status={status} />
          {setupCategory && (
            <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{setupCategory}</span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0, marginLeft: 12 }}>
          {score !== null && (
            <span style={{
              fontSize: 10, color: "var(--cyan)",
              fontFamily: "JetBrains Mono, monospace",
              background: "rgba(0,229,255,0.08)",
              borderRadius: 3, padding: "1px 6px",
            }}>
              {score.toFixed(1)}
            </span>
          )}
          <TimeInTrade since={since} label={triggered ? "in trade" : "watching"} />
        </div>
      </div>

      {/* Price row */}
      <div style={{
        display: "flex", alignItems: "center",
        justifyContent: "space-between", marginBottom: 16,
      }}>
        {triggered ? (
          <div style={{ display: "flex", alignItems: "flex-end", gap: 10 }}>
            {entry !== null && (
              <div>
                <div style={lbl}>Entry</div>
                <div style={{ ...priceNum, color: "var(--text-secondary)" }}>${entry.toFixed(2)}</div>
              </div>
            )}
            <div style={{ fontSize: 16, color: "var(--text-secondary)", paddingBottom: 2 }}>→</div>
            <div>
              <div style={lbl}>Now</div>
              <div style={{ ...priceNum, color: "var(--text-primary)" }}>
                {price !== null ? `$${price.toFixed(2)}` : "—"}
              </div>
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", alignItems: "flex-end", gap: 10 }}>
            <div>
              <div style={lbl}>Live</div>
              <div style={{ ...priceNum, color: "var(--text-primary)" }}>
                {price !== null ? `$${price.toFixed(2)}` : "—"}
              </div>
            </div>
            {entry !== null && (
              <>
                <div style={{ fontSize: 16, color: "var(--text-secondary)", paddingBottom: 2 }}>→</div>
                <div>
                  <div style={lbl}>Entry</div>
                  <div style={{ ...priceNum, color: "var(--cyan)" }}>${entry.toFixed(2)}</div>
                </div>
              </>
            )}
          </div>
        )}

        {/* P&L (triggered only) or distance-to-entry (watching only — never P&L) */}
        {triggered && entry !== null && price !== null ? (
          <PLBadge entry={entry} currentPrice={price} />
        ) : !triggered && distPct !== null ? (
          <div style={{ textAlign: "right" }}>
            <div style={lbl}>To Entry</div>
            <div style={{
              fontFamily: "JetBrains Mono, monospace", fontSize: 20, fontWeight: 700,
              color: Math.abs(distPct) <= 2 ? "var(--amber)" : "var(--text-secondary)",
            }}>
              {distPct > 0 ? "+" : ""}{distPct.toFixed(2)}%
            </div>
          </div>
        ) : null}
      </div>

      {/* Risk gauge */}
      {hasLevels && (
        <RiskGauge
          entry={entry!}
          stop={stop!}
          target={target!}
          currentPrice={price}
          triggered={triggered}
          dayHigh={quote?.day_high}
          dayLow={quote?.day_low}
        />
      )}

      {/* Bot thesis */}
      {thesis && (
        <div style={{
          marginTop: 12, padding: "8px 10px",
          background: "var(--bg-elevated)",
          borderRadius: 4, borderLeft: "2px solid var(--cyan)",
        }}>
          {(thesisLabel || thesisAction) && (
            <div style={{ fontSize: 10, color: "var(--amber)", marginBottom: 4, fontWeight: 600 }}>
              {[thesisLabel, thesisAction].filter(Boolean).join(" — ")}
            </div>
          )}
          <p style={{
            margin: 0, fontSize: 11,
            color: "var(--text-secondary)",
            fontStyle: "italic", lineHeight: 1.5,
          }}>
            &ldquo;{thesis}&rdquo;
          </p>
        </div>
      )}

      {/* Levels footer */}
      <div style={{
        display: "flex", gap: 16, marginTop: 12,
        fontSize: 10, fontFamily: "JetBrains Mono, monospace",
      }}>
        {stop   !== null && <span style={{ color: "var(--red)"            }}>SL ${stop.toFixed(2)}</span>}
        {target !== null && <span style={{ color: "var(--green)"          }}>TP ${target.toFixed(2)}</span>}
        {rr     !== null && <span style={{ color: "var(--text-secondary)" }}>R:R {rr.toFixed(1)}:1</span>}
      </div>
    </div>
  )
}
