// Default to SAME-ORIGIN (relative) so requests go to the host serving the page and
// Next.js rewrites (see next.config.ts) forward /api/* to the local FastAPI backend.
// This is what makes remote access (SSH tunnel / Tailscale) work — the browser must
// never be asked to reach "localhost", which would mean the user's own device, not the VM.
// Set NEXT_PUBLIC_API_URL only if you intentionally serve the API on a separate origin.
const BASE = process.env.NEXT_PUBLIC_API_URL ?? ""

// Resolve a (possibly relative) path against the page origin in the browser. A bare
// `new URL("/api/x")` throws when BASE is empty; giving it the current origin as the
// base makes relative same-origin URLs valid (and is ignored when BASE is absolute).
function originBase(): string {
  if (typeof window !== "undefined") return window.location.origin
  return "http://127.0.0.1:3000"
}

async function get<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  const url = new URL(`${BASE}${path}`, originBase())
  if (params) Object.entries(params).forEach(([k, v]) => { if (v !== undefined) url.searchParams.set(k, String(v)) })
  const res = await fetch(url.toString(), { cache: "no-store" })
  if (!res.ok) throw new Error(`API ${path} -> ${res.status}`)
  return res.json()
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`API POST ${path} -> ${res.status}`)
  return res.json()
}

export const api = {
  health: () => get<{ status: string; db_path: string }>("/api/health"),
  today: () => get<import("./types").TodayResponse>("/api/today"),
  picks: () => get<import("./types").PicksResponse>("/api/picks"),
  addPick: (body: { symbol: string; entry?: number; stop?: number; target?: number; notes?: string }) =>
    post<{ status: string; symbol: string }>("/api/picks", body),
  tracking: () => get<import("./types").TrackingResponse>("/api/tracking"),
  outcomes: (filter?: string) => get<import("./types").OutcomesResponse>("/api/outcomes", { filter }),
  scanLatest: (p?: { min_score?: number; category?: string; role?: string }) =>
    get<import("./types").LatestScanResponse>("/api/scan/latest", p),
  scanOverview: () => get<{ scanned: number; candidates: number; picks: number; last_scan_at: string | null }>("/api/scan/overview"),
  analytics: () => get<import("./types").AnalyticsResponse>("/api/analytics/backtest"),
  events: (p?: { severity?: string; limit?: number; unacked_only?: boolean }) =>
    get<import("./types").TonyEventsResponse>("/api/events", p),
  systemHealth: () => get<import("./types").SystemHealthResponse>("/api/system/health"),
  symbolDetail: (symbol: string) => get<import("./types").SymbolDetailResponse>(`/api/symbols/${symbol}/detail`),
  symbolChart: (symbol: string, days = 60) =>
    get<{ bars: { date: string; open: number; high: number; low: number; close: number; volume: number }[] }>(
      `/api/symbols/${symbol}/chart`, { days }),
  vaultBridge: () => get<import("./types").VaultBridgeSummary>("/api/vault/bridge"),
  streamUrl: () => `${BASE}/api/events/stream`,
  prices: () => get<import("./types").PricesResponse>("/api/prices"),
  priceSymbol: (symbol: string) => get<import("./types").LiveQuote>(`/api/prices/${symbol}`),
  commandCenter: () => get<import("./types").CommandCenterResponse>("/api/command-center"),
  paper: () => get<import("./types").PaperResponse>("/api/paper/positions"),
  paperEquityCurve: (base_equity?: number) =>
    get<import("./types").PaperEquityCurve>("/api/paper/equity-curve", { base_equity }),
  morningPrep: () => get<import("./types").MorningPrepResponse>("/api/morning-prep"),
}
