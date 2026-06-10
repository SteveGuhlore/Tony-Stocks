import type {
  CockpitResponse,
  ChartResponse,
  PaperResponse,
  PaperPosition,
  PaperEquityCurve,
  EquityCompareResponse,
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
  commandCenter: async (): Promise<CommandCenterResponse> => {
    // Backend serves {picks, record, agreement}; the UI's Track Record consumes a flat
    // shape. Map Tony's side here; the bot side is filled in the view from /paper.
    const raw = await get<{
      record?: { win_rate?: number | null; equity_curve?: number[]; avg_pl_per_trade?: number | null } | null
      agreement?: {
        agreed_right?: number
        agreed_wrong?: number
        cc_overrode_saved?: number
        cc_overrode_missed?: number
      } | null
      weights?: Record<string, number> | null
      proposed_weights?: Record<string, number> | null
    }>("/api/command-center")
    const eq = raw.record?.equity_curve ?? []
    const agr = raw.agreement
    return {
      tony_win_rate: raw.record?.win_rate ?? null,
      tony_avg_r: null, // Tony's record tracks $ P/L per trade, not R-multiples
      tony_return_pct: eq.length ? eq[eq.length - 1] - 100 : null,
      equity_tony: eq.map((v, i) => ({ t: i, equity: v })),
      bot_win_rate: null,
      bot_avg_r: null,
      bot_return_pct: null,
      equity_bot: [],
      agreement: agr
        ? {
            agreed_right: agr.agreed_right ?? 0,
            agreed_wrong: agr.agreed_wrong ?? 0,
            tony_saved: agr.cc_overrode_saved ?? 0,
            tony_missed: agr.cc_overrode_missed ?? 0,
          }
        : null,
      weights: raw.weights ?? null,
      proposed_weights: raw.proposed_weights ?? null,
    }
  },
  // The API returns {enabled, account_label, open[], closed[], summary}; the UI
  // consumes {positions, equity, open_pl, realized_pl}. Normalize here so every
  // consumer (Cockpit drawer + PaperBook) gets a stable shape and never reads
  // `.positions` off undefined.
  paper: async (): Promise<PaperResponse> => {
    const raw = await get<{
      enabled?: boolean
      account_label?: string
      open?: Array<Record<string, unknown>>
      closed?: Array<Record<string, unknown>>
      summary?: { realized_pl?: number | null; win_rate?: number | null }
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
    // Bot avg R = mean of (exit-entry)/(entry-stop) over closed trades (Track Record).
    const rs: number[] = []
    for (const c of raw.closed ?? []) {
      const entry = Number(c.entry_price)
      const stop = Number(c.stop)
      const exit = Number(c.exit_price)
      if (Number.isFinite(entry) && Number.isFinite(stop) && Number.isFinite(exit) && entry !== stop) {
        rs.push((exit - entry) / (entry - stop))
      }
    }
    return {
      status: raw.enabled ? "enabled" : "disabled",
      equity: null, // equity number lives in /paper/equity-curve, not this endpoint
      open_pl: positions.length ? openPl : null,
      realized_pl: raw.summary?.realized_pl ?? null,
      win_rate: raw.summary?.win_rate ?? null,
      avg_r: rs.length ? rs.reduce((a, b) => a + b, 0) / rs.length : null,
      positions,
    }
  },
  paperEquityCurve: (base_equity?: number) =>
    get<PaperEquityCurve>("/api/paper/equity-curve", { base_equity }),
  equityCompare: (period?: string, timeframe?: string) =>
    get<EquityCompareResponse>("/api/paper/equity-compare", { period, timeframe }),
  symbolChart: (symbol: string, timeframe?: string) =>
    get<ChartResponse>(`/api/symbols/${encodeURIComponent(symbol)}/chart`, { timeframe }),
  morningPrep: () => get<MorningPrepResponse>("/api/morning-prep"),
  // Score → outcome: win rate by score band, from the backtest analytics endpoint.
  // Flattens the by_score_bucket records (target_hit_rate = per-band win rate).
  analytics: async () => {
    const raw = await get<{
      backtest?: {
        win_rate?: number | null
        conclusive_outcomes?: number | null
        by_score_bucket?: Array<Record<string, unknown>>
      } | null
    }>("/api/analytics/backtest")
    const bt = raw.backtest
    const num = (r: Record<string, unknown>, k: string) => Number(r[k] ?? 0)
    const scoreBuckets = (bt?.by_score_bucket ?? []).map((b) => ({
      band: String(b["score_bucket"] ?? ""),
      winRate: b["target_hit_rate"] == null ? null : Number(b["target_hit_rate"]),
      conclusive:
        num(b, "target_hit_count") + num(b, "stop_hit_count") +
        num(b, "partial_move_count") + num(b, "failed_setup_count"),
      total: num(b, "total_snapshots"),
    }))
    return {
      overallWinRate: bt?.win_rate ?? null,
      conclusive: bt?.conclusive_outcomes ?? null,
      scoreBuckets,
    }
  },
  // Funnel drop reasons (pre-scoring rejections) from the latest scan run.
  scanSkipReasons: () =>
    get<{ scanned_at?: string | null; universe_count?: number | null; skip_reasons?: Record<string, number> }>(
      "/api/scan/skip-reasons",
    ),
  systemHealth: () => get<SystemHealthResponse>("/api/system/health"),
  streamUrl: () => `${API_BASE}/api/events/stream`,

  /* control endpoints (wired behind confirm dialogs; no-op in dev fence) */
  control: {
    stopWatch: (body: unknown) => post<{ status: string }>("/api/control/stop-watch", body),
    pausePaper: (body: unknown) => post<{ status: string }>("/api/control/pause-paper", body),
    resumePaper: (body: unknown) => post<{ status: string }>("/api/control/resume-paper", body),
    flattenAll: (body: unknown) => post<{ status: string }>("/api/control/flatten-all", body),
    flattenOne: (body: unknown) => post<{ status: string }>("/api/control/flatten-one", body),
    reProtect: (body: unknown) => post<{ status: string }>("/api/control/re-protect", body),
    triggerScan: (body: unknown) => post<{ status: string }>("/api/control/trigger-scan", body),
    ackAlert: (body: unknown) => post<{ status: string }>("/api/control/ack-alert", body),
  },
}
