import { useEffect, useState } from 'react'
import ChatDrawer from '@/components/ChatDrawer'
import Dialogs, { resolveCode } from '@/components/Dialogs'
import Hud from '@/components/Hud'
import LabScene from '@/components/LabScene'
import SidePanel from '@/components/SidePanel'
import { useLang, useT } from '@/lib/i18n'
import { connectRealtime, useLab } from '@/store'

export default function App() {
  const init = useLab((s) => s.init)
  const loaded = useLab((s) => !!s.lab)
  const [error, setError] = useState<string | null>(null)
  const t = useT()
  const lang = useLang((s) => s.lang)

  useEffect(() => {
    document.documentElement.lang = lang
    const s = useLab.getState()
    if (s.lab) {
      s.refreshLab()
      s.refreshQuests()
    }
  }, [lang])

  useEffect(() => {
    init()
      .then(() => {
        const code = new URLSearchParams(location.search).get('scan')
        if (code) {
          resolveCode(code)
          history.replaceState(null, '', location.pathname)
        }
      })
      .catch((e) => setError(String(e.message ?? e)))
    return connectRealtime()
  }, [init])

  return (
    <div className="relative h-full w-full overflow-hidden bg-[radial-gradient(ellipse_at_center,#14191C_0%,#080B0D_75%)]">
      <LabScene />
      {/* The 3D canvas stays full-bleed; the HUD is inset so it clears notches and the home indicator. */}
      <div className="hud-safe pointer-events-none absolute inset-0">
        <Hud />
        <ChatDrawer />
        <SidePanel />
      </div>
      <Dialogs />
      {!loaded && (
        <div className="absolute inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-canvas-edge">
          <div className="h-1 w-48 overflow-hidden rounded-full bg-white/10"><div className="h-full w-1/3 animate-pulse bg-accent" /></div>
          <p className="text-sm text-dim">{error ? t('app.apiError', { error }) : t('app.loading')}</p>
        </div>
      )}
    </div>
  )
}
