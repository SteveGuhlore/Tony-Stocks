import type {
  CockpitResponse,
  ChartResponse,
  PaperResponse,
  PaperPosition,
  PaperEquityCurve,
  CommandCenterResponse,
  MorningPrepResponse,
  SystemHealthResponse,
} from "./types"

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001"

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message)
    this.name = "ApiError"
  }
}

async function get<T>(
  path: string,
  params?: Record<string, string | number | boolean | undefined>,
): Promise<T> {
  const url = new URL(`${API_BASE}${path}`)
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined) url.searchParams.set(k, String(v))
    })
  }
  const res = await fetch(url.toString(), { cache: "no-store" })
  if (!res.ok) throw new ApiError(res.status, `GET ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new ApiError(res.status, `POST ${path} → ${res.status}`)
  return res.json() as Promise<T>
}

export const api = {
  /** PRIMARY read model — one row per symbol, all views derive from this. */
  cockpit: () => get<CockpitResponse>("/api/cockpit"),
  commandCenter: () => get<CommandCenterResponse>("/api/command-center"),
  // The API returns {enabled, account_label, open[], closed[], summary}; the UI
  // consumes {positions, equity, open_pl, realized_pl}. Normalize here so every
  // consumer (Cockpit drawer + PaperBook) gets a stable shape and never reads
  // `.positions` off undefined.
  paper: async (): Promise<PaperResponse> => {
    const raw = await get<{
      enabled?: boolean
      account_label?: string
      open?: Array<Record<string, unknown>>
      summary?: { realized_pl?: number | null }
    }>("/api/paper/positions")
    const open = raw.open ?? []
    const positions: PaperPosition[] = open.map((p) => ({
      symbol: String(p.symbol ?? ""),
      qty: Number(p.qty ?? 0),
      avg_entry_price: (p.entry_price as number | null) ?? null,
      fill_price: (p.entry_price as number | null) ?? null,
      last_price: (p.last_price as number | null) ?? null,
      unrealized_pl: (p.unrealized_pl as number | null) ?? null,
      unrealized_pl_pct: (p.unrealized_pl_pct as number | null) ?? null,
      protection_status: (p.protection_status as string | null) ?? null,
      stop: (p.stop as number | null) ?? null,
      target: (p.target as number | null) ?? null,
      opened_at: (p.opened_at as string | null) ?? null,
    }))
    const openPl = positions.reduce((s, p) => s + (p.unrealized_pl ?? 0), 0)
    return {
      status: raw.enabled ? "enabled" : "disabled",
      equity: null, // equity number lives in /paper/equity-curve, not this endpoint
      open_pl: positions.length ? openPl : null,
      realized_pl: raw.summary?.realized_pl ?? null,
      positions,
    }
  },
  paperEquityCurve: (base_equity?: number) =>
    get<PaperEquityCurve>("/api/paper/equity-curve", { base_equity }),
  symbolChart: (symbol: string, timeframe?: string) =>
    get<ChartResponse>(`/api/symbols/${encodeURIComponent(symbol)}/chart`, { timeframe }),
  morningPrep: () => get<MorningPrepResponse>("/api/morning-prep"),
  systemHealth: () => get<SystemHealthResponse>("/api/system/health"),
  streamUrl: () => `${API_BASE}/api/events/stream`,

  /* control endpoints (wired behind confirm dialogs; no-op in dev fence) */
  control: {
    stopWatch: (body: unknown) => post<{ status: string }>("/api/controls/stop-watch", body),
    pausePaper: (body: unknown) => post<{ status: string }>("/api/controls/pause-paper", body),
    resumePaper: (body: unknown) => post<{ status: string }>("/api/controls/resume-paper", body),
    flattenAll: (body: unknown) => post<{ status: string }>("/api/controls/flatten-all", body),
    flattenOne: (body: unknown) => post<{ status: string }>("/api/controls/flatten-one", body),
    reProtect: (body: unknown) => post<{ status: string }>("/api/controls/re-protect", body),
    triggerScan: (body: unknown) => post<{ status: string }>("/api/controls/trigger-scan", body),
    ackAlert: (body: unknown) => post<{ status: string }>("/api/controls/ack-alert", body),
  },
}
