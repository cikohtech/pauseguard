// The queue's optional new-case sound (off by default; the choice is remembered per browser).
const KEY = 'pauseguard.console.sound'

export function soundPreference(): boolean {
  try {
    return localStorage.getItem(KEY) === 'on'
  } catch {
    return false
  }
}

export function saveSoundPreference(on: boolean) {
  try {
    localStorage.setItem(KEY, on ? 'on' : 'off')
  } catch {
    // private mode: the toggle still works for this visit
  }
}

let ctx: AudioContext | null = null

/** Two soft notes (a gentle "new item", not an alarm). */
export function chime() {
  try {
    ctx ??= new AudioContext()
    const t = ctx.currentTime
    for (const [i, freq] of [660, 880].entries()) {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'sine'
      osc.frequency.value = freq
      const start = t + i * 0.14
      gain.gain.setValueAtTime(0.0001, start)
      gain.gain.exponentialRampToValueAtTime(0.12, start + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.3)
      osc.connect(gain).connect(ctx.destination)
      osc.start(start)
      osc.stop(start + 0.32)
    }
  } catch {
    // no audio (autoplay policy, old browser): the visual highlight is enough
  }
}
