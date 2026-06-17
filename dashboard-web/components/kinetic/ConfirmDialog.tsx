"use client"

import { AnimatePresence, motion } from "motion/react"
import { useEffect, useState } from "react"
import { Button } from "./Button"
import { duration } from "@/lib/motion-tokens"

export interface ConfirmSpec {
  title: string
  body: string
  confirmLabel: string
  danger?: boolean
  /** require typed PIN for dangerous money-adjacent actions */
  requirePin?: boolean
  /** Called on confirm with the typed PIN (empty string when none was required).
   * May be async; the dialog closes immediately after invoking it. */
  onConfirm: (pin: string) => void | Promise<void>
}

export function ConfirmDialog({ spec, onClose }: { spec: ConfirmSpec | null; onClose: () => void }) {
  const [pin, setPin] = useState("")
  useEffect(() => {
    if (spec) setPin("")
  }, [spec])
  const pinOk = !spec?.requirePin || pin.trim().length >= 4
  return (
    <AnimatePresence>
      {spec && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: duration.fast }}
          className="fixed inset-0 z-[70] grid place-items-center"
          style={{ background: "rgba(0,0,0,.5)" }}
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.96, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.96, opacity: 0 }}
            transition={{ duration: duration.fast }}
            role="alertdialog"
            aria-label={spec.title}
            onClick={(e) => e.stopPropagation()}
            className="kt-panel"
            style={{ padding: 20, width: 380, maxWidth: "92vw" }}
          >
            <h3 style={{ fontSize: 18, marginBottom: 8 }}>{spec.title}</h3>
            <p className="text-mut" style={{ fontSize: 12, lineHeight: 1.5, marginBottom: 16 }}>
              {spec.body}
            </p>
            {spec.requirePin && (
              <input
                value={pin}
                onChange={(e) => setPin(e.target.value)}
                type="password"
                inputMode="numeric"
                placeholder="Enter PIN to confirm"
                aria-label="Confirmation PIN"
                className="num"
                style={{
                  width: "100%",
                  background: "rgba(255,255,255,.04)",
                  border: "1px solid var(--line)",
                  borderRadius: 8,
                  color: "var(--ink)",
                  padding: "8px 12px",
                  fontSize: 13,
                  marginBottom: 16,
                  outline: "none",
                }}
              />
            )}
            <div className="flex gap-2 justify-end">
              <Button onClick={onClose}>Cancel</Button>
              <Button
                variant={spec.danger ? "danger" : "primary"}
                disabled={!pinOk}
                style={{ opacity: pinOk ? 1 : 0.5 }}
                onClick={() => {
                  void spec.onConfirm(pin)
                  onClose()
                }}
              >
                {spec.confirmLabel}
              </Button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
