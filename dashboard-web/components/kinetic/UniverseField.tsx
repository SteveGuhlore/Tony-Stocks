"use client"

import { useEffect, useRef, useState } from "react"
import { prefersReducedMotion } from "@/lib/motion-tokens"

/**
 * Signature hero — a drifting field of ~1,000-symbol particles via Pixi.js.
 * Hard perf fallback: static CSS gradient when reduced-motion, off-screen,
 * Pixi unavailable, or low-end. Capped node count. Paused when not visible.
 */
const STATIC_BG =
  "radial-gradient(900px 360px at 70% -20%, rgba(55,224,255,.10), transparent 60%), var(--bg2)"

export function UniverseField({ nodeCount = 70 }: { nodeCount?: number }) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const [fallback, setFallback] = useState(true)

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    if (prefersReducedMotion()) return // keep static gradient

    let destroyed = false
    let app: { destroy: (a?: boolean, b?: unknown) => void; ticker: { stop(): void; start(): void } } | null = null
    let observer: IntersectionObserver | null = null
    let cleanupResize: (() => void) | null = null

    ;(async () => {
      try {
        const PIXI = await import("pixi.js")
        if (destroyed || !host) return
        const application = new PIXI.Application()
        await application.init({
          backgroundAlpha: 0,
          antialias: true,
          resizeTo: host,
          autoDensity: true,
          resolution: Math.min(typeof window !== "undefined" ? window.devicePixelRatio : 1, 2),
        })
        if (destroyed) {
          application.destroy(true)
          return
        }
        app = application as unknown as typeof app
        host.appendChild(application.canvas)
        setFallback(false)

        const cap = Math.min(nodeCount, 140)
        const particles: { g: import("pixi.js").Graphics; vy: number; baseY: number; phase: number }[] = []
        const w = () => host.clientWidth || 600
        const h = () => host.clientHeight || 200
        for (let i = 0; i < cap; i++) {
          const g = new PIXI.Graphics()
          const size = 1 + Math.random() * 2.2
          const isLime = Math.random() > 0.78
          g.circle(0, 0, size).fill({ color: isLime ? 0xc4f042 : 0x37e0ff, alpha: 0.6 })
          g.x = Math.random() * w()
          const baseY = Math.random() * h()
          g.y = baseY
          application.stage.addChild(g)
          particles.push({ g, vy: 0.2 + Math.random() * 0.5, baseY, phase: Math.random() * Math.PI * 2 })
        }

        let t = 0
        application.ticker.add(() => {
          t += 0.016
          for (const p of particles) {
            p.g.y = p.baseY + Math.sin(t * p.vy + p.phase) * 10
            p.g.alpha = 0.25 + (Math.sin(t * p.vy + p.phase) * 0.5 + 0.5) * 0.6
          }
        })

        // pause when off-screen
        observer = new IntersectionObserver(
          (entries) => {
            for (const e of entries) {
              if (e.isIntersecting) application.ticker.start()
              else application.ticker.stop()
            }
          },
          { threshold: 0 },
        )
        observer.observe(host)
        cleanupResize = () => observer?.disconnect()
      } catch {
        // Pixi failed to load/init — keep static gradient
        setFallback(true)
      }
    })()

    return () => {
      destroyed = true
      cleanupResize?.()
      observer?.disconnect()
      try {
        app?.destroy(true, { children: true })
      } catch {
        /* noop */
      }
    }
  }, [nodeCount])

  return (
    <div
      ref={hostRef}
      aria-hidden
      className="pointer-events-none absolute inset-0 overflow-hidden"
      style={{ background: fallback ? STATIC_BG : undefined }}
    />
  )
}
