export function playBeep(type: "near_entry" | "stop_violation"): void {
  if (typeof window === "undefined") return
  try {
    const ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)()
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.connect(gain)
    gain.connect(ctx.destination)
    if (type === "near_entry") {
      osc.frequency.value = 880
      gain.gain.value = 0.3
      osc.start()
      osc.stop(ctx.currentTime + 0.2)
    } else {
      osc.frequency.value = 330
      gain.gain.value = 0.4
      osc.start()
      osc.stop(ctx.currentTime + 0.4)
    }
    osc.onended = () => ctx.close()
  } catch {
    // AudioContext unavailable (SSR or restricted env) — silently skip
  }
}
