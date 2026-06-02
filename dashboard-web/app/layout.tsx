import type { Metadata } from "next"
import "./globals.css"
import { Providers } from "@/lib/providers"
import { DrawerProvider } from "@/components/overlays/DrawerContext"
import { Sidebar } from "@/components/layout/Sidebar"
import { LazyDrawers } from "@/components/overlays/LazyDrawers"
import { AlertManager } from "@/components/alerts/AlertManager"
import { PermissionBanner } from "@/components/alerts/PermissionBanner"

export const metadata: Metadata = { title: "Trading Bot", description: "Financial terminal dashboard" }

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ display: "flex", minHeight: "100vh", background: "var(--bg-base)" }}>
        <Providers>
          <DrawerProvider>
            <PermissionBanner />
            <Sidebar />
            <main className="app-main" style={{ flex: 1, marginLeft: 52, padding: "16px", overflowY: "auto", minHeight: "100vh" }}>
              {children}
            </main>
            <LazyDrawers />
            <AlertManager />
          </DrawerProvider>
        </Providers>
      </body>
    </html>
  )
}
