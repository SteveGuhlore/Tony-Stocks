"use client"
import { useRef } from "react"
import dynamic from "next/dynamic"
import { useDrawer } from "./DrawerContext"

const SymbolDrawer = dynamic(
  () => import("./SymbolDrawer").then((m) => m.SymbolDrawer),
  { ssr: false },
)
const NotificationDrawer = dynamic(
  () => import("./NotificationDrawer").then((m) => m.NotificationDrawer),
  { ssr: false },
)

export function LazyDrawers() {
  const { symbolDrawer, notifDrawerOpen } = useDrawer()
  const symbolEverOpened = useRef(false)
  const notifEverOpened = useRef(false)
  if (symbolDrawer) symbolEverOpened.current = true
  if (notifDrawerOpen) notifEverOpened.current = true
  return (
    <>
      {symbolEverOpened.current ? <SymbolDrawer /> : null}
      {notifEverOpened.current ? <NotificationDrawer /> : null}
    </>
  )
}
