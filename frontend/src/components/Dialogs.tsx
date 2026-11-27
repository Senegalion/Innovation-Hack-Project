import {
  AlertOctagon, ArrowRight, BookOpen, Camera, Crosshair, History, Info, Leaf, MessageSquare, Navigation, QrCode,
  ShieldAlert, Sparkles, TriangleAlert, UserRoundSearch,
} from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Avatar, roleLabel } from '@/components/Hud'
import { StatusDot } from '@/components/LabScene'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { Input, Select, Textarea } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/lib/api'
import { t as tr, tx, useLang, useT, type TKey } from '@/lib/i18n'
import { cn, daysUntil, fmtDate, fmtTime } from '@/lib/utils'
import { useLab } from '@/store'
import type { EquipmentDetail, Incident, MaterialDetail, Message, Route } from '@/types'

const logLabel = (k: string) => tx(`log.${k}`, k)

function Field({ label, value, warn }: { label: string; value?: string | null; warn?: boolean }) {
  return (
    <div className="rounded-lg border border-line bg-canvas-edge/60 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wider text-dim">{label}</p>
      <p className={cn('mt-0.5 truncate font-mono text-[13px]', warn && 'text-accent')}>{value || '—'}</p>
    </div>
  )
}

const soon = (iso: string | null, days: number) => {
  const d = daysUntil(iso)
  return d !== null && d <= days
}

function Discussion({ equipmentId }: { equipmentId: string }) {
  const s = useLab()
  const t = useT()
  const channel = `eq:${equipmentId}`
  const [msgs, setMsgs] = useState<Message[]>([])
  const [text, setText] = useState('')
  const [help, setHelp] = useState(false)
  const load = useCallback(() => api.get<Message[]>(`/messages?channel=${channel}`).then(setMsgs), [channel])
  const live = s.messages[channel]
  useEffect(() => { load() }, [load, live?.length])
  const send = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!text.trim()) return
    await api.post('/messages', { channel, sender_id: s.meId, text, help_request: help })
    setText(''); setHelp(false)
    load(); s.loadChannels(); s.refreshQuests()
  }
  return (
    <div className="space-y-3">
      <div className="max-h-64 space-y-2.5 overflow-y-auto">
        {msgs.length === 0 && <p className="py-6 text-center text-sm text-muted">{t('eq.discussionEmpty')}</p>}
        {msgs.map((m) => (
          <div key={m.id} className="flex gap-2">
            <Avatar initials={s.users.find((u) => u.id === m.sender_id)?.initials ?? 'SL'} className="size-7 text-[10px]" />
            <div className="flex-1">
              <p className="text-[11px] text-dim"><span className="font-medium text-fg">{m.sender ?? 'SMARTLAB'}</span> · <span className="font-mono">{fmtDate(m.at)} {fmtTime(m.at)}</span></p>
              <p className="text-sm">{m.help_request ? <Badge variant="accent" className="mr-1">{t('eq.helpTag')}</Badge> : null}{m.text}</p>
            </div>
          </div>
        ))}
      </div>
      <form onSubmit={send} className="flex items-center gap-2">
        <Input value={text} onChange={(e) => setText(e.target.value)} placeholder={t('eq.discussionPlaceholder')} />
        <label className="flex shrink-0 items-center gap-1.5 text-xs text-dim"><Switch checked={help} onCheckedChange={setHelp} /> {t('eq.help')}</label>
        <Button type="submit" size="sm"><ArrowRight /></Button>
      </form>
    </div>
  )
}

function EquipmentDialog() {
  const s = useLab()
  const t = useT()
  const id = s.equipmentId
  const [d, setD] = useState<EquipmentDetail | null>(null)
  const [kind, setKind] = useState('use')
  const [note, setNote] = useState('')
  const [status, setStatus] = useState('')
  const labEq = s.lab?.equipment.find((e) => e.id === id)
  const lang = useLang((x) => x.lang)
  const load = useCallback(() => {
    if (id) api.get<EquipmentDetail>(`/equipment/${id}?user_id=${s.meId}`).then(setD)
  }, [id, s.meId, lang])
  useEffect(() => { setD(null); load() }, [load, labEq?.status, labEq?.last_service])

  const addLog = async (e: React.FormEvent) => {
    e.preventDefault()
    await api.post(`/equipment/${id}/logs`, { user_id: s.meId, kind, note, status: status || null })
    s.toast(t('eq.logged', { kind: logLabel(kind), name: d?.name ?? '' }))
    setNote(''); setStatus('')
    load(); s.refreshLab()
  }
  const route = async () => {
    const r = await api.post<Route>('/route', { lab_id: s.labId, stops: [id] })
    s.set({ route: r, equipmentId: null })
  }
  const pingHelper = async (uid: string, name: string) => {
    await api.post('/messages', {
      channel: `dm:${[s.meId, uid].sort().join(':')}`, sender_id: s.meId, equipment_ref: id,
      text: t('eq.helpMessage', { name: name.replace('Dr. ', '').split(' ')[0], device: d?.name ?? '' }),
    })
    s.toast(t('eq.helpSent', { name }))
    s.loadChannels()
  }

  return (
    <Dialog open={!!id} onOpenChange={(o) => !o && s.set({ equipmentId: null })}>
      <DialogContent className="w-[min(720px,96vw)]">
        {!d ? <div className="p-10 text-center text-sm text-dim">{t('common.loading')}</div> : (
          <>
            <div className="border-b border-line p-5 pr-12">
              <div className="flex items-center gap-2 text-xs text-dim">
                <span className="font-mono">{d.id}</span> · {d.category}
              </div>
              <DialogTitle className="mt-1 font-display text-xl font-semibold">{d.name}</DialogTitle>
              <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
                <span className="flex items-center gap-2"><StatusDot status={d.status} /> {t(`status.${d.status}`)}</span>
                {d.reading && <span className="font-mono text-xs text-dim">{d.reading}</span>}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" variant="subtle" onClick={() => { s.set({ equipmentId: null }); s.focus(d.id) }}><Crosshair /> {t('eq.showOnMap')}</Button>
                <Button size="sm" variant="subtle" onClick={route}><Navigation /> {t('eq.routeHere')}</Button>
                <Button size="sm" variant="outline" onClick={() => s.set({ reportFor: d.id })}><TriangleAlert /> {t('eq.reportIssue')}</Button>
              </div>
            </div>
            <Tabs defaultValue="info" className="flex min-h-0 flex-1 flex-col">
              <div className="px-5 pt-3">
                <TabsList className="w-full">
                  <TabsTrigger value="info"><Info /> {t('eq.tab.card')}</TabsTrigger>
                  <TabsTrigger value="history"><History /> {t('eq.tab.logs')}</TabsTrigger>
                  <TabsTrigger value="chat"><MessageSquare /> {t('eq.tab.discussion')}</TabsTrigger>
                  <TabsTrigger value="help"><UserRoundSearch /> {t('eq.tab.help')}</TabsTrigger>
                </TabsList>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto p-5">
                <TabsContent value="info" className="space-y-4">
                  {d.notes && <div className="rounded-lg border border-accent/30 bg-accent/5 p-3 text-sm">{d.notes}</div>}
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                    <Field label={t('eq.serial')} value={d.serial} />
                    <Field label={t('eq.responsible')} value={d.responsible} />
                    <Field label={t('eq.lastUsedBy')} value={labEq?.last_used_by} />
                    <Field label={t('eq.readingsVerified')} value={fmtDate(d.last_check)} warn={(daysUntil(d.last_check) ?? 0) < -60} />
                    <Field label={t('eq.uncertainty')} value={d.uncertainty} />
                    <Field label={t('eq.lastServicedBy')} value={labEq?.last_serviced_by} />
                    <Field label={t('eq.lastService')} value={fmtDate(d.last_service)} />
                    <Field label={t('eq.nextService')} value={fmtDate(d.next_service)} warn={soon(d.next_service, 7)} />
                    <Field label={t('eq.certValid')} value={fmtDate(d.cert_expiry)} warn={soon(d.cert_expiry, 14)} />
                  </div>
                  {d.manual && (
                    <div>
                      <p className="mb-1 text-[10px] uppercase tracking-wider text-dim">{t('eq.instructions')}</p>
                      <p className="text-sm leading-relaxed text-fg/90">{d.manual}</p>
                    </div>
                  )}
                  {(d.materials.length > 0 || d.samples.length > 0) && (
                    <div>
                      <p className="mb-1.5 text-[10px] uppercase tracking-wider text-dim">{t('eq.contents')}</p>
                      <div className="divide-y divide-line rounded-lg border border-line">
                        {d.materials.map((m) => (
                          <button key={m.id} onClick={() => s.set({ materialId: m.id })} className="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left text-sm hover:bg-hover">
                            <span className="flex-1">{m.name}</span><span className="font-mono text-xs text-dim">{m.quantity} {m.unit}</span>
                          </button>
                        ))}
                        {d.samples.map((x) => (
                          <div key={x.id} className="flex items-center gap-2 px-3 py-2 text-sm">
                            <span className="font-mono text-xs text-accent">{x.id}</span><span className="flex-1">{x.label}</span><span className="text-xs text-dim">{x.status}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="flex items-center gap-4 rounded-lg border border-line p-3">
                    <div className="rounded-md bg-white p-1.5"><QRCodeSVG value={`${location.origin}/?scan=${d.id}`} size={76} /></div>
                    <div className="text-xs text-dim"><p className="font-medium text-fg">{t('eq.qrTitle')}</p>{t('eq.qrText')}
                    </div>
                  </div>
                </TabsContent>
                <TabsContent value="history" className="space-y-4">
                  <form onSubmit={addLog} className="grid grid-cols-2 gap-2 rounded-lg border border-line p-3 sm:grid-cols-[1fr_1fr_2fr_auto]">
                    <Select value={kind} onChange={(e) => setKind(e.target.value)}>
                      {['use', 'check', 'calibration', 'service', 'fix', 'note'].map((k) => <option key={k} value={k}>{logLabel(k)}</option>)}
                    </Select>
                    <Select value={status} onChange={(e) => setStatus(e.target.value)}>
                      <option value="">{t('eq.keepStatus')}</option>
                      <option value="ok">{t('eq.toOk')}</option><option value="maint">{t('eq.toMaint')}</option>
                      <option value="alert">{t('eq.toAlert')}</option><option value="off">{t('eq.toOff')}</option>
                    </Select>
                    <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t('eq.notePlaceholder')} className="col-span-2 sm:col-span-1" />
                    <Button type="submit" size="sm" className="h-9">{t('eq.log')}</Button>
                  </form>
                  <ol className="relative space-y-3 border-l border-line pl-4">
                    {d.logs.map((l) => (
                      <li key={l.id} className="relative">
                        <span className={cn('absolute -left-[21px] top-1.5 size-2.5 rounded-full border-2 border-surface', l.kind === 'issue' ? 'bg-accent' : 'bg-fg/70')} />
                        <p className="font-mono text-[11px] text-dim">{fmtDate(l.at)} · {logLabel(l.kind).toUpperCase()} · {l.user}</p>
                        <p className="text-sm">{l.note || '—'}</p>
                      </li>
                    ))}
                  </ol>
                </TabsContent>
                <TabsContent value="chat"><Discussion equipmentId={d.id} /></TabsContent>
                <TabsContent value="help" className="space-y-4">
                  <div>
                    <p className="mb-2 flex items-center gap-1.5 text-sm font-medium"><Sparkles className="size-4 text-accent" /> {t('eq.whoCanHelp')}</p>
                    <p className="mb-3 text-xs text-dim">{t('eq.helpExplain')}</p>
                    <div className="space-y-2">
                      {d.helpers.map((h) => (
                        <div key={h.user_id} className="flex items-center gap-3 rounded-xl border border-line bg-elev/60 p-3">
                          <Avatar initials={s.users.find((u) => u.id === h.user_id)?.initials ?? '?'} online={h.online} />
                          <div className="min-w-0 flex-1">
                            <p className="text-sm font-medium">{h.name} <span className="text-xs font-normal text-dim">· {roleLabel(h.role)}</span></p>
                            <p className="truncate text-xs text-dim">{h.reasons.join(' · ')}</p>
                          </div>
                          <Badge variant={h.match === 'high' ? 'accent' : 'default'}>{t(h.match === 'high' ? 'eq.match.high' : 'eq.match.good')}</Badge>
                          <Button size="sm" variant="subtle" onClick={() => pingHelper(h.user_id, h.name)}>{t('common.ask')}</Button>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <p className="mb-2 flex items-center gap-1.5 text-sm font-medium"><BookOpen className="size-4 text-accent" /> {t('eq.kb')}</p>
                    {d.knowledge.length === 0 && <p className="text-xs text-muted">{t('eq.kbEmpty')}</p>}
                    {d.knowledge.map((k, i) => (
                      <div key={i} className="mb-2 rounded-xl border border-line p-3 text-sm">
                        <p className="text-dim"><span className="text-[10px] uppercase tracking-wider">{t('eq.problem')}</span><br />{k.problem}</p>
                        {k.cause && <p className="mt-2 text-dim"><span className="text-[10px] uppercase tracking-wider">{t('eq.cause')}</span><br />{k.cause}</p>}
                        <p className="mt-2"><span className="text-[10px] uppercase tracking-wider text-accent">{t('eq.solution')}</span><br />{k.solution}</p>
                        <p className="mt-2 font-mono text-[11px] text-dim">{k.by} · {fmtDate(k.date)}</p>
                      </div>
                    ))}
                  </div>
                </TabsContent>
              </div>
            </Tabs>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

function MaterialDialog() {
  const s = useLab()
  const t = useT()
  const id = s.materialId
  const [d, setD] = useState<MaterialDetail | null>(null)
  const [amount, setAmount] = useState('')
  const labMat = s.lab?.materials.find((m) => m.id === id)
  const lang = useLang((x) => x.lang)
  const load = useCallback(() => { if (id) api.get<MaterialDetail>(`/materials/${id}`).then(setD) }, [id, lang])
  useEffect(() => { setD(null); load() }, [load, labMat?.quantity])
  const log = async (kind: 'take' | 'restock' | 'check') => {
    await api.post(`/materials/${id}/logs`, { user_id: s.meId, kind, amount: parseFloat(amount) || 0 })
    s.toast(kind === 'check' ? t('mat.verified') : t(kind === 'take' ? 'mat.taken' : 'mat.restocked', { amount, unit: d?.unit ?? '' }))
    setAmount('')
    load(); s.refreshLab(); s.refreshQuests()
  }
  const f = d?.forecast
  return (
    <Dialog open={!!id} onOpenChange={(o) => !o && s.set({ materialId: null })}>
      <DialogContent>
        {!d || !f ? <div className="p-10 text-center text-sm text-dim">{t('common.loading')}</div> : (
          <div className="overflow-y-auto">
            <div className="border-b border-line p-5 pr-12">
              <p className="font-mono text-xs text-dim">{t('mat.cas')} {d.cas} · {t('mat.cat')} {d.catalog_no} · {t('mat.lot')} {d.lot}</p>
              <DialogTitle className="mt-1 font-display text-xl font-semibold">{d.name}</DialogTitle>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {d.hazards.map((h) => <Badge key={h}>{h}</Badge>)}
                {!d.sds && <Badge variant="accent">{t('stock.sdsMissing')}</Badge>}
                {f.alerts.includes('wrong_location') && <Badge variant="accent">{t('stock.wrongLocation')}</Badge>}
                {f.alerts.includes('quantity_mismatch') && <Badge variant="accent">{t('stock.mismatch')}</Badge>}
                {f.alerts.includes('expiring') && <Badge variant="accent">{t('mat.expiresIn', { n: f.days_to_expiry ?? 0 })}</Badge>}
              </div>
            </div>
            <div className="space-y-4 p-5">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                <Field label={t('mat.inStock')} value={`${d.quantity} ${d.unit}`} warn={d.quantity < d.min_stock} />
                <Field label={t('mat.minimum')} value={`${d.min_stock} ${d.unit}`} />
                <Field label={t('mat.location')} value={d.location} />
                <Field label={t('mat.expires')} value={fmtDate(d.expires)} warn={soon(d.expires, 14)} />
                <Field label={t('mat.delivered')} value={fmtDate(d.delivered)} />
                <Field label={t('eq.responsible')} value={d.responsible} />
              </div>
              <div className="rounded-xl border border-accent/30 bg-accent/5 p-4">
                <p className="flex items-center gap-1.5 text-sm font-medium"><Sparkles className="size-4 text-accent" /> {t('mat.forecast')}</p>
                <div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                  <div><p className="text-[10px] uppercase tracking-wider text-dim">{t('mat.planned30')}</p><p className="font-mono">{f.planned_use_30d} {d.unit}</p></div>
                  <div><p className="text-[10px] uppercase tracking-wider text-dim">{t('mat.belowMin')}</p><p className="font-mono">{fmtDate(f.below_min_on)}</p></div>
                  <div><p className="text-[10px] uppercase tracking-wider text-dim">{t('mat.runsOut')}</p><p className="font-mono">{fmtDate(f.runs_out_on)}</p></div>
                  <div><p className="text-[10px] uppercase tracking-wider text-dim">{t('mat.orderBy')}</p><p className="font-mono text-accent">{f.order_by ? fmtDate(f.order_by) : t('mat.noNeed')}</p></div>
                </div>
                <p className="mt-2 text-xs text-dim">{t('mat.leadTime', { n: d.lead_time_days, list: d.used_in.map((u) => `${u.code} ${u.title}`).join(', ') || '—' })}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Input type="number" step="any" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder={t('mat.amount', { unit: d.unit })} className="w-36" />
                <Button size="sm" onClick={() => log('take')} disabled={!amount}>{t('mat.take')}</Button>
                <Button size="sm" variant="subtle" onClick={() => log('restock')} disabled={!amount}>{t('mat.restock')}</Button>
                <Button size="sm" variant="ghost" onClick={() => log('check')}>{t('mat.verify')}</Button>
                <Button size="sm" variant="ghost" onClick={() => { s.set({ materialId: null, equipmentId: null }); s.focus(d.location_id) }}><Crosshair /> {t('mat.locate')}</Button>
              </div>
              {d.notes && <p className="text-sm text-dim">{d.notes}</p>}
              <div>
                <p className="mb-2 text-[10px] uppercase tracking-wider text-dim">{t('mat.usageLog')}</p>
                <div className="divide-y divide-line rounded-lg border border-line text-sm">
                  {d.logs.map((l) => (
                    <div key={l.id} className="flex items-center gap-2 px-3 py-2">
                      <span className="w-24 font-mono text-[11px] uppercase text-dim">{logLabel(l.kind)}</span>
                      <span className="flex-1">{l.user}{l.note ? ` — ${l.note}` : ''}</span>
                      {!!l.amount && <span className="font-mono text-xs">{l.kind === 'take' ? '−' : '+'}{l.amount}</span>}
                      <span className="font-mono text-[11px] text-dim">{fmtDate(l.at)}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function ReportDialog() {
  const s = useLab()
  const t = useT()
  const open = s.reportFor !== undefined
  const [category, setCategory] = useState('fault')
  const [priority, setPriority] = useState('medium')
  const [desc, setDesc] = useState('')
  const [eq, setEq] = useState('')
  const [anon, setAnon] = useState(false)
  useEffect(() => { if (open) { setEq(s.reportFor ?? ''); setDesc(''); setPriority('medium'); setCategory('fault') } }, [open])
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    await api.post('/incidents', { lab_id: s.labId, reporter_id: s.meId, category, priority, description: desc, equipment_id: eq || null, anonymous: anon })
    s.toast(t('report.sent'))
    s.set({ reportFor: undefined })
    s.refreshLab(); s.refreshUsers(); s.refreshQuests()
  }
  const aid = s.lab?.points.filter((p) => ['eyewash', 'shower', 'exit', 'firstaid'].includes(p.kind)) ?? []
  return (
    <Dialog open={open} onOpenChange={(o) => !o && s.set({ reportFor: undefined })}>
      <DialogContent className="w-[min(520px,94vw)]">
        <form onSubmit={submit} className="space-y-4 overflow-y-auto p-5">
          <DialogTitle className="flex items-center gap-2 font-display text-lg font-semibold"><ShieldAlert className="size-5 text-accent" /> {t('report.title')}</DialogTitle>
          {priority === 'critical' && (
            <div className="rounded-xl border-2 border-accent bg-accent/10 p-3 text-sm">
              <p className="flex items-center gap-1.5 font-semibold"><AlertOctagon className="size-4 text-accent" /> {t('report.emergencyTitle')}</p>
              <p className="mt-1 text-xs text-fg/90">{t('report.emergencyText', { list: aid.map((p) => p.label).join(', ') })}</p>
              <Button type="button" size="sm" variant="subtle" className="mt-2" onClick={() => { s.set({ layer: 'safety', reportFor: undefined, equipmentId: null }) }}>{t('report.showSafety')}</Button>
            </div>
          )}
          <div className="grid grid-cols-2 gap-2">
            <label className="space-y-1 text-xs text-dim">{t('report.category')}
              <Select value={category} onChange={(e) => setCategory(e.target.value)} className="w-full">
                {(['fault', 'spill', 'exposure', 'fire', 'near_miss', 'other'] as const).map((c) => <option key={c} value={c}>{t(`report.cat.${c}`)}</option>)}
              </Select>
            </label>
            <label className="space-y-1 text-xs text-dim">{t('report.priority')}
              <Select value={priority} onChange={(e) => setPriority(e.target.value)} className="w-full">
                {(['low', 'medium', 'high', 'critical'] as const).map((p) => <option key={p} value={p}>{t(`report.pri.${p}`)}</option>)}
              </Select>
            </label>
          </div>
          <label className="block space-y-1 text-xs text-dim">{t('report.location')}
            <Select value={eq} onChange={(e) => setEq(e.target.value)} className="w-full">
              <option value="">{t('report.wholeLab')}</option>
              {s.lab?.equipment.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
            </Select>
          </label>
          <Textarea value={desc} onChange={(e) => setDesc(e.target.value)} placeholder={t('report.placeholder')} required />
          <label className="flex items-center gap-2 text-sm"><Switch checked={anon} onCheckedChange={setAnon} /> {t('report.anonymous')} <span className="text-xs text-dim">{t('report.anonymousHint')}</span></label>
          <Button type="submit" className="w-full">{t('report.submit')}</Button>
        </form>
      </DialogContent>
    </Dialog>
  )
}

declare global {
  interface Window { BarcodeDetector?: new (o: { formats: string[] }) => { detect: (v: HTMLVideoElement) => Promise<{ rawValue: string }[]> } }
}

export async function resolveCode(raw: string) {
  const s = useLab.getState()
  const code = (raw.includes('scan=') ? new URL(raw, location.origin).searchParams.get('scan') ?? raw : raw).trim()
  try {
    const r = await api.get<{ type: string; id: string; lab_id: string; location?: string; sample?: { label: string; status: string }; owner?: string }>(`/scan/${encodeURIComponent(code)}`)
    if (r.lab_id !== s.labId) await s.selectLab(r.lab_id)
    s.set({ scanOpen: false })
    if (r.type === 'equipment') s.focus(r.id, true)
    else if (r.type === 'material') s.set({ materialId: r.id })
    else {
      s.focus(r.location!)
      s.toast(tr('scan.sample', { id: r.id, label: r.sample?.label ?? '', status: r.sample?.status ?? '', location: r.location ?? '', owner: r.owner ?? '' }), 'plain')
    }
  } catch (e) {
    s.toast((e as Error).message, 'plain')
  }
}

function ScanDialog() {
  const s = useLab()
  const t = useT()
  const [code, setCode] = useState('')
  const [cam, setCam] = useState(false)
  const video = useRef<HTMLVideoElement>(null)
  const supported = typeof window !== 'undefined' && !!window.BarcodeDetector

  useEffect(() => {
    if (!cam || !s.scanOpen) return
    let stream: MediaStream | null = null
    let alive = true
    ;(async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } })
        if (!video.current) return
        video.current.srcObject = stream
        await video.current.play()
        const det = new window.BarcodeDetector!({ formats: ['qr_code'] })
        while (alive) {
          const res = await det.detect(video.current).catch(() => [])
          if (res[0]) { alive = false; resolveCode(res[0].rawValue); break }
          await new Promise((r) => setTimeout(r, 300))
        }
      } catch {
        s.toast(t('scan.cameraError'), 'plain')
        setCam(false)
      }
    })()
    return () => { alive = false; stream?.getTracks().forEach((t) => t.stop()) }
  }, [cam, s.scanOpen])

  return (
    <Dialog open={s.scanOpen} onOpenChange={(o) => { s.set({ scanOpen: o }); if (!o) setCam(false) }}>
      <DialogContent className="w-[min(440px,94vw)]">
        <div className="space-y-4 p-5">
          <DialogTitle className="flex items-center gap-2 font-display text-lg font-semibold"><QrCode className="size-5 text-accent" /> {t('scan.title')}</DialogTitle>
          {cam ? (
            <video ref={video} className="aspect-square w-full rounded-xl bg-black object-cover" muted playsInline />
          ) : (
            <Button variant="subtle" className="w-full" onClick={() => setCam(true)} disabled={!supported}>
              <Camera /> {supported ? t('scan.camera') : t('scan.unsupported')}
            </Button>
          )}
          <form onSubmit={(e) => { e.preventDefault(); resolveCode(code) }} className="flex gap-2">
            <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder={t('scan.placeholder')} autoFocus />
            <Button type="submit">{t('common.open')}</Button>
          </form>
          <p className="text-xs text-dim">{t('scan.hint')}</p>
        </div>
      </DialogContent>
    </Dialog>
  )
}

interface Stats {
  hotspots: { equipment_id: string; name: string; count: number }[]
  incidents_open: number; near_misses: number; incidents_by_priority: Record<string, number>
  rejection_signals: { title: string; reason: string; count: number }[]
  esg: { expiring_flagged: number; expired: number; reorders_planned: number; esg_quests_done: number; est_savings_eur: number }
  engagement: { active_users: number; users: number; quests_done: number; xp_total: number }
  leaderboard: { name: string; xp: number; role: string }[]
}

function AdminDialog() {
  const s = useLab()
  const t = useT()
  const lang = useLang((x) => x.lang)
  const [stats, setStats] = useState<Stats | null>(null)
  const [inc, setInc] = useState<Incident[]>([])
  const [res, setRes] = useState<Record<number, string>>({})
  const load = useCallback(() => {
    api.get<Stats>(`/admin/stats?lab_id=${s.labId}`).then(setStats)
    api.get<Incident[]>(`/incidents?lab_id=${s.labId}`).then(setInc)
  }, [s.labId, lang])
  useEffect(() => { if (s.adminOpen) load() }, [s.adminOpen, load, s.lab])
  const resolve = async (id: number) => {
    await api.post(`/incidents/${id}/resolve`, { user_id: s.meId, resolution: res[id] || t('admin.resolvedDefault') })
    s.toast(t('admin.resolved'))
    load(); s.refreshLab(); s.refreshQuests()
  }
  const open = inc.filter((i) => i.status === 'open')
  const max = Math.max(1, ...(stats?.hotspots.map((h) => h.count) ?? [1]))
  return (
    <Dialog open={s.adminOpen} onOpenChange={(o) => s.set({ adminOpen: o })}>
      <DialogContent className="w-[min(960px,96vw)]">
        <div className="border-b border-line p-5">
          <DialogTitle className="font-display text-xl font-semibold">{t('admin.title', { lab: s.lab?.name ?? '' })}</DialogTitle>
          <p className="text-xs text-dim">{t('admin.subtitle')}</p>
        </div>
        {stats && (
          <div className="grid gap-4 overflow-y-auto p-5 md:grid-cols-2">
            <div className="grid grid-cols-2 gap-2 md:col-span-2 md:grid-cols-4">
              {[
                [t('admin.openIncidents'), stats.incidents_open], [t('admin.nearMisses'), stats.near_misses],
                [t('admin.questsDone'), stats.engagement.quests_done], [t('admin.savings'), stats.esg.est_savings_eur],
              ].map(([l, v]) => (
                <div key={l} className="rounded-xl border border-line bg-elev/60 p-3">
                  <p className="text-[10px] uppercase tracking-wider text-dim">{l}</p>
                  <p className="font-display text-2xl font-semibold">{v}</p>
                </div>
              ))}
            </div>
            <section className="space-y-2 md:col-span-2">
              <h4 className="flex items-center gap-1.5 text-sm font-medium"><ShieldAlert className="size-4 text-accent" /> {t('admin.escalations')}</h4>
              {open.length === 0 && <p className="text-xs text-muted">{t('admin.nothingOpen')}</p>}
              {open.map((i) => (
                <div key={i.id} className={cn('flex flex-wrap items-center gap-2 rounded-xl border p-3', i.priority === 'critical' || i.priority === 'high' ? 'border-accent/50' : 'border-line')}>
                  <Badge variant={i.priority === 'critical' ? 'solid' : i.priority === 'high' ? 'accent' : 'default'}>{t(`priority.${i.priority}`)}</Badge>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm">{i.description}</p>
                    <p className="text-xs text-dim">{t(`report.cat.${i.category}` as TKey)} · {i.equipment ?? t('common.lab')} · {i.reporter} · {fmtDate(i.at)} {fmtTime(i.at)}</p>
                  </div>
                  <Input value={res[i.id] ?? ''} onChange={(e) => setRes({ ...res, [i.id]: e.target.value })} placeholder={t('admin.resolution')} className="h-8 w-48 text-xs" />
                  <Button size="sm" onClick={() => resolve(i.id)}>{t('admin.resolve')}</Button>
                </div>
              ))}
            </section>
            <section className="rounded-xl border border-line p-4">
              <h4 className="mb-3 text-sm font-medium">{t('admin.hotspots')}</h4>
              {stats.hotspots.map((h) => (
                <button key={h.equipment_id} onClick={() => { s.set({ adminOpen: false, layer: 'social' }); s.focus(h.equipment_id) }} className="mb-2 block w-full cursor-pointer text-left">
                  <div className="flex justify-between text-xs"><span>{h.name}</span><span className="font-mono">{h.count}</span></div>
                  <div className="mt-1 h-1.5 rounded-full bg-white/10"><div className="h-full rounded-full bg-accent" style={{ width: `${(h.count / max) * 100}%` }} /></div>
                </button>
              ))}
            </section>
            <section className="rounded-xl border border-line p-4">
              <h4 className="mb-3 text-sm font-medium">{t('admin.signals')}</h4>
              {stats.rejection_signals.length === 0 && <p className="text-xs text-muted">{t('admin.noSignals')}</p>}
              {stats.rejection_signals.map((r) => (
                <div key={r.title} className="mb-2 rounded-lg border border-accent/30 bg-accent/5 p-2.5 text-xs">
                  <p className="font-medium text-fg">{t('admin.rejected', { title: r.title, n: r.count })}</p>
                  <p className="text-dim">{t('admin.reason', { reason: r.reason })}</p>
                </div>
              ))}
            </section>
            <section className="rounded-xl border border-line p-4">
              <h4 className="mb-3 flex items-center gap-1.5 text-sm font-medium"><Leaf className="size-4 text-accent" /> {t('admin.esg')}</h4>
              <ul className="space-y-1.5 text-xs">
                {[
                  [t('admin.esg.flagged'), stats.esg.expiring_flagged], [t('admin.esg.expired'), stats.esg.expired],
                  [t('admin.esg.reorders'), stats.esg.reorders_planned], [t('admin.esg.quests'), stats.esg.esg_quests_done],
                ].map(([l, v]) => <li key={l} className="flex justify-between border-b border-line pb-1.5"><span className="text-dim">{l}</span><span className="font-mono">{v}</span></li>)}
              </ul>
            </section>
            <section className="rounded-xl border border-line p-4">
              <h4 className="mb-3 text-sm font-medium">{t('admin.engagement', { active: stats.engagement.active_users, total: stats.engagement.users })}</h4>
              <ul className="space-y-1.5 text-xs">
                {stats.leaderboard.map((u) => <li key={u.name} className="flex justify-between"><span>{u.name} <span className="text-dim">· {roleLabel(u.role)}</span></span><span className="font-mono">{u.xp} XP</span></li>)}
              </ul>
              <p className="mt-2 text-[10px] text-muted">{t('admin.engagementNote')}</p>
            </section>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

const TIPS = [1, 2, 3, 4, 5] as const

function Onboarding() {
  const s = useLab()
  const t = useT()
  const [i, setI] = useState(0)
  const me = s.me()
  return (
    <Dialog open={s.onboardingOpen} onOpenChange={(o) => { s.set({ onboardingOpen: o }); if (!o) setI(0) }}>
      <DialogContent className="w-[min(460px,94vw)]">
        <div className="p-6">
          <p className="font-mono text-[11px] tracking-[0.1em] text-accent">ONBOARDING · {i + 1}/{TIPS.length}</p>
          <DialogTitle className="mt-2 font-display text-2xl font-semibold">{i === 0 && me ? t('onb.welcome', { name: me.name.replace('Dr. ', '').split(' ')[0] }) : ''}{t(`onb.${TIPS[i]}.title`)}</DialogTitle>
          <p className="mt-3 text-sm leading-relaxed text-fg/85">{t(`onb.${TIPS[i]}.body`)}</p>
          <div className="mt-5 flex gap-1">{TIPS.map((_, k) => <span key={k} className={cn('h-1 flex-1 rounded-full', k <= i ? 'bg-accent' : 'bg-white/10')} />)}</div>
          <div className="mt-5 flex justify-between">
            <Button variant="ghost" onClick={() => s.set({ onboardingOpen: false })}>{t('onb.skip')}</Button>
            <Button onClick={() => (i < TIPS.length - 1 ? setI(i + 1) : (s.set({ onboardingOpen: false }), setI(0)))}>
              {i < TIPS.length - 1 ? t('onb.next') : t('onb.start')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default function Dialogs() {
  return (
    <>
      <EquipmentDialog />
      <MaterialDialog />
      <ReportDialog />
      <ScanDialog />
      <AdminDialog />
      <Onboarding />
    </>
  )
}
