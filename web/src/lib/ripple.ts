// The Material ripple: one delegated listener for the whole page. A press on any `.ripple` element
// grows a circle from the pointer (index.css, .ripple-wave) and fades it out on release. The
// spans are decoration only (empty, aria-hidden) and remove themselves.

export function installRipple(doc: Document = document): () => void {
  const reduce = doc.defaultView?.matchMedia?.('(prefers-reduced-motion: reduce)')

  const onDown = (e: PointerEvent) => {
    if (reduce?.matches || e.button !== 0) return
    const host = (e.target as Element | null)?.closest?.<HTMLElement>('.ripple')
    if (!host || host.matches(':disabled, [aria-disabled="true"]')) return
    const rect = host.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    // big enough to reach the farthest corner from the press point
    const r = Math.hypot(Math.max(x, rect.width - x), Math.max(y, rect.height - y))
    const wave = doc.createElement('span')
    wave.className = 'ripple-wave'
    wave.setAttribute('aria-hidden', 'true')
    wave.style.cssText = `width:${r * 2}px;height:${r * 2}px;left:${x - r}px;top:${y - r}px`
    host.appendChild(wave)

    const release = () => {
      doc.removeEventListener('pointerup', release)
      doc.removeEventListener('pointercancel', release)
      // let the wave finish growing before it fades, so a quick tap still shows it
      setTimeout(() => {
        wave.classList.add('ripple-out')
        setTimeout(() => wave.remove(), 400)
      }, 180)
    }
    doc.addEventListener('pointerup', release)
    doc.addEventListener('pointercancel', release)
  }

  doc.addEventListener('pointerdown', onDown, { passive: true })
  return () => doc.removeEventListener('pointerdown', onDown)
}
