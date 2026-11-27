import {
  Bell, Check, CheckCheck, ChevronDown, ClipboardList, FlaskConical, Layers, LayoutDashboard, MessageSquare, Minus, Plus, QrCode,
  RotateCcw, RotateCw, Search, Settings2, Sparkles, TriangleAlert, Undo2, X,
} from 'lucide-react'
import { useState } from 'react'
import { StatusDot } from '@/components/LabScene'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Switch } from '@/components/ui/switch'
import { api } from '@/lib/api'
import { tx, useLang, useT, type TKey } from '@/lib/i18n'
import { cn, fmtDate, fmtTime } from '@/lib/utils'
import { useLab } from '@/store'
import type { AppNotification, Layer } from '@/types'

export const roleLabel = (r: string) => tx(`role.${r}`, r)

export function Avatar({ initials, online, className }: { initials: string; online?: boolean; className?: string }) {
  return (
    <span className={cn('relative inline-flex size-8 shrink-0 items-center justify-center rounded-full border border-line-strong bg-elev font-mono text-[11px] font-semibold text-fg', className)}>
      {initials}
      {online !== undefined && (
        <span className={cn('absolute -bottom-0.5 -right-0.5 size-2.5 rounded-full border-2 border-surface', online ? 'bg-accent' : 'bg-muted')} />
      )}
    </span>
  )
}

function LanguageSwitch() {
  const { lang, setLang } = useLang()
  const t = useT()
  return (
    <div role="group" aria-label={t('header.language')} className="flex h-12 items-center rounded-full border border-line-strong bg-surface p-1">
      {(['pl', 'en'] as const).map((l) => (
        <button key={l} onClick={() => setLang(l)} aria-pressed={lang === l}
          className={cn('h-full cursor-pointer rounded-full px-2.5 font-mono text-[11px] font-semibold uppercase transition-colors',
            lang === l ? 'bg-accent text-accent-ink' : 'text-dim hover:text-fg')}>
          {l}
        </button>
      ))}
    </div>
  )
}

function NotificationsMenu() {
  const s = useLab()
  const t = useT()
  const unread = s.notifications.filter((n) => !n.read).length
  const open = async (n: AppNotification) => {
    if (!n.read) await api.post(`/notifications/${n.id}/read`, {})
    s.loadNotifications()
    if (n.ref_type === 'equipment' && n.ref_id) s.focus(n.ref_id, true)
    else if (n.ref_type === 'material' && n.ref_id) s.set({ materialId: n.ref_id })
    else if (n.ref_type === 'sample' && n.ref_id) s.set({ sampleId: n.ref_id })
    else if (n.ref_type === 'quest') s.set({ sideOpen: true, sideTab: 'quests' })
    else if (n.ref_type === 'channel' && n.ref_id) {
      s.set({ chatOpen: true })
      s.openChannel(n.ref_id)
    } else if (n.ref_type === 'incident') s.set(s.me()?.access === 'worker' ? { layer: 'safety' } : { adminOpen: true })
  }
  const readAll = async () => {
    await api.post(`/notifications/read-all?user_id=${s.meId}`, {})
    s.loadNotifications()
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="relative flex size-12 cursor-pointer items-center justify-center rounded-full border border-line-strong bg-surface text-fg outline-none hover:bg-hover" aria-label={t('notif.title')}>
          <Bell className="size-5" />
          {unread > 0 && (
            <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full border-2 border-canvas-edge bg-accent px-1.5 font-mono text-[11px] font-bold text-accent-ink">{unread}</span>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-[min(360px,92vw)]">
        <div className="flex items-center justify-between px-2.5 pb-1">
          <DropdownMenuLabel className="px-0">{t('notif.title')}</DropdownMenuLabel>
          {unread > 0 && (
            <button onClick={readAll} className="flex cursor-pointer items-center gap-1 text-[11px] text-accent hover:underline"><CheckCheck className="size-3.5" />{t('notif.readAll')}</button>
          )}
        </div>
        <div className="max-h-[60vh] overflow-y-auto">
          {s.notifications.length === 0 && <p className="px-2.5 py-6 text-center text-xs text-muted">{t('notif.empty')}</p>}
          {s.notifications.slice(0, 30).map((n) => (
            <DropdownMenuItem key={n.id} onSelect={() => open(n)} className="items-start">
              <span className={cn('mt-1.5 size-2 shrink-0 rounded-full', n.read ? 'bg-transparent' : 'bg-accent')} />
              <div className="min-w-0 flex-1">
                <p className={cn('text-[13px] leading-snug', !n.read && 'font-medium')}>{n.title}</p>
                {n.body && <p className="line-clamp-2 text-xs text-dim">{n.body}</p>}
                <p className="mt-0.5 font-mono text-[10px] text-muted">{fmtDate(n.at)} {fmtTime(n.at)}</p>
              </div>
            </DropdownMenuItem>
          ))}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function Header() {
  const s = useLab()
  const t = useT()
  const me = s.me()
  const unread = Object.values(s.unread).reduce((a, b) => a + b, 0)
  const lab = s.lab
  const openQuests = s.quests ? s.quests.mine.length : 0

  return (
    <header className="pointer-events-none absolute inset-x-0 top-0 z-20 flex items-start justify-between gap-3 p-3 sm:p-4">
      <div className="pointer-events-auto flex items-center gap-2">
        <div className="hidden h-12 items-center gap-2 rounded-full border border-line bg-surface/90 px-4 backdrop-blur md:flex">
          <FlaskConical className="size-5 text-accent" />
          <span className="font-display text-sm font-bold tracking-wide">SMARTLAB</span>
        </div>
        <button
          onClick={() => s.set({ chatOpen: !s.chatOpen })}
          className={cn(
            'relative flex size-12 cursor-pointer items-center justify-center rounded-full border transition-colors',
            s.chatOpen ? 'border-accent bg-accent text-accent-ink' : 'border-line-strong bg-surface text-fg hover:bg-hover',
          )}
          aria-label={t('header.chat')}
        >
          <MessageSquare className="size-[22px]" />
          {unread > 0 && (
            <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full border-2 border-canvas-edge bg-accent px-1.5 font-mono text-[11px] font-bold text-accent-ink">
              {unread}
            </span>
          )}
        </button>
        <NotificationsMenu />
      </div>

      <div className="pointer-events-auto flex min-w-0 flex-col items-center">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="group flex max-w-full cursor-pointer items-center gap-2.5 rounded-xl border border-transparent px-3 py-1.5 outline-none transition-colors hover:border-line hover:bg-elev/80 data-[state=open]:border-line data-[state=open]:bg-elev/80">
              <StatusDot status={lab && s.labs.find((l) => l.id === lab.id)?.alerts ? 'alert' : 'ok'} />
              <h1 className="truncate text-lg font-semibold sm:text-xl">{lab?.name ?? t('common.loading')}</h1>
              <ChevronDown className="size-4 text-dim transition-transform duration-200 group-data-[state=open]:rotate-180" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-[320px]" align="center">
            <DropdownMenuLabel>{t('header.selectLab')}</DropdownMenuLabel>
            {s.labs.map((l) => (
              <DropdownMenuItem key={l.id} onSelect={() => s.selectLab(l.id)} className={cn(l.id === s.labId && 'bg-accent/10')}>
                <div className="flex-1">
                  <div className="font-medium">{l.name}</div>
                  <div className="text-xs text-dim">{l.building}</div>
                </div>
                {l.alerts ? (
                  <span className="flex items-center gap-1.5 font-mono text-xs text-accent"><StatusDot status="alert" className="size-2" />{l.alerts}</span>
                ) : (
                  <span className="flex items-center gap-1.5 font-mono text-xs text-dim"><StatusDot status="ok" className="size-2" />OK</span>
                )}
                {l.id === s.labId && <Check className="size-4 text-accent" />}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        {lab && (
          <p className="hidden text-xs text-dim sm:block">
            {lab.building ? `${lab.building} · ` : ''}{t('header.manager')}: {lab.manager} ·{' '}
            {(() => {
              const n = lab.equipment.filter((e) => e.status === 'alert').length
              return <span className={n ? 'text-accent' : ''}>{t('header.alertsActive', { n })}</span>
            })()}
          </p>
        )}
      </div>

      <div className="pointer-events-auto flex items-center gap-2">
        <LanguageSwitch />
        <Button variant="outline" size="icon" className="hidden sm:inline-flex" onClick={() => s.set({ scanOpen: true })} aria-label={t('header.scan')}>
          <QrCode className="size-5!" />
        </Button>
        <Button variant="outline" size="icon" className="hidden sm:inline-flex" onClick={() => s.set({ reportFor: null })} aria-label={t('header.report')}>
          <TriangleAlert className="size-5!" />
        </Button>
        {me && me.access !== 'worker' && (
          <Button variant="outline" size="icon" onClick={() => s.set({ adminOpen: true })} aria-label={t('header.admin')}>
            <LayoutDashboard className="size-5!" />
          </Button>
        )}
        <button
          onClick={() => s.set({ sideOpen: !s.sideOpen })}
          className={cn(
            'relative flex size-12 cursor-pointer items-center justify-center rounded-full border transition-colors',
            s.sideOpen ? 'border-accent bg-accent text-accent-ink' : 'border-line-strong bg-surface text-fg hover:bg-hover',
          )}
          aria-label={t('header.quests')}
        >
          <ClipboardList className="size-5" />
          {openQuests > 0 && !s.sideOpen && (
            <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full border-2 border-canvas-edge bg-fg px-1.5 font-mono text-[11px] font-bold text-canvas">
              {openQuests}
            </span>
          )}
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button className="flex h-12 cursor-pointer items-center gap-2 rounded-full border border-line-strong bg-surface pl-1.5 pr-3 outline-none hover:bg-hover">
              {me && <Avatar initials={me.initials} />}
              <Settings2 className="size-4 text-dim" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-72">
            <DropdownMenuLabel>{t('header.signedInAs')}</DropdownMenuLabel>
            {s.users.map((u) => (
              <DropdownMenuItem key={u.id} onSelect={() => s.setMe(u.id)}>
                <Avatar initials={u.initials} online={!!u.online} className="size-7" />
                <div className="flex-1">
                  <div className="text-sm">{u.name}</div>
                  <div className="text-xs text-dim">{roleLabel(u.role)} · {t(`access.${u.access}` as TKey)}</div>
                </div>
                {u.id === s.meId && <Check className="size-4 text-accent" />}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={(e) => { e.preventDefault(); s.set({ showLabels: !s.showLabels }) }}>
              <span className="flex-1">{t('header.showLabels')}</span>
              <Switch checked={s.showLabels} />
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => s.camera({ type: 'reset' })}><Undo2 /> {t('header.resetView')}</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => s.set({ scanOpen: true })} className="sm:hidden"><QrCode /> {t('header.scanOrId')}</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => s.set({ reportFor: null })} className="sm:hidden"><TriangleAlert /> {t('header.report')}</DropdownMenuItem>
            <DropdownMenuItem onSelect={() => s.set({ onboardingOpen: true })}><Sparkles /> {t('header.onboarding')}</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}

const LAYERS: Layer[] = ['infra', 'inventory', 'safety', 'social', 'quests']

function Legend() {
  const { lab, layer, set, chatOpen } = useLab()
  const t = useT()
  if (!lab) return null
  const count = (st: string) => lab.equipment.filter((e) => e.status === st && e.kind !== 'bench').length
  return (
    <div className={cn('pointer-events-auto absolute bottom-4 left-4 z-20 w-56 space-y-3 rounded-2xl border border-line bg-surface/90 p-3.5 backdrop-blur transition-[left]', chatOpen && 'max-sm:hidden sm:left-[396px]')}>
      <div>
        <div className="mb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-dim"><Layers className="size-3.5" /> {t('layer.title')}</div>
        <div className="flex flex-wrap gap-1">
          {LAYERS.map((l) => (
            <button key={l} onClick={() => set({ layer: l })}
              className={cn('cursor-pointer rounded-md border px-2 py-1 text-xs transition-colors',
                layer === l ? 'border-accent/60 bg-accent/10 text-accent' : 'border-line text-dim hover:text-fg')}>
              {t(`layer.${l}`)}
            </button>
          ))}
        </div>
      </div>
      <div className="space-y-1.5 border-t border-line pt-3 text-xs">
        {(['ok', 'maint', 'alert'] as const).map((st) => (
          <div key={st} className="flex items-center gap-2">
            <StatusDot status={st} />
            <span className="flex-1 text-dim">{t(`status.${st}`)}</span>
            <span className="font-mono text-fg">{count(st)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function ViewportControls() {
  const { camera, route, set, sideOpen } = useLab()
  const t = useT()
  const btn = 'size-10 cursor-pointer flex items-center justify-center rounded-xl text-dim hover:bg-hover hover:text-fg'
  return (
    <div className={cn('pointer-events-auto absolute bottom-4 right-4 z-20 flex flex-col items-end gap-2 transition-[right]', sideOpen && 'max-sm:hidden sm:right-[416px]')}>
      {route && (
        <div className="flex items-center gap-3 rounded-xl border border-accent/40 bg-surface/95 px-3 py-2 text-xs backdrop-blur">
          <span className="text-dim">{t('route.label')}</span>
          <span className="font-mono text-accent">{t('route.summary', { stops: route.order.length, m: route.distance_m, min: route.minutes })}</span>
          <button onClick={() => set({ route: null })} className="cursor-pointer text-dim hover:text-fg"><X className="size-3.5" /></button>
        </div>
      )}
      <div className="flex gap-0.5 rounded-2xl border border-line bg-surface/90 p-1 backdrop-blur">
        <button className={btn} onClick={() => camera({ type: 'rotate', value: -Math.PI / 4 })} aria-label={t('view.rotateLeft')}><RotateCcw className="size-4" /></button>
        <button className={btn} onClick={() => camera({ type: 'rotate', value: Math.PI / 4 })} aria-label={t('view.rotateRight')}><RotateCw className="size-4" /></button>
        <button className={btn} onClick={() => camera({ type: 'zoom', value: 1.22 })} aria-label={t('view.zoomOut')}><Minus className="size-4" /></button>
        <button className={btn} onClick={() => camera({ type: 'zoom', value: 0.82 })} aria-label={t('view.zoomIn')}><Plus className="size-4" /></button>
      </div>
    </div>
  )
}

function Assistant() {
  const { lab, focus, set, chatOpen, sideOpen } = useLab()
  const t = useT()
  const [q, setQ] = useState('')
  const [answer, setAnswer] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const ask = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!q.trim() || !lab) return
    setBusy(true)
    try {
      const r = await api.post<{ answer: string; highlight: string | null; material?: string; point?: string }>(
        '/assistant', { lab_id: lab.id, question: q })
      setAnswer(r.answer)
      if (r.highlight) focus(r.highlight)
      if (r.point) set({ layer: 'safety' })
      if (r.material) set({ layer: 'inventory' })
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className={cn('pointer-events-auto absolute bottom-4 left-1/2 z-20 w-[min(440px,calc(100vw-2rem))] -translate-x-1/2 max-md:bottom-24', (chatOpen || sideOpen) && 'max-lg:hidden', sideOpen && !chatOpen && 'lg:left-[calc(50%-200px)]', chatOpen && !sideOpen && 'lg:left-[calc(50%+190px)]', chatOpen && sideOpen && 'max-2xl:hidden')}>
      {answer && (
        <div className="mb-2 flex items-start gap-2 rounded-xl border border-line bg-surface/95 p-3 text-sm backdrop-blur">
          <Sparkles className="mt-0.5 size-4 shrink-0 text-accent" />
          <p className="flex-1">{answer}</p>
          <button onClick={() => setAnswer(null)} className="cursor-pointer text-dim hover:text-fg"><X className="size-4" /></button>
        </div>
      )}
      <form onSubmit={ask} className="flex items-center gap-2 rounded-full border border-line-strong bg-surface/95 py-1.5 pl-4 pr-1.5 backdrop-blur">
        <Search className="size-4 text-dim" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t('assistant.placeholder')}
          className="flex-1 bg-transparent text-sm placeholder:text-muted focus:outline-none" />
        <Button type="submit" size="sm" className="rounded-full" disabled={busy}>{t('common.ask')}</Button>
      </form>
    </div>
  )
}

function Toasts() {
  const toasts = useLab((s) => s.toasts)
  return (
    <div className="pointer-events-none absolute left-1/2 top-24 z-[60] flex w-[min(420px,92vw)] -translate-x-1/2 flex-col gap-2">
      {toasts.map((t) => (
        <div key={t.id} className={cn('rounded-xl border bg-surface/95 px-4 py-2.5 text-sm shadow-xl backdrop-blur', t.tone === 'accent' ? 'border-accent/50' : 'border-line')}>
          {t.text}
        </div>
      ))}
    </div>
  )
}

export default function Hud() {
  return (
    <>
      <Header />
      <Legend />
      <ViewportControls />
      <Assistant />
      <Toasts />
    </>
  )
}
