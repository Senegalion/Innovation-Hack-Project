import {
  Award, BookOpen, Check, ChevronRight, Clock, Crosshair, FlaskConical, Leaf, MapPin, Navigation, Package, Plus,
  Shield, Sparkles, Users, X,
} from 'lucide-react'
import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input, Select } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/lib/api'
import { locale, t as tr, tx, useT } from '@/lib/i18n'
import { cn, daysUntil, fmtDate } from '@/lib/utils'
import { useLab } from '@/store'
import type { Material, Quest, Route } from '@/types'

function dueLabel(iso: string | null) {
  const d = daysUntil(iso)
  if (d === null) return null
  if (d < 0) return tr('due.overdue', { n: -d })
  if (d === 0) return tr('due.today')
  if (d === 1) return tr('due.tomorrow')
  return tr('due.in', { n: d })
}

function QuestCard({ q, kind }: { q: Quest; kind: 'mine' | 'pool' | 'done' }) {
  const s = useLab()
  const t = useT()
  const [mode, setMode] = useState<null | 'reject' | 'escalate'>(null)
  const [reason, setReason] = useState('')
  const act = async (action: string, r = '') => {
    const res = await api.post<{ xp: number }>(`/quests/${q.id}/action`, { user_id: s.meId, action, reason: r })
    if (action === 'complete') {
      s.toast(t('quest.completed', { xp: res.xp }))
      s.refreshUsers()
    }
    if (action === 'escalate') s.toast(t('quest.escalated'))
    setMode(null)
    s.refreshQuests()
  }
  const hi = q.priority === 'high' || q.priority === 'critical'
  return (
    <div className={cn('rounded-xl border bg-elev/60 p-3', hi && kind !== 'done' ? 'border-accent/35' : 'border-line', kind === 'done' && 'opacity-60')}>
      <div className="flex items-start gap-2.5">
        {kind === 'mine' ? (
          <button onClick={() => act('complete')} aria-label={t('quest.complete')}
            className="mt-0.5 flex size-5 shrink-0 cursor-pointer items-center justify-center rounded-md border border-fg/70 hover:border-accent hover:bg-accent/20" />
        ) : kind === 'done' ? (
          <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-md bg-accent text-accent-ink"><Check className="size-3.5" /></span>
        ) : null}
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <p className={cn('text-[13.5px] font-medium leading-snug', kind === 'done' && 'line-through')}>{q.title}</p>
            <span className="shrink-0 font-mono text-xs font-semibold text-accent">+{q.xp} XP</span>
          </div>
          {q.description && kind !== 'done' && <p className="mt-1 text-xs leading-relaxed text-dim">{q.description}</p>}
          {q.reason && kind === 'pool' && <p className="mt-1 text-[11px] text-accent">{t('quest.suggested', { reason: q.reason })}</p>}
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11px] text-dim">
            <Badge variant={q.source === 'leader' || q.source === 'social' ? 'default' : 'accent'}>{t(`source.${q.source}`)}</Badge>
            {q.category !== 'daily' && <Badge>{t(`category.${q.category}`)}</Badge>}
            {hi && <Badge variant="accent">{t(`priority.${q.priority}`)}</Badge>}
            {q.location && (
              <button onClick={() => q.target_id && s.focus(q.target_id)} className="flex cursor-pointer items-center gap-0.5 hover:text-fg">
                <MapPin className="size-3" />{q.location}
              </button>
            )}
            <span className="flex items-center gap-0.5 font-mono"><Clock className="size-3" />{q.minutes}m</span>
            {q.due && <span className="font-mono">· {dueLabel(q.due)}</span>}
          </div>
        </div>
      </div>
      {kind !== 'done' && !mode && (
        <div className="mt-2.5 flex flex-wrap gap-1.5 pl-0">
          {kind === 'pool' ? (
            <>
              <Button size="sm" onClick={() => act('accept')}>{t('quest.accept')}</Button>
              <Button size="sm" variant="subtle" onClick={() => setMode('reject')}>{t('quest.reject')}</Button>
              <Button size="sm" variant="ghost" onClick={() => act('snooze')}>{t('quest.later')}</Button>
            </>
          ) : (
            <>
              <Button size="sm" onClick={() => act('complete')}><Check /> {t('quest.done')}</Button>
              <Button size="sm" variant="ghost" onClick={() => act('unassign')}>{t('quest.giveBack')}</Button>
              <Button size="sm" variant="ghost" onClick={() => setMode('escalate')}>{t('quest.escalate')}</Button>
            </>
          )}
        </div>
      )}
      {mode && (
        <form className="mt-2.5 flex gap-1.5" onSubmit={(e) => { e.preventDefault(); act(mode, reason) }}>
          <Input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} className="h-8 text-xs"
            placeholder={mode === 'reject' ? t('quest.rejectWhy') : t('quest.problemWhat')} />
          <Button size="sm" type="submit">{mode === 'reject' ? t('quest.reject') : t('common.send')}</Button>
          <Button size="sm" variant="ghost" type="button" onClick={() => setMode(null)}><X /></Button>
        </form>
      )}
    </div>
  )
}

function CreateQuest() {
  const s = useLab()
  const t = useT()
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [target, setTarget] = useState('')
  const [assignee, setAssignee] = useState('')
  const [category, setCategory] = useState('daily')
  const [xp, setXp] = useState(20)
  if (!open) return <Button variant="outline" size="sm" className="w-full border-dashed" onClick={() => setOpen(true)}><Plus /> {t('quest.create')}</Button>
  return (
    <form className="space-y-2 rounded-xl border border-line bg-elev/60 p-3" onSubmit={async (e) => {
      e.preventDefault()
      if (!title.trim()) return
      await api.post('/quests', { lab_id: s.labId, title, created_by: s.meId, category, xp, target_id: target || null, assignee_id: assignee || null })
      setTitle(''); setOpen(false)
      s.toast(t('quest.published'))
      s.refreshQuests()
    }}>
      <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={t('quest.title')} autoFocus />
      <div className="grid grid-cols-2 gap-2">
        <Select value={target} onChange={(e) => setTarget(e.target.value)}>
          <option value="">{t('quest.location')}</option>
          {s.lab?.equipment.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
        </Select>
        <Select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
          <option value="">{t('quest.openToAll')}</option>
          {s.users.filter((u) => u.lab_id === s.labId).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </Select>
        <Select value={category} onChange={(e) => setCategory(e.target.value)}>
          {(['daily', 'weekly', 'emergency', 'team', 'esg', 'knowledge'] as const).map((c) => <option key={c} value={c}>{t(`category.${c}`)}</option>)}
        </Select>
        <Input type="number" value={xp} onChange={(e) => setXp(+e.target.value)} />
      </div>
      <div className="flex gap-2"><Button size="sm" type="submit">{t('quest.publish')}</Button><Button size="sm" variant="ghost" type="button" onClick={() => setOpen(false)}>{t('common.cancel')}</Button></div>
    </form>
  )
}

function QuestsTab() {
  const s = useLab()
  const t = useT()
  const me = s.me()
  const q = s.quests
  if (!q || !me) return null
  const total = q.mine.length + q.done.length
  const day = new Date().toLocaleDateString(locale(), { weekday: 'long' }).toUpperCase()

  const planRoute = async () => {
    const quest_ids = q.mine.filter((x) => x.target_id).map((x) => x.id)
    if (!quest_ids.length) return s.toast(t('quests.needLocation'))
    const route = await api.post<Route>('/route', { lab_id: s.labId, quest_ids })
    route.unreachable?.forEach((u) => s.toast(t('quests.skipped', { id: u.id, reason: u.reason }), 'plain'))
    s.set({ route, layer: 'quests' })
    s.camera({ type: 'reset' })
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-line bg-gradient-to-br from-elev to-surface p-4">
        <p className="font-mono text-[11px] tracking-[0.1em] text-accent">{day} • {t('quests.daily')}</p>
        <h3 className="mt-1 text-lg font-semibold">{t('quests.greeting', { name: me.name.replace('Dr. ', '').split(' ')[0] })}</h3>
        <p className="text-xs text-dim">{t('quests.waiting')}</p>
        <div className="mt-3 flex items-center justify-between text-xs">
          <span className="text-dim">{t('quests.progress')}</span>
          <span className="font-mono">{t('quests.doneCount', { done: q.done.length, total: total || 0 })}</span>
        </div>
        <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-white/10">
          <div className="h-full bg-accent transition-all" style={{ width: `${total ? (q.done.length / total) * 100 : 0}%` }} />
        </div>
        <Button size="sm" variant="subtle" className="mt-3 w-full" onClick={planRoute}><Navigation /> {t('quests.planRoute')}</Button>
      </div>

      {me.access !== 'worker' && <CreateQuest />}

      <section className="space-y-2">
        <h4 className="text-xs font-medium uppercase tracking-[0.08em] text-dim">{t('quests.mine', { n: q.mine.length })}</h4>
        {q.mine.length === 0 && <p className="rounded-xl border border-dashed border-line p-3 text-center text-xs text-muted">{t('quests.mineEmpty')}</p>}
        {q.mine.map((x) => <QuestCard key={x.id} q={x} kind="mine" />)}
      </section>
      <section className="space-y-2">
        <h4 className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-[0.08em] text-dim"><Sparkles className="size-3.5 text-accent" /> {t('quests.suggested', { n: q.pool.length })}</h4>
        {q.pool.map((x) => <QuestCard key={x.id} q={x} kind="pool" />)}
      </section>
      {q.done.length > 0 && (
        <section className="space-y-2">
          <h4 className="text-xs font-medium uppercase tracking-[0.08em] text-dim">{t('quests.completed')}</h4>
          {q.done.map((x) => <QuestCard key={x.id} q={x} kind="done" />)}
        </section>
      )}
    </div>
  )
}

function ProjectsTab() {
  const s = useLab()
  const t = useT()
  if (!s.quests || !s.lab) return null
  const lab = s.lab
  return (
    <div className="space-y-3">
      {s.quests.projects.map((p) => {
        const exp = lab.experiments.find((e) => e.id === p.id)
        const done = p.quests.filter((q) => q.status === 'done').length
        return (
          <div key={p.id} className="rounded-xl border border-line bg-elev/60 p-3.5">
            <p className="font-mono text-[11px] text-dim">{p.code}</p>
            <h4 className="text-[15px] font-semibold">{p.title}</h4>
            <p className="text-xs text-dim">{t('projects.lead')}: {p.lead} · {t('projects.nextRun')}: <span className="font-mono text-fg">{fmtDate(p.next_run)}</span></p>
            {p.quests.length > 0 && (
              <>
                <div className="mt-2.5 flex items-center gap-2">
                  <div className="h-1 flex-1 overflow-hidden rounded-full bg-white/10"><div className="h-full bg-accent" style={{ width: `${(done / p.quests.length) * 100}%` }} /></div>
                  <span className="font-mono text-[11px] text-dim">{done}/{p.quests.length}</span>
                </div>
                <ul className="mt-2 space-y-1.5">
                  {p.quests.map((q) => (
                    <li key={q.id} className="flex items-center gap-2 text-[13px]">
                      <span className={cn('flex size-4 items-center justify-center rounded border', q.status === 'done' ? 'border-accent bg-accent text-accent-ink' : 'border-fg/50')}>
                        {q.status === 'done' && <Check className="size-3" />}
                      </span>
                      <span className={cn('flex-1', q.status === 'done' && 'text-muted line-through')}>{q.title}</span>
                      <span className="font-mono text-[10px] text-dim">{q.assignee?.split(' ').map((w) => w[0]).join('') ?? t('projects.open')}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
            {exp && (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {exp.equipment_ids.map((id) => {
                  const e = lab.equipment.find((x) => x.id === id)
                  return e ? (
                    <button key={id} onClick={() => s.focus(id)} className="flex cursor-pointer items-center gap-1 rounded-md border border-line px-1.5 py-0.5 text-[11px] text-dim hover:border-accent/60 hover:text-fg">
                      <Crosshair className="size-3" />{e.name}
                    </button>
                  ) : null
                })}
              </div>
            )}
            {exp && (
              <div className="mt-2.5 space-y-1 border-t border-line pt-2.5 text-xs">
                <p className="text-[10px] uppercase tracking-wider text-dim">{t('projects.materialsPerRun')}</p>
                {exp.usage.map((u) => {
                  const m = lab.materials.find((x) => x.id === u.material_id)
                  if (!m) return null
                  return (
                    <button key={u.material_id} onClick={() => s.set({ materialId: m.id })} className="flex w-full cursor-pointer items-center gap-2 text-left hover:text-fg">
                      <span className="flex-1 text-dim">{m.name}</span>
                      <span className="font-mono">{u.amount} {m.unit}</span>
                      {m.forecast.alerts.length > 0 && <span className="size-2 rounded-full bg-accent" />}
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

export function MaterialRow({ m }: { m: Material }) {
  const set = useLab((s) => s.set)
  const t = useT()
  const f = m.forecast
  const pct = Math.min(100, (m.quantity / Math.max(m.min_stock * 3, m.quantity)) * 100)
  return (
    <button onClick={() => set({ materialId: m.id })} className="w-full cursor-pointer rounded-xl border border-line bg-elev/60 p-3 text-left hover:border-line-strong">
      <div className="flex items-center gap-2">
        <span className="flex-1 text-[13.5px] font-medium">{m.name}</span>
        <span className="font-mono text-xs">{m.quantity} {m.unit}</span>
        <ChevronRight className="size-3.5 text-dim" />
      </div>
      <div className="relative mt-2 h-1 rounded-full bg-white/10">
        <div className={cn('h-full rounded-full', m.quantity < m.min_stock ? 'bg-accent' : 'bg-fg/70')} style={{ width: `${pct}%` }} />
        <div className="absolute -top-0.5 h-2 w-px bg-dim" style={{ left: `${(m.min_stock / Math.max(m.min_stock * 3, m.quantity)) * 100}%` }} title={t('stock.minimum')} />
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] text-dim">
        <span className="font-mono">{m.location_id}</span>
        {f.alerts.includes('expiring') && <Badge variant="accent">{t('stock.expiresIn', { n: f.days_to_expiry ?? 0 })}</Badge>}
        {f.alerts.includes('expired') && <Badge variant="solid">{t('stock.expired')}</Badge>}
        {f.order_by && <Badge variant={f.alerts.includes('reorder') ? 'accent' : 'default'}>{t('stock.orderBy', { date: fmtDate(f.order_by) })}</Badge>}
        {f.alerts.includes('missing_sds') && <Badge variant="accent">{t('stock.sdsMissing')}</Badge>}
        {f.alerts.includes('wrong_location') && <Badge variant="accent">{t('stock.wrongLocation')}</Badge>}
        {f.alerts.includes('quantity_mismatch') && <Badge variant="accent">{t('stock.mismatch')}</Badge>}
      </div>
    </button>
  )
}

function InventoryTab() {
  const s = useLab()
  const t = useT()
  const [filter, setFilter] = useState<'alerts' | 'all'>('alerts')
  if (!s.lab) return null
  const mats = [...s.lab.materials].sort((a, b) => b.forecast.alerts.length - a.forecast.alerts.length)
  const shown = filter === 'all' ? mats : mats.filter((m) => m.forecast.alerts.length)
  return (
    <div className="space-y-3">
      <div className="flex gap-1.5">
        {(['alerts', 'all'] as const).map((f) => (
          <button key={f} onClick={() => setFilter(f)} className={cn('cursor-pointer rounded-md border px-2.5 py-1 text-xs', filter === f ? 'border-accent/60 bg-accent/10 text-accent' : 'border-line text-dim')}>
            {f === 'alerts' ? t('stock.needsAttention', { n: mats.filter((m) => m.forecast.alerts.length).length }) : t('stock.all', { n: mats.length })}
          </button>
        ))}
      </div>
      {shown.map((m) => <MaterialRow key={m.id} m={m} />)}
      <h4 className="pt-2 text-xs font-medium uppercase tracking-[0.08em] text-dim">{t('stock.samples')}</h4>
      {s.lab.samples.map((x) => (
        <button key={x.id} onClick={() => s.focus(x.location_id)} className="flex w-full cursor-pointer items-center gap-2 rounded-lg border border-line px-3 py-2 text-left text-xs hover:border-line-strong">
          <span className="font-mono text-accent">{x.id}</span>
          <span className="flex-1 truncate">{x.label}</span>
          <span className="text-dim">{x.location_id}</span>
        </button>
      ))}
    </div>
  )
}

const BADGE_ICON: Record<string, typeof Shield> = { shield: Shield, leaf: Leaf, users: Users, book: BookOpen, package: Package }

function ProfileTab() {
  const s = useLab()
  const t = useT()
  const me = s.me()
  if (!me) return null
  const team = s.users.filter((u) => u.lab_id === s.labId)
  const teamXp = team.reduce((a, u) => a + u.xp, 0)
  const challenge = s.quests?.challenges?.find((c) => c.active) ?? null
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-line bg-elev/60 p-4">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-dim">{t('me.level')}</p>
            <p className="font-display text-3xl font-bold">{me.level}</p>
          </div>
          <div className="text-right">
            <p className="font-mono text-xl text-accent">{me.xp} XP</p>
            <p className="text-xs text-dim">{t('me.questsDone', { n: me.quests_done })}</p>
          </div>
        </div>
        <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10"><div className="h-full bg-accent" style={{ width: `${me.level_progress * 100}%` }} /></div>
        <p className="mt-1 text-right font-mono text-[10px] text-dim">{t('me.toLevel', { xp: 200 - (me.xp % 200), level: me.level + 1 })}</p>
      </div>
      <section>
        <h4 className="mb-2 text-xs font-medium uppercase tracking-[0.08em] text-dim">{t('me.badges')}</h4>
        {me.badges.length === 0 && <p className="text-xs text-muted">{t('me.noBadges')}</p>}
        <div className="grid grid-cols-2 gap-2">
          {me.badges.map((b) => {
            const Icon = BADGE_ICON[b.icon] ?? Award
            return (
              <div key={b.name} className="rounded-xl border border-line bg-elev/60 p-3">
                <Icon className="size-5 text-accent" />
                <p className="mt-1.5 text-sm font-medium">{tx(`badge.${b.name}`, b.name)}</p>
                <p className="text-[11px] text-dim">{tx(`badgeDesc.${b.name}`, b.desc)} · {b.count}×</p>
              </div>
            )
          })}
        </div>
      </section>
      <section className="rounded-xl border border-accent/30 bg-accent/5 p-3.5">
        <h4 className="flex items-center gap-1.5 text-sm font-semibold"><Users className="size-4 text-accent" /> {t('me.teamChallenge')}</h4>
        <p className="mt-1 text-xs text-dim">{challenge?.title ?? t('me.noChallenge')}</p>
        {challenge && (
          <div className="mt-2 flex items-center gap-2">
            <div className="h-1 flex-1 overflow-hidden rounded-full bg-white/10"><div className="h-full bg-accent" style={{ width: `${challenge.progress * 100}%` }} /></div>
            <span className="font-mono text-[11px] text-dim">{challenge.value}/{challenge.target}</span>
          </div>
        )}
        <p className="mt-2 font-mono text-xs">{t('me.teamXp')}: <span className="text-accent">{teamXp}</span></p>
        <p className="mt-1 text-[11px] text-muted">{t('me.teamNote')}</p>
      </section>
      <section>
        <h4 className="mb-2 text-xs font-medium uppercase tracking-[0.08em] text-dim">{t('me.pointsTitle')}</h4>
        <ul className="space-y-1 text-xs">
          {([['me.p.daily', '20'], ['me.p.help', '30–40'], ['me.p.hazard', '40'], ['me.p.docs', '15'], ['me.p.waste', '35'], ['me.p.knowledge', '25']] as const).map(([a, p]) => (
            <li key={a} className="flex justify-between border-b border-line py-1.5"><span className="text-dim">{t(a)}</span><span className="font-mono">{p}</span></li>
          ))}
        </ul>
        <p className="mt-1.5 text-[10px] text-muted">{t('me.pointsNote')}</p>
      </section>
    </div>
  )
}

export default function SidePanel() {
  const s = useLab()
  const t = useT()
  if (!s.sideOpen) return null
  return (
    <aside className="pointer-events-auto absolute bottom-0 right-0 top-20 z-30 flex w-[min(400px,100vw)] flex-col border-l border-t border-line bg-surface/97 backdrop-blur-md sm:rounded-tl-2xl">
      <Tabs value={s.sideTab} onValueChange={(v) => s.set({ sideTab: v })} className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center gap-2 border-b border-line p-3">
          <TabsList className="flex-1">
            <TabsTrigger value="quests"><Sparkles /> {t('tabs.quests')}</TabsTrigger>
            <TabsTrigger value="projects"><FlaskConical /> {t('tabs.projects')}</TabsTrigger>
            <TabsTrigger value="inventory"><Package /> {t('tabs.stock')}</TabsTrigger>
            <TabsTrigger value="me"><Award /> {t('tabs.me')}</TabsTrigger>
          </TabsList>
          <button onClick={() => s.set({ sideOpen: false })} className="cursor-pointer rounded-lg p-1.5 text-dim hover:bg-hover hover:text-fg"><X className="size-4" /></button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          <TabsContent value="quests"><QuestsTab /></TabsContent>
          <TabsContent value="projects"><ProjectsTab /></TabsContent>
          <TabsContent value="inventory"><InventoryTab /></TabsContent>
          <TabsContent value="me"><ProfileTab /></TabsContent>
        </div>
      </Tabs>
    </aside>
  )
}
