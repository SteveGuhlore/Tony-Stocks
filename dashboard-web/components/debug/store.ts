/**
 * Tiny module-level error store shared by the window-event capture engine and
 * the React error boundary, so render errors and runtime errors land in one
 * newest-first list. Plain pub/sub — no React, no deps — so it cannot itself
 * be the thing that crashes the app it is meant to surface.
 */

import type { CapturedError, ErrorKind } from "@/lib/debug"

export type { CapturedError }

type Listener = (errors: CapturedError[]) => void

const MAX_ERRORS = 200

let errors: CapturedError[] = []
let nextId = 1
const listeners = new Set<Listener>()

function emit() {
  for (const l of listeners) l(errors)
}

export function subscribe(fn: Listener): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}

export function getErrors(): CapturedError[] {
  return errors
}

export function pushError(
  e: Omit<CapturedError, "id" | "time"> & Partial<Pick<CapturedError, "time">>,
): void {
  const entry: CapturedError = {
    id: nextId++,
    time: e.time ?? Date.now(),
    kind: e.kind,
    message: e.message,
    source: e.source,
    line: e.line,
    column: e.column,
    stack: e.stack,
  }
  // newest first; cap the buffer so a runaway error loop can't eat memory
  errors = [entry, ...errors].slice(0, MAX_ERRORS)
  emit()
}

export function clearErrors(): void {
  errors = []
  emit()
}

/** Normalize a thrown value (Error or anything) into store fields. */
export function describeThrown(value: unknown, kind: ErrorKind) {
  if (value instanceof Error) {
    return { kind, message: value.message || value.name || "Error", stack: value.stack }
  }
  if (typeof value === "string") return { kind, message: value }
  try {
    return { kind, message: JSON.stringify(value) }
  } catch {
    return { kind, message: String(value) }
  }
}
