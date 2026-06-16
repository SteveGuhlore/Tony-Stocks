import { describe, it, expect, beforeEach, afterEach } from "vitest"
import {
  DEBUG_STORAGE_KEY,
  escapeHtml,
  formatErrorAsText,
  formatErrorsAsText,
  isDebugEnabled,
  type CapturedError,
} from "@/lib/debug"
import { clearErrors, describeThrown, getErrors, pushError, subscribe } from "./store"

describe("escapeHtml", () => {
  it("escapes all five HTML-significant characters", () => {
    expect(escapeHtml(`<img src=x onerror="alert('xss')">`)).toBe(
      "&lt;img src=x onerror=&quot;alert(&#39;xss&#39;)&quot;&gt;",
    )
  })
  it("escapes ampersands first so entities aren't double-broken", () => {
    expect(escapeHtml("a & <b>")).toBe("a &amp; &lt;b&gt;")
  })
  it("coerces null/undefined/numbers to a safe string", () => {
    expect(escapeHtml(null)).toBe("")
    expect(escapeHtml(undefined)).toBe("")
    expect(escapeHtml(42)).toBe("42")
  })
})

describe("formatErrorAsText", () => {
  const base: CapturedError = {
    id: 1,
    kind: "error",
    message: "boom",
    time: 0,
  }
  it("renders kind, message, and location when present", () => {
    const txt = formatErrorAsText({ ...base, source: "app.js", line: 12, column: 3, stack: "Error: boom\n  at x" })
    expect(txt).toContain("ERROR: boom")
    expect(txt).toContain("at app.js:12:3")
    expect(txt).toContain("Error: boom")
  })
  it("omits the location line when there is no source/line/column", () => {
    expect(formatErrorAsText(base)).not.toContain(" at ")
  })
})

describe("formatErrorsAsText", () => {
  it("reports an empty state", () => {
    expect(formatErrorsAsText([])).toBe("(no errors captured)")
  })
  it("includes a count header and joins entries", () => {
    const txt = formatErrorsAsText([
      { id: 1, kind: "error", message: "one", time: 0 },
      { id: 2, kind: "react", message: "two", time: 0 },
    ])
    expect(txt).toContain("2 captured errors")
    expect(txt).toContain("one")
    expect(txt).toContain("two")
  })
})

describe("isDebugEnabled gate", () => {
  beforeEach(() => {
    window.localStorage.clear()
    window.history.replaceState({}, "", "/")
  })
  afterEach(() => {
    window.localStorage.clear()
    window.history.replaceState({}, "", "/")
  })

  it("is off by default", () => {
    expect(isDebugEnabled()).toBe(false)
  })
  it("turns on with ?debug=1 and persists the flag", () => {
    window.history.replaceState({}, "", "/?debug=1")
    expect(isDebugEnabled()).toBe(true)
    expect(window.localStorage.getItem(DEBUG_STORAGE_KEY)).toBe("1")
  })
  it("turns on with #debug", () => {
    window.history.replaceState({}, "", "/#debug")
    expect(isDebugEnabled()).toBe(true)
  })
  it("stays on from the persisted flag without a URL param", () => {
    window.localStorage.setItem(DEBUG_STORAGE_KEY, "1")
    expect(isDebugEnabled()).toBe(true)
  })
  it("?debug=0 clears the persisted flag and turns off", () => {
    window.localStorage.setItem(DEBUG_STORAGE_KEY, "1")
    window.history.replaceState({}, "", "/?debug=0")
    expect(isDebugEnabled()).toBe(false)
    expect(window.localStorage.getItem(DEBUG_STORAGE_KEY)).toBeNull()
  })
})

describe("error store", () => {
  beforeEach(() => clearErrors())

  it("stores newest first and notifies subscribers", () => {
    const seen: number[] = []
    const unsub = subscribe((errs) => seen.push(errs.length))
    pushError({ kind: "error", message: "first" })
    pushError({ kind: "error", message: "second" })
    const errs = getErrors()
    expect(errs[0].message).toBe("second")
    expect(errs[1].message).toBe("first")
    expect(errs[0].id).not.toBe(errs[1].id)
    expect(seen).toEqual([1, 2])
    unsub()
  })

  it("clearErrors empties the buffer", () => {
    pushError({ kind: "error", message: "x" })
    clearErrors()
    expect(getErrors()).toHaveLength(0)
  })

  it("describeThrown normalizes Errors, strings, and objects", () => {
    expect(describeThrown(new Error("nope"), "unhandledrejection")).toMatchObject({
      kind: "unhandledrejection",
      message: "nope",
    })
    expect(describeThrown("plain", "error")).toMatchObject({ message: "plain" })
    expect(describeThrown({ a: 1 }, "error").message).toContain("\"a\":1")
  })
})
