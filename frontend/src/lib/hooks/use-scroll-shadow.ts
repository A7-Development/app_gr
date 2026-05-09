// frontend/src/lib/hooks/use-scroll-shadow.ts
//
// useScrollShadow — detecta scroll dentro de um container interno (overflow-y-auto)
// e retorna um boolean `scrolled` para aplicar sombra/visual de "conteudo passando
// por baixo". Padrao canonico A1b — usado pela toolbar unificada do
// DashboardBiPadrao para sinalizar fixed-chrome durante scroll.
//
// USO:
//   const [scrollRef, scrolled] = useScrollShadow<HTMLDivElement>()
//   // ...
//   <div className={cx("sticky ...", scrolled && "shadow-sm", "transition-shadow")}>
//     ...toolbar...
//   </div>
//   <div ref={scrollRef} className="flex-1 overflow-y-auto">
//     ...conteudo scrollavel...
//   </div>
//
// Para sticky elements em scroll de PAGINA (window.scroll), prefira o padrao
// IntersectionObserver+sentinel ja inline em <FilterBar /> — mecanica diferente.

"use client"

import { useEffect, useRef, useState } from "react"

export function useScrollShadow<T extends HTMLElement = HTMLDivElement>() {
  const [scrolled, setScrolled] = useState(false)
  const ref = useRef<T>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const handler = () => setScrolled(el.scrollTop > 0)
    handler()
    el.addEventListener("scroll", handler, { passive: true })
    return () => el.removeEventListener("scroll", handler)
  }, [])

  return [ref, scrolled] as const
}
