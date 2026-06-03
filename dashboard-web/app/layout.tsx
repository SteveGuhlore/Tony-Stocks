import type { Metadata } from "next"
import "./globals.css"
import { Providers } from "@/lib/providers"
import { DrawerProvider } from "@/components/overlays/DrawerContext"
import { StatusBar } from "@/components/layout/StatusBar"
import { LazyDrawers } from "@/components/overlays/LazyDrawers"
import { AlertManager } from "@/components/alerts/AlertManager"
import { PermissionBanner } from "@/components/alerts/PermissionBanner"

export const metadata: Metadata = { title: "Tony", description: "Tony's trading cockpit" }

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ background: "var(--bg-base)", minHeight: "100vh" }}>
        <Providers>
          <DrawerProvider>
            <PermissionBanner />
            <StatusBar />
            <main className="app-main" style={{ paddingTop: 48, minHeight: "100vh" }}>
              <div style={{ padding: 16 }}>{children}</div>
            </main>
            <LazyDrawers />
            <AlertManager />
          </DrawerProvider>
        </Providers>
      </body>
    </html>
  )
}
