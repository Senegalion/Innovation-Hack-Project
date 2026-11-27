import {
  AlertOctagon, ArrowRight, BookOpen, Camera, Crosshair, History, ImagePlus, Info, MessageSquare, Navigation,
  Printer, QrCode, ShieldAlert, Sparkles, TestTube, TriangleAlert, UserRoundSearch,
} from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { useCallback, useEffect, useRef, useState } from 'react'
import AdminPanel from '@/components/AdminPanel'
import { MessageExtras } from '@/components/ChatDrawer'
import { Avatar, roleLabel } from '@/components/Hud'
import { StatusDot } from '@/components/LabScene'
import { DocumentList, DocumentUpload } from '@/components/SidePanel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { Input, Select, Textarea } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/lib/api'
import { t as tr, tx, useLang, useT } from '@/lib/i18n'
import { cn, daysUntil, fmtDate, fmtTime } from '@/lib/utils'
import { useLab } from '@/store'
import type { EquipmentDetail, LogEntry, MaterialDetail, Message, Onboarding, Procedure, Route, Sample } from '@/types'

const logLabel = (k: string) => tx(`log.${k}`, k)

function Field({ label, value, warn }: { label: string; value?: string | null; warn?: boolean }) {
  return (
    <div className="rounded-lg border border-line bg-canvas-edge/60 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wider text-dim">{label}</p>
      <p className={cn('mt-0.5 truncate font-mono text-[13px]', warn && 'text-accent')}>{value || '—'}</p>
    </div>
  )
}

const soon = (iso: string | null | undefined, days: number) => {
  const d = daysUntil(iso)
  return d !== null && d <= days
}

function Timeline({ logs }: { logs: LogEntry[] }) {
  return (
    <ol className="relative space-y-3 border-l border-line pl-4">
      {logs.map((l) => (
        <li key={l.id} className="relative">
          <span className={cn('absolute -left-[21px] top-1.5 size-2.5 rounded-full border-2 border-surface', l.kind === 'issue' ? 'bg-accent' : 'bg-fg/70')} />
          <p className="font-mono text-[11px] text-dim">{fmtDate(l.at)} {fmtTime(l.at)} · {logLabel(l.kind).toUpperCase()} · {l.user ?? '—'}</p>
          <p className="text-sm">{l.note || '—'}</p>
        </li>
      ))}
    </ol>
  )
}

function Discussion({ equipmentId }: { equipmentId: string }) {
  const s = useLab()
  const t = useT()
  const channel = `eq:${equipmentId}`
  const [msgs, setMsgs] = useState<Message[]>([])
  const [text, setText] = useState('')
  const [help, setHelp] = useState(false)
  const [photo, setPhoto] = useState<{ id: number; title: string } | null>(null)
  const load = useCallback(() => api.get<Message[]>(`/messages?channel=${channel}`).then(setMsgs), [channel])
  const live = s.messages[channel]
  useEffect(() => { load() }, [load, live?.length])
  const send = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!text.trim() && !photo) return
    await api.post('/messages', { channel, sender_id: s.meId, text: text || '📷', help_request: help, attachments: photo ? [photo.id] : [] })
    setText(''); setHelp(false); setPhoto(null)
    load(); s.loadChannels(); s.refreshQuests()
  }
  return (
    <div className="space-y-3">
      <div className="max-h-72 space-y-2.5 overflow-y-auto">
        {msgs.length === 0 && <p className="py-6 text-center text-sm text-muted">{t('eq.discussionEmpty')}</p>}
        {msgs.map((m) => (
          <div key={m.id} className="flex gap-2">
            <Avatar initials={s.users.find((u) => u.id === m.sender_id)?.initials ?? 'SL'} className="size-7 text-[10px]" />
            <div className="flex-1">
              <p className="text-[11px] text-dim"><span className="font-medium text-fg">{m.sender ?? 'SMARTLAB'}</span> · <span className="font-mono">{fmtDate(m.at)} {fmtTime(m.at)}</span></p>
              <p className="text-sm">{m.help_request ? <Badge variant="accent" className="mr-1">{t('eq.helpTag')}</Badge> : null}{m.text}</p>
              <MessageExtras m={m} />
            </div>
          </div>
        ))}
      </div>
      {photo && <p className="text-xs text-dim">📎 {photo.title} <button className="cursor-pointer text-accent" onClick={() => setPhoto(null)}>×</button></p>}
      <form onSubmit={send} className="flex items-center gap-2">
        <Input value={text} onChange={(e) => setText(e.target.value)} placeholder={t('eq.discussionPlaceholder')} />
        <label className="flex shrink-0 cursor-pointer items-center rounded-lg border border-line p-2 text-dim hover:text-fg" title={t('eq.addPhoto')}>
          <ImagePlus className="size-4" />
          <input type="file" accept="image/*" capture="environment" className="hidden" onChange={async (e) => {
            const f = e.target.files?.[0]
            if (!f) return
            const d = await api.upload<{ id: number; title: string }>('/documents', { file: f, lab_id: s.labId, kind: 'image', target_type: 'machine', target_id: equipmentId, process: 'false' })
            setPhoto(d)
            e.target.value = ''
          }} />
        </label>
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
  const [reading, setReading] = useState('')
  const [within, setWithin] = useState(true)
  const labEq = s.lab?.equipment.find((e) => e.id === id)
  const lang = useLang((x) => x.lang)
  const load = useCallback(() => {
    if (id) api.get<EquipmentDetail>(`/equipment/${id}?user_id=${s.meId}`).then(setD).catch(() => setD(null))
  }, [id, s.meId, lang])
  useEffect(() => { setD(null); load() }, [load, labEq?.status, labEq?.last_service])

  const isReading = kind === 'check' || kind === 'calibration'
  const addLog = async (e: React.FormEvent) => {
    e.preventDefault()
    await api.post(`/equipment/${id}/logs`, {
      user_id: s.meId, kind, note, status: status || null,
      reading: isReading ? reading || null : null, within_uncertainty: isReading ? within : null,
    })
    s.toast(isReading && !within ? t('eq.outOfRange') : t('eq.logged', { kind: logLabel(kind), name: d?.name ?? '' }), isReading && !within ? 'accent' : 'plain')
    setNote(''); setStatus(''); setReading(''); setWithin(true)
    load(); s.refreshLab(); s.refreshQuests(); s.refreshUsers()
  }
  const route = async () => {
    const r = await api.post<Route>('/route', { lab_id: s.labId, stops: [id] })
    r.unreachable?.forEach((u) => s.toast(t('quests.skipped', { id: u.id, reason: u.reason }), 'plain'))
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
  const quests = [...(s.quests?.mine ?? []), ...(s.quests?.pool ?? [])].filter((q) => q.target_id === id)
  const p = d?.prediction

  return (
    <Dialog open={!!id} onOpenChange={(o) => !o && s.set({ equipmentId: null })}>
      <DialogContent className="w-[min(760px,96vw)]">
        {!d ? <div className="p-10 text-center text-sm text-dim">{t('common.loading')}</div> : (
          <>
            <div className="border-b border-line p-5 pr-14">
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
                  {quests.length > 0 && (
                    <div>
                      <p className="mb-1.5 text-[10px] uppercase tracking-wider text-dim">{t('eq.assignedQuests')}</p>
                      <div className="space-y-1">
                        {quests.map((q) => (
                          <button key={q.id} onClick={() => s.set({ equipmentId: null, sideOpen: true, sideTab: 'quests' })} className="flex w-full cursor-pointer items-center gap-2 rounded-lg border border-line px-3 py-2 text-left text-sm hover:bg-hover">
                            <Sparkles className="size-3.5 text-accent" /><span className="flex-1">{q.title}</span><span className="font-mono text-xs text-accent">+{q.xp} XP</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
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
                  {p && (
                    <div className="rounded-xl border border-accent/30 bg-accent/5 p-4">
                      <p className="flex items-center gap-1.5 text-sm font-medium"><Sparkles className="size-4 text-accent" /> {t('eq.prediction')}</p>
                      <div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                        <div><p className="text-[10px] uppercase tracking-wider text-dim">{t('eq.nextInspection')}</p><p className="font-mono">{fmtDate(p.next_inspection)}</p><p className="text-[11px] text-dim">{p.next_inspection_reason ? tx(`eq.reason.${p.next_inspection_reason}`, p.next_inspection_reason) : ''}</p></div>
                        <div><p className="text-[10px] uppercase tracking-wider text-dim">{t('eq.failures')}</p><p className="font-mono">{p.failures_recorded}</p></div>
                        <div><p className="text-[10px] uppercase tracking-wider text-dim">{t('eq.mtbf')}</p><p className="font-mono">{p.mtbf_days ? t('common.days', { n: p.mtbf_days }) : '—'}</p></div>
                        <div><p className="text-[10px] uppercase tracking-wider text-dim">{t('eq.predictedIssue')}</p><p className="font-mono text-accent">{fmtDate(p.predicted_next_issue)}</p></div>
                      </div>
                    </div>
                  )}
                  {d.manual && (
                    <div>
                      <p className="mb-1 text-[10px] uppercase tracking-wider text-dim">{t('eq.instructions')}</p>
                      <p className="text-sm leading-relaxed text-fg/90">{d.manual}</p>
                    </div>
                  )}
                  {d.on_workstation.length > 0 && (
                    <div>
                      <p className="mb-1.5 text-[10px] uppercase tracking-wider text-dim">{t('eq.onWorkstation')}</p>
                      <div className="flex flex-wrap gap-1.5">
                        {d.on_workstation.map((e) => (
                          <button key={e.id} onClick={() => s.set({ equipmentId: e.id })} className="cursor-pointer rounded-md border border-line px-2 py-1 text-xs text-dim hover:border-accent/60 hover:text-fg">{e.name}</button>
                        ))}
                      </div>
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
                          <button key={x.id} onClick={() => s.set({ sampleId: x.id })} className="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left text-sm hover:bg-hover">
                            <span className="font-mono text-xs text-accent">{x.id}</span><span className="flex-1">{x.label}</span><span className="text-xs text-dim">{x.status}</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="space-y-2">
                    <p className="text-[10px] uppercase tracking-wider text-dim">{t('docs.title')}</p>
                    <DocumentList docs={d.documents} />
                    <DocumentUpload targetType={d.asset_type ?? 'machine'} targetId={d.id} onDone={() => setTimeout(load, 800)} />
                  </div>
                  <div className="flex items-center gap-4 rounded-lg border border-line p-3">
                    <div className="rounded-md bg-white p-1.5"><QRCodeSVG value={`${location.origin}/?scan=${d.id}`} size={76} /></div>
                    <div className="flex-1 text-xs text-dim"><p className="font-medium text-fg">{t('eq.qrTitle')}</p>{t('eq.qrText')}</div>
                    <Button size="sm" variant="ghost" onClick={() => window.open(`/api/qr/${d.id}.svg?base_url=${encodeURIComponent(location.origin)}&scale=10`, '_blank')}><Printer /></Button>
                  </div>
                </TabsContent>
                <TabsContent value="history" className="space-y-4">
                  <form onSubmit={addLog} className="space-y-2 rounded-lg border border-line p-3">
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-[1fr_1fr_2fr_auto]">
                      <Select value={kind} onChange={(e) => setKind(e.target.value)}>
                        {['use', 'check', 'calibration', 'service', 'fix', 'note', 'issue'].map((k) => <option key={k} value={k}>{logLabel(k)}</option>)}
                      </Select>
                      <Select value={status} onChange={(e) => setStatus(e.target.value)}>
                        <option value="">{t('eq.keepStatus')}</option>
                        <option value="ok">{t('eq.toOk')}</option><option value="maint">{t('eq.toMaint')}</option>
                        <option value="alert">{t('eq.toAlert')}</option><option value="off">{t('eq.toOff')}</option>
                      </Select>
                      <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t('eq.notePlaceholder')} className="col-span-2 sm:col-span-1" />
                      <Button type="submit" size="sm" className="h-9">{t('eq.log')}</Button>
                    </div>
                    {isReading && (
                      <div className="flex flex-wrap items-center gap-3">
                        <Input value={reading} onChange={(e) => setReading(e.target.value)} placeholder={t('eq.readingPlaceholder')} className="w-56 max-w-full" />
                        <label className="flex items-center gap-2 text-xs text-dim"><Switch checked={within} onCheckedChange={setWithin} /> {t('eq.withinUncertainty', { range: d.uncertainty || '—' })}</label>
                      </div>
                    )}
                  </form>
                  <Timeline logs={d.logs} />
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
                            <p className="truncate text-xs text-dim" title={h.reasons.join(' · ')}>{h.reasons.join(' · ')}</p>
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
                  {d.incidents.filter((i) => i.status === 'open').length > 0 && (
                    <div>
                      <p className="mb-2 flex items-center gap-1.5 text-sm font-medium"><TriangleAlert className="size-4 text-accent" /> {t('eq.openIssues')}</p>
                      {d.incidents.filter((i) => i.status === 'open').map((i) => (
                        <div key={i.id} className="mb-2 rounded-xl border border-accent/30 p-3 text-sm">
                          <p>{i.description}</p>
                          <p className="mt-1 font-mono text-[11px] text-dim">{t(`priority.${i.priority}`)} · {i.reporter} · {fmtDate(i.at)}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </TabsContent>
              </div>
            </Tabs>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

type MatAction = 'take' | 'restock' | 'check' | 'move' | 'dispose' | 'use_before_expiry'

function MaterialDialog() {
  const s = useLab()
  const t = useT()
  const id = s.materialId
  const [d, setD] = useState<MaterialDetail | null>(null)
  const [action, setAction] = useState<MatAction>('take')
  const [amount, setAmount] = useState('')
  const [target, setTarget] = useState('')
  const labMat = s.lab?.materials.find((m) => m.id === id)
  const lang = useLang((x) => x.lang)
  const load = useCallback(() => { if (id) api.get<MaterialDetail>(`/materials/${id}`).then(setD) }, [id, lang])
  useEffect(() => { setD(null); load() }, [load, labMat?.quantity, labMat?.location_id])
  const needsAmount = action !== 'move'
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const value = parseFloat(amount)
    if (needsAmount && Number.isNaN(value)) return
    if (action === 'move' && !target) return
    await api.post(`/materials/${id}/logs`, {
      user_id: s.meId, kind: action, amount: action === 'check' ? 0 : value || 0,
      observed: action === 'check' ? value : null, location_id: action === 'move' ? target : null,
    })
    s.toast(t(`mat.done.${action}`, { amount, unit: d?.unit ?? '' }))
    setAmount(''); setTarget('')
    load(); s.refreshLab(); s.refreshQuests(); s.refreshUsers()
  }
  const f = d?.forecast
  const storages = s.lab?.equipment.filter((e) => e.kind === 'storage' || e.kind === 'freezer') ?? []
  return (
    <Dialog open={!!id} onOpenChange={(o) => !o && s.set({ materialId: null })}>
      <DialogContent className="w-[min(720px,96vw)]">
        {!d || !f ? <div className="p-10 text-center text-sm text-dim">{t('common.loading')}</div> : (
          <div className="overflow-y-auto">
            <div className="border-b border-line p-5 pr-14">
              <p className="font-mono text-xs text-dim">{t('mat.cas')} {d.cas} · {t('mat.cat')} {d.catalog_no} · {t('mat.lot')} {d.lot}</p>
              <DialogTitle className="mt-1 font-display text-xl font-semibold">{d.name}</DialogTitle>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {d.hazards.map((h) => <Badge key={h}>{h}</Badge>)}
                {!d.sds && <Badge variant="accent">{t('stock.sdsMissing')}</Badge>}
                {f.alerts.includes('wrong_location') && <Badge variant="accent">{t('stock.wrongLocation')}</Badge>}
                {f.alerts.includes('quantity_mismatch') && <Badge variant="accent">{t('stock.mismatch')}</Badge>}
                {f.alerts.includes('expiring') && <Badge variant="accent">{t('mat.expiresIn', { n: f.days_to_expiry ?? 0 })}</Badge>}
                {f.alerts.includes('expired') && <Badge variant="solid">{t('stock.expired')}</Badge>}
              </div>
            </div>
            <div className="space-y-4 p-5">
              {(f.storage_issue || f.quantity_issue) && (
                <div className="space-y-1 rounded-xl border border-accent/40 bg-accent/5 p-3 text-sm">
                  {f.storage_issue && <p className="flex items-start gap-1.5"><TriangleAlert className="mt-0.5 size-4 shrink-0 text-accent" />{f.storage_issue}</p>}
                  {f.quantity_issue && <p className="flex items-start gap-1.5"><TriangleAlert className="mt-0.5 size-4 shrink-0 text-accent" />{t('mat.mismatchText', { observed: f.quantity_issue.observed, expected: f.quantity_issue.expected, unit: d.unit })}</p>}
                </div>
              )}
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                <Field label={t('mat.inStock')} value={`${d.quantity} ${d.unit}`} warn={d.quantity < d.min_stock} />
                <Field label={t('mat.minimum')} value={`${d.min_stock} ${d.unit}`} />
                <Field label={t('mat.location')} value={d.location} />
                <Field label={t('mat.expires')} value={fmtDate(d.expires)} warn={soon(d.expires, 14)} />
                <Field label={t('mat.delivered')} value={fmtDate(d.delivered)} />
                <Field label={t('eq.responsible')} value={d.responsible} />
                <Field label={t('mat.lastUsedBy')} value={d.last_used_by} />
                <Field label={t('mat.storage')} value={tx(`storage.${d.storage_requirement}`, d.storage_requirement)} />
                <Field label={t('mat.unitCost')} value={d.unit_cost_eur ? `${d.unit_cost_eur} € / ${d.unit}` : '—'} />
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
                {!!f.suggested_order_qty && <p className="mt-1 text-xs">{t('mat.suggestedOrder', { qty: f.suggested_order_qty, unit: d.unit })}</p>}
                {!!f.waste_risk_eur && <p className="mt-1 text-xs text-accent">{t('mat.wasteRisk', { qty: f.unused_at_expiry ?? 0, unit: d.unit, eur: f.waste_risk_eur })}</p>}
              </div>
              <form onSubmit={submit} className="space-y-2 rounded-lg border border-line p-3">
                <div className="flex flex-wrap gap-1.5">
                  {(['take', 'restock', 'check', 'move', 'dispose', 'use_before_expiry'] as const).map((a) => (
                    <button type="button" key={a} onClick={() => setAction(a)} className={cn('cursor-pointer rounded-md border px-2 py-1 text-xs', action === a ? 'border-accent/60 bg-accent/10 text-accent' : 'border-line text-dim hover:text-fg')}>
                      {t(`mat.action.${a}`)}
                    </button>
                  ))}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {needsAmount ? (
                    <Input type="number" step="any" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder={action === 'check' ? t('mat.counted', { unit: d.unit }) : t('mat.amount', { unit: d.unit })} className="w-44 max-w-full" />
                  ) : (
                    <Select value={target} onChange={(e) => setTarget(e.target.value)} className="w-64 max-w-full">
                      <option value="">{t('mat.newLocation')}</option>
                      {storages.filter((e) => e.id !== d.location_id).map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
                    </Select>
                  )}
                  <Button size="sm" type="submit" className="h-9">{t('mat.save')}</Button>
                  <Button size="sm" variant="ghost" type="button" onClick={() => { s.set({ materialId: null, equipmentId: null }); s.focus(d.location_id) }}><Crosshair /> {t('mat.locate')}</Button>
                </div>
              </form>
              {d.notes && <p className="text-sm text-dim">{d.notes}</p>}
              <div className="space-y-2">
                <p className="text-[10px] uppercase tracking-wider text-dim">{t('mat.documents')}</p>
                <DocumentList docs={d.documents} />
                <DocumentUpload targetType="material" targetId={d.id} kind="sds" onDone={() => setTimeout(load, 800)} />
              </div>
              <div>
                <p className="mb-2 text-[10px] uppercase tracking-wider text-dim">{t('mat.usageLog')}</p>
                <div className="divide-y divide-line rounded-lg border border-line text-sm">
                  {d.logs.map((l) => (
                    <div key={l.id} className="flex items-center gap-2 px-3 py-2">
                      <span className="w-28 shrink-0 font-mono text-[11px] uppercase text-dim max-sm:w-20">{logLabel(l.kind)}</span>
                      <span className="flex-1">{l.user}{l.note ? ` — ${l.note}` : ''}</span>
                      {!!l.amount && <span className="font-mono text-xs">{['take', 'dispose', 'use_before_expiry'].includes(l.kind) ? '−' : '+'}{l.amount}</span>}
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

type SampleFull = Sample & { owner: string | null; history: LogEntry[] }

function SampleDialog() {
  const s = useLab()
  const t = useT()
  const id = s.sampleId
  const [d, setD] = useState<SampleFull | null>(null)
  const [loc, setLoc] = useState('')
  const [status, setStatus] = useState('')
  const load = useCallback(() => { if (id) api.get<SampleFull>(`/samples/${id}`).then(setD).catch(() => setD(null)) }, [id])
  useEffect(() => { setD(null); load() }, [load])
  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    await api.patch(`/samples/${id}`, { user_id: s.meId, location_id: loc || null, status: status || null })
    s.toast(t('sample.updated'))
    setLoc(''); setStatus('')
    load(); s.refreshLab()
  }
  const qr = id ? `/api/qr/${id}.svg?base_url=${encodeURIComponent(location.origin)}&scale=8` : ''
  return (
    <Dialog open={!!id} onOpenChange={(o) => !o && s.set({ sampleId: null })}>
      <DialogContent className="w-[min(560px,94vw)]">
        {!d ? <div className="p-10 text-center text-sm text-dim">{t('common.loading')}</div> : (
          <div className="space-y-4 overflow-y-auto p-5">
            <div className="flex items-start gap-4 pr-8">
              <img src={qr || undefined} alt="QR" className="size-24 rounded-md bg-white p-1" />
              <div className="flex-1">
                <p className="font-mono text-xs text-accent">{d.id}</p>
                <DialogTitle className="flex items-center gap-2 font-display text-xl font-semibold"><TestTube className="size-5 text-accent" />{d.label}</DialogTitle>
                <p className="mt-1 text-sm text-dim">{d.status}</p>
                <Button size="sm" variant="ghost" className="mt-1 px-0" onClick={() => window.open(qr.replace('scale=8', 'scale=14'), '_blank')}><Printer /> {t('sample.printLabel')}</Button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Field label={t('mat.location')} value={s.lab?.equipment.find((e) => e.id === d.location_id)?.name ?? d.location_id} />
              <Field label={t('sample.owner')} value={d.owner} />
              <Field label={t('sample.project')} value={s.lab?.experiments.find((x) => x.id === d.experiment_id)?.title ?? '—'} />
              <Field label={t('sample.collected')} value={fmtDate(d.collected)} />
            </div>
            <form onSubmit={save} className="flex flex-wrap gap-2 rounded-lg border border-line p-3">
              <Select value={loc} onChange={(e) => setLoc(e.target.value)} className="flex-1">
                <option value="">{t('sample.moveTo')}</option>
                {s.lab?.equipment.filter((e) => e.id !== d.location_id).map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
              </Select>
              <Input value={status} onChange={(e) => setStatus(e.target.value)} placeholder={t('sample.newStatus')} className="flex-1" />
              <Button size="sm" type="submit" className="h-9" disabled={!loc && !status}>{t('mat.save')}</Button>
              <Button size="sm" variant="ghost" type="button" className="h-9" onClick={() => { s.set({ sampleId: null }); s.focus(d.location_id) }}><Crosshair /></Button>
            </form>
            <div>
              <p className="mb-2 text-[10px] uppercase tracking-wider text-dim">{t('sample.history')}</p>
              <Timeline logs={d.history} />
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
  const [procedure, setProcedure] = useState<Procedure | null>(null)
  useEffect(() => { if (open) { setEq(s.reportFor ?? ''); setDesc(''); setPriority('medium'); setCategory('fault'); setProcedure(null) } }, [open])
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    const r = await api.post<{ procedure?: Procedure }>('/incidents', { lab_id: s.labId, reporter_id: s.meId, category, priority, description: desc, equipment_id: eq || null, anonymous: anon })
    s.toast(t('report.sent'))
    s.refreshLab(); s.refreshUsers(); s.refreshQuests()
    if (r.procedure) setProcedure(r.procedure)
    else s.set({ reportFor: undefined })
  }
  const aid = s.lab?.points.filter((p) => ['eyewash', 'shower', 'exit', 'firstaid'].includes(p.kind)) ?? []
  return (
    <Dialog open={open} onOpenChange={(o) => !o && s.set({ reportFor: undefined })}>
      <DialogContent className="w-[min(520px,94vw)]">
        {procedure ? (
          <div className="space-y-4 overflow-y-auto p-5">
            <DialogTitle className="flex items-center gap-2 font-display text-lg font-semibold"><AlertOctagon className="size-5 text-accent" /> {t('report.procedureTitle')}</DialogTitle>
            <div className="rounded-xl border-2 border-accent bg-accent/10 p-3 text-sm">
              <p className="font-semibold">{procedure.disclaimer}</p>
              <p className="mt-1 text-xs">{t('report.callNumber', { n: procedure.emergency_number })}</p>
            </div>
            <ol className="list-decimal space-y-1.5 pl-5 text-sm">
              {procedure.steps.map((step, i) => <li key={i}>{step}</li>)}
            </ol>
            {procedure.nearest.length > 0 && (
              <div>
                <p className="mb-1.5 text-[10px] uppercase tracking-wider text-dim">{t('report.nearestPoints')}</p>
                <div className="space-y-1">
                  {procedure.nearest.map((p) => (
                    <div key={p.id} className="flex items-center justify-between rounded-lg border border-line px-3 py-2 text-sm">
                      <span>{p.label}</span><span className="font-mono text-xs text-dim">{p.distance_m !== null ? `${p.distance_m} m` : ''}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <p className="text-xs text-dim">{t('report.notified')}</p>
            <div className="flex gap-2">
              <Button className="flex-1" onClick={() => s.set({ layer: 'safety', reportFor: undefined, equipmentId: null })}>{t('report.showSafety')}</Button>
              <Button variant="ghost" onClick={() => s.set({ reportFor: undefined })}>{t('common.close')}</Button>
            </div>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4 overflow-y-auto p-5">
            <DialogTitle className="flex items-center gap-2 font-display text-lg font-semibold"><ShieldAlert className="size-5 text-accent" /> {t('report.title')}</DialogTitle>
            {priority === 'critical' && (
              <div className="rounded-xl border-2 border-accent bg-accent/10 p-3 text-sm">
                <p className="flex items-center gap-1.5 font-semibold"><AlertOctagon className="size-4 text-accent" /> {t('report.emergencyTitle')}</p>
                <p className="mt-1 text-xs text-fg/90">{t('report.emergencyText', { list: aid.map((p) => p.label).join(', ') })}</p>
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
        )}
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
    const r = await api.get<{ type: string; id: string; lab_id: string; location?: string }>(`/scan/${encodeURIComponent(code)}`)
    if (r.lab_id !== s.labId) await s.selectLab(r.lab_id)
    s.set({ scanOpen: false })
    if (r.type === 'equipment') s.focus(r.id, true)
    else if (r.type === 'material') s.set({ materialId: r.id })
    else {
      s.focus(r.location!)
      s.set({ sampleId: r.id })
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
        s.toast(tr('scan.cameraError'), 'plain')
        setCam(false)
      }
    })()
    return () => { alive = false; stream?.getTracks().forEach((x) => x.stop()) }
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

const LOCAL_TIPS = [1, 2, 3, 4, 5] as const

function OnboardingDialog() {
  const s = useLab()
  const t = useT()
  const lang = useLang((x) => x.lang)
  const [i, setI] = useState(0)
  const [data, setData] = useState<Onboarding | null>(null)
  const me = s.me()
  useEffect(() => {
    if (s.onboardingOpen) api.get<Onboarding>(`/onboarding/${s.meId}`).then(setData).catch(() => setData(null))
  }, [s.onboardingOpen, s.meId, lang])
  const tips = data?.tips.length ? data.tips : LOCAL_TIPS.map((k) => ({ title: t(`onb.${k}.title`), body: t(`onb.${k}.body`) }))
  const total = tips.length + (data ? 1 : 0)
  const close = async () => {
    s.set({ onboardingOpen: false })
    setI(0)
    await api.post(`/onboarding/${s.meId}/complete`, {}).catch(() => null)
    s.refreshUsers()
  }
  const onTeamStep = !!data && i === tips.length
  return (
    <Dialog open={s.onboardingOpen} onOpenChange={(o) => { if (!o) close() }}>
      <DialogContent className="w-[min(520px,94vw)]">
        <div className="overflow-y-auto p-6">
          <p className="font-mono text-[11px] tracking-[0.1em] text-accent">ONBOARDING · {i + 1}/{total}</p>
          {onTeamStep && data ? (
            <>
              <DialogTitle className="mt-2 font-display text-2xl font-semibold">{t('onb.teamTitle')}</DialogTitle>
              {data.mentor && <p className="mt-3 text-sm">{t('onb.mentor', { name: data.mentor.name })}</p>}
              <div className="mt-3 max-h-64 space-y-2 overflow-y-auto">
                {data.who_does_what.map((r) => (
                  <div key={r.id} className="rounded-lg border border-line p-2.5 text-xs">
                    <p className="text-sm font-medium">{r.name} {r.people.length > 0 && <span className="text-xs font-normal text-dim">· {r.people.join(', ')}</span>}</p>
                    <p className="text-dim">{r.description}</p>
                  </div>
                ))}
              </div>
              {data.starter_quests.length > 0 && (
                <p className="mt-3 text-xs text-dim">{t('onb.starter')}: {data.starter_quests.map((q) => q.title).join(' · ')}</p>
              )}
            </>
          ) : (
            <>
              <DialogTitle className="mt-2 font-display text-2xl font-semibold">{i === 0 && me ? t('onb.welcome', { name: me.name.replace('Dr. ', '').split(' ')[0] }) : ''}{tips[i]?.title}</DialogTitle>
              <p className="mt-3 text-sm leading-relaxed text-fg/85">{tips[i]?.body}</p>
            </>
          )}
          <div className="mt-5 flex gap-1">{Array.from({ length: total }).map((_, k) => <span key={k} className={cn('h-1 flex-1 rounded-full', k <= i ? 'bg-accent' : 'bg-white/10')} />)}</div>
          <div className="mt-5 flex justify-between">
            <Button variant="ghost" onClick={close}>{t('onb.skip')}</Button>
            <Button onClick={() => (i < total - 1 ? setI(i + 1) : close())}>{i < total - 1 ? t('onb.next') : t('onb.start')}</Button>
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
      <SampleDialog />
      <ReportDialog />
      <ScanDialog />
      <AdminPanel />
      <OnboardingDialog />
    </>
  )
}
