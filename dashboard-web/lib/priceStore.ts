"use client"

import { useSyncExternalStore } from "react"

/**
 * Isolated per-symbol live-price store. Components subscribe to a single symbol,
 * so a tick on one symbol re-renders only that row — not the whole virtualized tape.
 */
interface Tick {
  price: number | null
  changePct: number | null
}

const ticks = new Map<string, Tick>()
const listeners = new Map<string, Set<() => void>>()

function emit(symbol: string) {
  listeners.get(symbol)?.forEach((l) => l())
}

export function setTick(symbol: string, tick: Tick) {
  ticks.set(symbol, tick)
  emit(symbol)
}

export function seedTicks(rows: { symbol: string; last_price: number | null; day_change_pct: number | null }[]) {
  for (const r of rows) {
    // only seed if we have no live tick yet (don't clobber fresher data)
    if (!ticks.has(r.symbol)) {
      ticks.set(r.symbol, { price: r.last_price, changePct: r.day_change_pct })
    }
  }
}

function subscribe(symbol: string, cb: () => void) {
  let set = listeners.get(symbol)
  if (!set) {
    set = new Set()
    listeners.set(symbol, set)
  }
  set.add(cb)
  return () => {
    set?.delete(cb)
  }
}

const EMPTY: Tick = { price: null, changePct: null }

export function useLiveTick(symbol: string): Tick {
  return useSyncExternalStore(
    (cb) => subscribe(symbol, cb),
    () => ticks.get(symbol) ?? EMPTY,
    () => EMPTY,
  )
}
