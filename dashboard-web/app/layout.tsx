import type { Metadata } from "next"
import "./globals.css"
import { Providers } from "@/lib/providers"
import { Toaster } from "sonner"
import { ErrorBoundary } from "@/components/debug/ErrorBoundary"
import { DebugConsole } from "@/components/debug/DebugConsole"

export const metadata: Metadata = {
  title: "Kinetic Tape — Tony",
  description: "First-pass scanner cockpit",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Space+Mono:wght@400;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <Providers>
          <ErrorBoundary>{children}</ErrorBoundary>
          {/* Sibling of the boundary so a crashing view can't take the console
              down with it. Self-gates: renders nothing for public visitors. */}
          <DebugConsole />
          <Toaster
            theme="dark"
            position="bottom-right"
            toastOptions={{
              style: {
                background: "#0e1614",
                border: "1px solid var(--cyan)",
                color: "var(--ink)",
                fontFamily: "var(--mono)",
                fontSize: "12px",
              },
            }}
          />
        </Providers>
      </body>
    </html>
  )
}
