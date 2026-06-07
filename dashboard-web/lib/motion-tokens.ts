/**
 * Kinetic Tape motion tokens (ported from 08-kinetic-system.html §03).
 * Transform/opacity only. Press = scale(.96). Stagger rows 40ms.
 * Everything must respect prefers-reduced-motion.
 */

export const duration = {
  instant: 0.08,
  fast: 0.18,
  normal: 0.35,
  slow: 0.6,
} as const

export const easing = {
  smooth: [0.22, 1, 0.36, 1] as const, // enter
  sharp: [0.4, 0, 0.2, 1] as const, // state change
  out: [0.23, 1, 0.32, 1] as const,
  drawer: [0.32, 0.72, 0, 1] as const,
}

/** "spring · alive" preset from the design system. */
export const spring = { type: "spring" as const, stiffness: 400, damping: 10 }

/** Row enter — staggered 40ms, transform+opacity only. */
export const rowEnter = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: duration.normal, ease: easing.smooth },
}

export const STAGGER_MS = 40

/** Press feedback shared by all buttons. */
export const press = { scale: 0.96 }

/** Detect reduced-motion preference (SSR-safe). */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches
}
