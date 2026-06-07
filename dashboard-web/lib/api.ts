import type {
  CockpitResponse,
  ChartResponse,
  PaperResponse,
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
  paper: () => get<PaperResponse>("/api/paper/positions"),
  paperEquityCurve: (base_equity?: number) =>
    get<PaperEquityCurve>("/api/paper/equity-curve", { base_equity }),
  symbolChart: (symbol: string, timeframe?: string) =>
    get<ChartResponse>(`/api/symbols/${encodeURIComponent(symbol)}/chart`, { timeframe }),
  morningPrep: () => get<MorningPrepResponse>("/api/morning-prep"),
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
