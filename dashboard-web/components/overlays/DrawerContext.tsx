"use client"
import React, { createContext, useContext, useState, useCallback } from "react"

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
  const openSymbol = useCallback((sym: string) => setSymbolDrawer(sym.toUpperCase()), [])
  const closeSymbol = useCallback(() => setSymbolDrawer(null), [])
  const openNotif = useCallback(() => setNotifDrawerOpen(true), [])
  const closeNotif = useCallback(() => setNotifDrawerOpen(false), [])
  return (
    <Ctx.Provider value={{ symbolDrawer, notifDrawerOpen, openSymbol, closeSymbol, openNotif, closeNotif }}>
      {children}
    </Ctx.Provider>
  )
}

export const useDrawer = () => useContext(Ctx)
