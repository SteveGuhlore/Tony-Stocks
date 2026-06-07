"use client"

import { motion, type HTMLMotionProps } from "motion/react"
import { forwardRef } from "react"
import { duration, easing } from "@/lib/motion-tokens"

type Variant = "default" | "primary" | "danger"

export interface ButtonProps extends Omit<HTMLMotionProps<"button">, "ref"> {
  variant?: Variant
}

/** Kinetic button — press = scale(.96) "it heard me" feedback. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "default", className = "", children, ...rest },
  ref,
) {
  return (
    <motion.button
      ref={ref}
      whileTap={{ scale: 0.96 }}
      transition={{ duration: duration.fast, ease: easing.out }}
      className={`kt-btn ${variant !== "default" ? variant : ""} ${className}`}
      {...rest}
    >
      {children}
    </motion.button>
  )
})
