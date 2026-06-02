"use client"
import React, { createContext, useContext, useState, useCallback, useRef } from "react"

interface DrawerState {
  symbolDrawer: string | null
  notifDrawerOpen: boolean
  openSymbol: (sym: string) => void
  closeSymbol: () => void
  openNotif: () => void
  closeNotif: () => void
}

const Ctx = createContext<DrawerState>({
  symbolDrawer: null, notifDrawerOpen: false,
  openSymbol: () => {}, closeSymbol: () => {}, openNotif: () => {}, closeNotif: () => {},
})

export function DrawerProvider({ children }: { children: React.ReactNode }) {
  const [symbolDrawer, setSymbolDrawer] = useState<string | null>(null)
  const [notifDrawerOpen, setNotifDrawerOpen] = useState(false)
  const symbolTriggerRef = useRef<HTMLElement | null>(null)
  const notifTriggerRef = useRef<HTMLElement | null>(null)

  const openSymbol = useCallback((sym: string) => {
    symbolTriggerRef.current = (document.activeElement as HTMLElement | null) ?? null
    setSymbolDrawer(sym.toUpperCase())
  }, [])
  const closeSymbol = useCallback(() => {
    setSymbolDrawer(null)
    const t = symbolTriggerRef.current
    if (t) queueMicrotask(() => t.focus?.())
  }, [])
  const openNotif = useCallback(() => {
    notifTriggerRef.current = (document.activeElement as HTMLElement | null) ?? null
    setNotifDrawerOpen(true)
  }, [])
  const closeNotif = useCallback(() => {
    setNotifDrawerOpen(false)
    const t = notifTriggerRef.current
    if (t) queueMicrotask(() => t.focus?.())
  }, [])

  return (
    <Ctx.Provider value={{ symbolDrawer, notifDrawerOpen, openSymbol, closeSymbol, openNotif, closeNotif }}>
      {children}
    </Ctx.Provider>
  )
}

export const useDrawer = () => useContext(Ctx)
