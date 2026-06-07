"use client"

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { useState, type ReactNode } from "react"

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // polling is the source of truth; SSE is best-effort on top
            refetchInterval: 8000,
            refetchOnWindowFocus: false,
            staleTime: 4000,
            retry: 2,
          },
        },
      }),
  )
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}
