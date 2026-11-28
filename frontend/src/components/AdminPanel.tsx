import {
  BellRing, Box, Building2, CalendarClock, Download, Leaf, LayoutDashboard, MapPin, Plus, ScanLine, ShieldAlert, Trash2, Trophy, Upload, Users,
} from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { roleLabel } from '@/components/Hud'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { Input, Select } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { api } from '@/lib/api'
import { useLang, useT, type TKey } from '@/lib/i18n'
import { cn, fmtDate, fmtTime } from '@/lib/utils'
import { useLab } from '@/store'
import type { Challenge, Equipment, Incident, Point, Space } from '@/types'

interface Stats {
  hotspots: { equipment_id: string; name: string; count: number; issue_logs: number }[]
  incidents_open: number; near_misses: number; anonymous_reports: number
  rejection_signals: { title: string; reason: string; count: number }[]
  execution_problems: { quest_id: number; title: string; problem: string }[]
  esg: {
    expiring_flagged: number; expired: number; reorders_planned: number; esg_quests_done: number; est_savings_eur: number
    waste_risk_eur: number; waste_disposed_eur: number; saved_by_using_before_expiry_eur: number; storage_violations: number
  }
  engagement: { active_users: number; users: number; quests_done: number; xp_total: number }
  leaderboard: { name: string; xp: number; role: string }[]
  challenges: Challenge[]
  competence: { user_id: string; name: string; role: string; online: boolean; areas: { area: string; score: number }[]; go_to_for: string[] }[]
}

interface Role { id: string; name: string; access: string; description: string; responsibilities: string[]; people: string[] }
interface Rule { id: string; label: string; points: number; currency: string; active: number }
interface Instance { id: string; label: string; x: number; z: number; w: number; d: number; h: number; matched_asset: string | null; match_iou: number; confidence: number }
interface Reconstruction {
  id: number; status: string; method: string; error: string; at: string
  result: { method?: string; notes?: string[]; points?: number; matched?: number; unmatched?: number; instances?: Instance[] }
}

function useAction() {
  const s = useLab()
  return async <T,>(fn: () => Promise<T>, ok?: string): Promise<T | null> => {
    try {
      const r = await fn()
      if (ok) s.toast(ok)
      return r
    } catch (e) {
      s.toast((e as Error).message, 'plain')
      return null
    }
  }
}

function Section({ title, icon, children, className }: { title: string; icon?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    // min-w-0: a grid item otherwise refuses to shrink below its longest unbreakable line and pushes the dialog wider than a phone.
    <section className={cn('min-w-0 rounded-xl border border-line p-4', className)}>
      <h4 className="mb-3 flex items-center gap-1.5 text-sm font-medium">{icon}{title}</h4>
      {children}
    </section>
  )
}

interface DueInspection {
  equipment_id: string; name: string; kind: 'certificate' | 'service' | 'verification'; due: string
  days_left: number; overdue: boolean; responsible: string | null; title: string
}

function Inspections() {
  const s = useLab()
  const t = useT()
  const run = useAction()
  const lang = useLang((x) => x.lang)
  const [items, setItems] = useState<DueInspection[] | null>(null)
  const load = useCallback(() => {
    api.get<{ items: DueInspection[] }>(`/notifications/inspections?lab_id=${s.labId}`).then((r) => setItems(r.items)).catch(() => setItems([]))
  }, [s.labId, lang])
  useEffect(() => { load() }, [load, s.lab])
  const send = async () => {
    const r = await run(() => api.post<{ notifications: number }>(`/notifications/inspections/run?lab_id=${s.labId}`, {}))
    if (r) s.toast(r.notifications ? t('insp.sent', { n: r.notifications }) : t('insp.nothingNew'))
    s.loadNotifications()
  }
  return (
    <Section title={t('insp.title')} icon={<CalendarClock className="size-4 text-accent" />} className="md:col-span-2">
      {items === null && <p className="text-xs text-muted">{t('common.loading')}</p>}
      {items?.length === 0 && <p className="text-xs text-muted">{t('insp.none')}</p>}
      <div className="space-y-1.5">
        {items?.map((i) => (
          <button key={`${i.equipment_id}-${i.kind}`} onClick={() => { s.set({ adminOpen: false }); s.focus(i.equipment_id, true) }}
            className="flex w-full cursor-pointer items-center gap-2 rounded-lg border border-line px-2.5 py-2 text-left text-xs hover:bg-hover">
            <Badge variant={i.overdue ? 'solid' : i.days_left <= 3 ? 'accent' : 'default'}>{t(`insp.kind.${i.kind}`)}</Badge>
            <span className="min-w-0 flex-1 truncate">{i.name}</span>
            <span className="hidden text-dim sm:inline">{i.responsible ?? '—'}</span>
            <span className={cn('font-mono', i.overdue || i.days_left <= 3 ? 'text-accent' : 'text-dim')}>
              {i.overdue ? t('insp.overdueShort', { n: -i.days_left }) : i.days_left === 0 ? t('insp.todayShort') : t('insp.inDays', { n: i.days_left })}
            </span>
          </button>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] text-muted">{t('insp.auto')}</p>
        <Button size="sm" variant="subtle" onClick={send} disabled={!items?.length}><BellRing /> {t('insp.send')}</Button>
      </div>
    </Section>
  )
}

function Overview() {
  const s = useLab()
  const t = useT()
  const run = useAction()
  const lang = useLang((x) => x.lang)
  const [stats, setStats] = useState<Stats | null>(null)
  const [inc, setInc] = useState<Incident[]>([])
  const [res, setRes] = useState<Record<number, { cause: string; resolution: string }>>({})
  const load = useCallback(() => {
    api.get<Stats>(`/admin/stats?lab_id=${s.labId}`).then(setStats)
    api.get<Incident[]>(`/incidents?lab_id=${s.labId}`).then(setInc)
  }, [s.labId, lang])
  useEffect(() => { load() }, [load, s.lab])
  const resolve = async (id: number) => {
    const r = res[id] ?? { cause: '', resolution: '' }
    await run(() => api.post(`/incidents/${id}/resolve`, { user_id: s.meId, resolution: r.resolution || t('admin.resolvedDefault'), cause: r.cause }), t('admin.resolved'))
    load(); s.refreshLab(); s.refreshQuests()
  }
  if (!stats) return <p className="p-6 text-sm text-dim">{t('common.loading')}</p>
  const open = inc.filter((i) => i.status === 'open')
  const max = Math.max(1, ...stats.hotspots.map((h) => h.count * 2 + h.issue_logs))
  return (
    <div className="grid gap-4 md:grid-cols-2">
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
      <Inspections />
      <Section title={t('admin.escalations')} icon={<ShieldAlert className="size-4 text-accent" />} className="md:col-span-2">
        {open.length === 0 && <p className="text-xs text-muted">{t('admin.nothingOpen')}</p>}
        <div className="space-y-2">
          {open.map((i) => (
            <div key={i.id} className={cn('space-y-2 rounded-xl border p-3', i.priority === 'critical' || i.priority === 'high' ? 'border-accent/50' : 'border-line')}>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={i.priority === 'critical' ? 'solid' : i.priority === 'high' ? 'accent' : 'default'}>{t(`priority.${i.priority}`)}</Badge>
                <p className="flex-1 text-sm">{i.description}</p>
              </div>
              <p className="text-xs text-dim">{t(`report.cat.${i.category}` as TKey)} · {i.equipment ?? t('common.lab')} · {i.reporter} · {fmtDate(i.at)} {fmtTime(i.at)}</p>
              <div className="flex flex-wrap gap-2">
                <Input value={res[i.id]?.cause ?? ''} onChange={(e) => setRes({ ...res, [i.id]: { ...(res[i.id] ?? { resolution: '' }), cause: e.target.value } })} placeholder={t('admin.cause')} className="h-8 min-w-0 flex-1 text-xs max-sm:basis-full" />
                <Input value={res[i.id]?.resolution ?? ''} onChange={(e) => setRes({ ...res, [i.id]: { ...(res[i.id] ?? { cause: '' }), resolution: e.target.value } })} placeholder={t('admin.resolution')} className="h-8 min-w-0 flex-1 text-xs max-sm:basis-full" />
                <Button size="sm" className="max-sm:w-full" onClick={() => resolve(i.id)}>{t('admin.resolve')}</Button>
              </div>
            </div>
          ))}
        </div>
      </Section>
      <Section title={t('admin.hotspots')}>
        {stats.hotspots.map((h) => (
          <button key={h.equipment_id} onClick={() => { s.set({ adminOpen: false, layer: 'social' }); s.focus(h.equipment_id) }} className="mb-2 block w-full cursor-pointer text-left">
            <div className="flex justify-between text-xs"><span>{h.name}</span><span className="font-mono">{t('admin.hotspotCount', { n: h.count, logs: h.issue_logs })}</span></div>
            <div className="mt-1 h-1.5 rounded-full bg-white/10"><div className="h-full rounded-full bg-accent" style={{ width: `${((h.count * 2 + h.issue_logs) / max) * 100}%` }} /></div>
          </button>
        ))}
      </Section>
      <Section title={t('admin.signals')}>
        {stats.rejection_signals.length === 0 && stats.execution_problems.length === 0 && <p className="text-xs text-muted">{t('admin.noSignals')}</p>}
        {stats.rejection_signals.map((r) => (
          <div key={r.title} className="mb-2 rounded-lg border border-accent/30 bg-accent/5 p-2.5 text-xs">
            <p className="font-medium text-fg">{t('admin.rejected', { title: r.title, n: r.count })}</p>
            <p className="text-dim">{t('admin.reason', { reason: r.reason })}</p>
          </div>
        ))}
        {stats.execution_problems.map((p) => (
          <div key={p.quest_id} className="mb-2 rounded-lg border border-line p-2.5 text-xs">
            <p className="font-medium">{t('admin.problemWith', { title: p.title })}</p>
            <p className="text-dim">{p.problem}</p>
          </div>
        ))}
      </Section>
      <Section title={t('admin.esg')} icon={<Leaf className="size-4 text-accent" />}>
        <ul className="space-y-1.5 text-xs">
          {([
            ['admin.esg.flagged', stats.esg.expiring_flagged], ['admin.esg.expired', stats.esg.expired],
            ['admin.esg.reorders', stats.esg.reorders_planned], ['admin.esg.quests', stats.esg.esg_quests_done],
            ['admin.esg.storage', stats.esg.storage_violations], ['admin.esg.risk', `${stats.esg.waste_risk_eur} €`],
            ['admin.esg.disposed', `${stats.esg.waste_disposed_eur} €`], ['admin.esg.saved', `${stats.esg.saved_by_using_before_expiry_eur} €`],
          ] as const).map(([l, v]) => <li key={l} className="flex justify-between border-b border-line pb-1.5"><span className="text-dim">{t(l)}</span><span className="font-mono">{v}</span></li>)}
        </ul>
      </Section>
      <Section title={t('admin.engagement', { active: stats.engagement.active_users, total: stats.engagement.users })}>
        <ul className="space-y-1.5 text-xs">
          {stats.leaderboard.map((u) => <li key={u.name} className="flex justify-between"><span>{u.name} <span className="text-dim">· {roleLabel(u.role)}</span></span><span className="font-mono">{u.xp} XP</span></li>)}
        </ul>
        <p className="mt-2 text-[10px] text-muted">{t('admin.engagementNote')}</p>
      </Section>
      <Section title={t('admin.competence')} icon={<Users className="size-4 text-accent" />} className="md:col-span-2">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {stats.competence.map((c) => (
            <div key={c.user_id} className="rounded-lg border border-line p-2.5 text-xs">
              <p className="text-sm font-medium">{c.name} <span className="text-xs font-normal text-dim">· {roleLabel(c.role)}</span></p>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {c.areas.map((a) => <Badge key={a.area} variant={c.go_to_for.includes(a.area) ? 'accent' : 'default'}>{a.area} {a.score}</Badge>)}
              </div>
            </div>
          ))}
        </div>
        <p className="mt-2 text-[10px] text-muted">{t('admin.engagementNote')}</p>
      </Section>
    </div>
  )
}

function LabsTab() {
  const s = useLab()
  const t = useT()
  const run = useAction()
  const lab = s.lab
  const [form, setForm] = useState({ code: '', name: '', building: '', width: '20', depth: '14' })
  const [model, setModel] = useState<File | null>(null)
  const [manifest, setManifest] = useState<File | null>(null)
  const [importAssets, setImportAssets] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [summary, setSummary] = useState<string | null>(null)
  const [scan, setScan] = useState<File | null>(null)
  const [method, setMethod] = useState('geometric')
  const [recs, setRecs] = useState<Reconstruction[]>([])
  const [fpKey, setFpKey] = useState(0)
  const loadRecs = useCallback(() => { if (lab) api.get<Reconstruction[]>(`/labs/${lab.id}/reconstructions`).then(setRecs) }, [lab?.id])
  useEffect(() => { loadRecs() }, [loadRecs])
  useEffect(() => {
    if (!recs.some((r) => r.status === 'queued' || r.status === 'running')) return
    const h = setTimeout(loadRecs, 1500)
    return () => clearTimeout(h)
  }, [recs, loadRecs])
  if (!lab) return null

  const createLab = async (e: React.FormEvent) => {
    e.preventDefault()
    const r = await run(() => api.post<{ id: string }>('/labs', { code: form.code, name: form.name, building: form.building, width: +form.width, depth: +form.depth }), t('labs.created'))
    if (r) {
      setForm({ code: '', name: '', building: '', width: '20', depth: '14' })
      await s.refreshLabs()
      await s.selectLab(r.id)
    }
  }
  const uploadModel = async () => {
    if (!model) return
    setUploading(true)
    const r = await run(() => api.upload<{ created: string[]; updated: string[]; objects: number; nodes_total: number }>(`/labs/${lab.id}/model`, {
      file: model, manifest, import_assets: String(importAssets),
    }))
    setUploading(false)
    if (r) {
      setSummary(t('labs.modelResult', { objects: r.objects, nodes: r.nodes_total, created: r.created.length, updated: r.updated.length }))
      setModel(null); setManifest(null); setFpKey((k) => k + 1)
      await s.refreshLab()
      s.camera({ type: 'reset' })
    }
  }
  const removeModel = async () => {
    await run(() => api.del(`/labs/${lab.id}/model`), t('labs.modelRemoved'))
    s.refreshLab()
  }
  const startRec = async () => {
    if (!scan) return
    await run(() => api.upload(`/labs/${lab.id}/reconstructions`, { file: scan, method }), t('labs.recStarted'))
    setScan(null)
    loadRecs()
  }
  const accept = async (rec: Reconstruction, inst: Instance) => {
    const id = window.prompt(t('labs.assetIdPrompt'), inst.label.toUpperCase().slice(0, 4) + '-' + inst.id.slice(-3).toUpperCase())
    if (!id) return
    const name = window.prompt(t('labs.assetNamePrompt'), id) ?? id
    const kind = inst.label === 'bench' ? 'bench' : inst.label === 'fume_hood' ? 'hood' : inst.label === 'cabinet_or_freezer' ? 'storage' : 'instrument'
    await run(() => api.post(`/reconstructions/${rec.id}/accept`, { instance_id: inst.id, asset_id: id, name, kind }), t('labs.assetCreated'))
    loadRecs(); s.refreshLab()
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Section title={t('labs.current', { name: lab.name })} icon={<Building2 className="size-4 text-accent" />} className="md:col-span-2">
        <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_280px]">
          <div className="space-y-3 text-sm">
            <p className="text-dim">{t('labs.size', { w: lab.width.toFixed(1), d: lab.depth.toFixed(1) })} · {lab.model_meta ? t('labs.modelLoaded', { name: lab.model_meta.filename ?? 'GLB', n: Object.keys(lab.model_meta.nodes).length }) : t('labs.noModel')}</p>
            <div className="space-y-2 rounded-lg border border-dashed border-line-strong p-3">
              <p className="font-medium">{t('labs.uploadModel')}</p>
              <p className="text-xs text-dim">{t('labs.uploadModelHint')}</p>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <label className="flex cursor-pointer items-center gap-1.5 rounded-md border border-line px-2 py-1.5 hover:bg-hover">
                  <Upload className="size-3.5" />{model ? model.name : t('labs.chooseModel')}
                  <input type="file" accept=".glb,.gltf,.obj,.ply,.stl,.off" className="hidden" onChange={(e) => setModel(e.target.files?.[0] ?? null)} />
                </label>
                <label className="flex cursor-pointer items-center gap-1.5 rounded-md border border-line px-2 py-1.5 hover:bg-hover">
                  <Upload className="size-3.5" />{manifest ? manifest.name : t('labs.chooseManifest')}
                  <input type="file" accept=".json" className="hidden" onChange={(e) => setManifest(e.target.files?.[0] ?? null)} />
                </label>
                <label className="flex items-center gap-1.5"><Switch checked={importAssets} onCheckedChange={setImportAssets} /> {t('labs.importAssets')}</label>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={uploadModel} disabled={!model || uploading}><Box /> {uploading ? t('docs.uploading') : t('labs.upload')}</Button>
                {lab.model_meta && <Button size="sm" variant="ghost" onClick={removeModel}><Trash2 /> {t('labs.removeModel')}</Button>}
              </div>
              {summary && <p className="text-xs text-accent">{summary}</p>}
            </div>
            <div className="flex flex-wrap gap-2 text-xs">
              <a className="flex items-center gap-1 rounded-md border border-line px-2 py-1.5 text-dim hover:text-fg" href={`/api/labs/${lab.id}/export/model.glb`}><Download className="size-3.5" />{t('labs.exportGlb')}</a>
              <a className="flex items-center gap-1 rounded-md border border-line px-2 py-1.5 text-dim hover:text-fg" href={`/api/labs/${lab.id}/export/pointcloud.ply`}><Download className="size-3.5" />{t('labs.exportPly')}</a>
            </div>
          </div>
          <div>
            <p className="mb-1 text-[10px] uppercase tracking-wider text-dim">{t('labs.floorplan')}</p>
            <img key={fpKey} src={`/api/labs/${lab.id}/floorplan?format=svg&v=${fpKey}-${lab.equipment.length}`} alt="floor plan" className="w-full rounded-lg border border-line" />
          </div>
        </div>
      </Section>
      <Section title={t('labs.reconstruction')} icon={<ScanLine className="size-4 text-accent" />} className="md:col-span-2">
        <p className="mb-2 text-xs text-dim">{t('labs.reconstructionHint')}</p>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <label className="flex cursor-pointer items-center gap-1.5 rounded-md border border-line px-2 py-1.5 hover:bg-hover">
            <Upload className="size-3.5" />{scan ? scan.name : t('labs.chooseScan')}
            <input type="file" accept=".ply,.xyz,.pcd,.glb,.obj,.txt,.csv" className="hidden" onChange={(e) => setScan(e.target.files?.[0] ?? null)} />
          </label>
          <Select value={method} onChange={(e) => setMethod(e.target.value)} className="h-8 text-xs">
            <option value="geometric">{t('labs.method.geometric')}</option>
            <option value="sam3d">SAM-3D Objects</option>
            <option value="openpcseg">OpenPCSeg</option>
          </Select>
          <Button size="sm" onClick={startRec} disabled={!scan}>{t('labs.runSegmentation')}</Button>
        </div>
        <div className="mt-3 space-y-3">
          {recs.slice(0, 3).map((r) => (
            <div key={r.id} className="rounded-lg border border-line p-3 text-xs">
              <p className="font-medium">#{r.id} · {r.result.method ?? r.method} · {t(`labs.status.${r.status}` as TKey)} · {fmtDate(r.at)} {fmtTime(r.at)}</p>
              {r.error && <p className="text-accent">{r.error}</p>}
              {r.result.notes?.map((n, i) => <p key={i} className="text-dim">{n}</p>)}
              {r.status === 'done' && (
                <>
                  <p className="mt-1 text-dim">{t('labs.recSummary', { points: r.result.points ?? 0, matched: r.result.matched ?? 0, unmatched: r.result.unmatched ?? 0 })}</p>
                  <div className="mt-2 max-h-48 overflow-auto rounded border border-line">
                    <table className="w-full min-w-[480px] text-left">
                      <thead className="text-[10px] uppercase text-dim"><tr><th className="p-1.5">{t('labs.col.label')}</th><th>x,z</th><th>w×d×h</th><th>{t('labs.col.match')}</th><th /></tr></thead>
                      <tbody>
                        {(r.result.instances ?? []).filter((i) => i.label !== 'wall').map((i) => (
                          <tr key={i.id} className="border-t border-line">
                            <td className="p-1.5">{t(`seg.${i.label}` as TKey)}</td>
                            <td className="font-mono">{i.x},{i.z}</td>
                            <td className="font-mono">{i.w}×{i.d}×{i.h}</td>
                            <td>{i.matched_asset ? <Badge variant="accent">{i.matched_asset}</Badge> : <span className="text-muted">—</span>}</td>
                            <td className="text-right">{!i.matched_asset && <Button size="sm" variant="ghost" onClick={() => accept(r, i)}><Plus /></Button>}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      </Section>
      <SpacesEditor />
      <PointsEditor />
      <AssetsEditor />
      <Section title={t('labs.create')} icon={<Plus className="size-4 text-accent" />}>
        <form onSubmit={createLab} className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder={t('labs.code')} required />
            <Input value={form.building} onChange={(e) => setForm({ ...form, building: e.target.value })} placeholder={t('labs.building')} />
          </div>
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder={t('labs.name')} required />
          <div className="grid grid-cols-2 gap-2">
            <Input type="number" step="any" value={form.width} onChange={(e) => setForm({ ...form, width: e.target.value })} placeholder={t('labs.width')} />
            <Input type="number" step="any" value={form.depth} onChange={(e) => setForm({ ...form, depth: e.target.value })} placeholder={t('labs.depth')} />
          </div>
          <Button size="sm" type="submit">{t('labs.createButton')}</Button>
        </form>
      </Section>
    </div>
  )
}

function SpacesEditor() {
  const s = useLab()
  const t = useT()
  const run = useAction()
  const lab = s.lab!
  const [f, setF] = useState({ name: '', x: '', z: '', w: '3', d: '3', hazard: '', roles: '' })
  const save = async (sp: Space, patch: Partial<Space>) => {
    const next = { ...sp, ...patch }
    await run(() => api.put(`/labs/${lab.id}/spaces/${sp.id}`, {
      id: sp.id, name: next.name, x: next.x, z: next.z, w: next.w, d: next.d, kind: next.kind, hazard: next.hazard,
      restricted: next.restricted, closed: next.closed, access_roles: next.access_roles,
    }))
    s.refreshLab()
  }
  const add = async (e: React.FormEvent) => {
    e.preventDefault()
    const id = `z-${Date.now().toString(36)}`
    await run(() => api.put(`/labs/${lab.id}/spaces/${id}`, {
      id, name: f.name, x: +f.x, z: +f.z, w: +f.w, d: +f.d, hazard: f.hazard, restricted: f.roles ? 1 : 0,
      access_roles: f.roles ? f.roles.split(',').map((r) => r.trim()).filter(Boolean) : [],
    }), t('labs.saved'))
    setF({ name: '', x: '', z: '', w: '3', d: '3', hazard: '', roles: '' })
    s.refreshLab()
  }
  return (
    <Section title={t('labs.spaces')} icon={<ShieldAlert className="size-4 text-accent" />}>
      <div className="space-y-2">
        {lab.spaces.map((sp) => (
          <div key={sp.id} className="flex flex-wrap items-center gap-2 rounded-lg border border-line p-2 text-xs">
            <span className="flex-1 font-medium">{sp.name}{sp.hazard && <span className="font-normal text-dim"> · {sp.hazard}</span>}</span>
            <label className="flex items-center gap-1">{t('labs.closed')} <Switch checked={!!sp.closed} onCheckedChange={(v) => save(sp, { closed: v ? 1 : 0 })} /></label>
            <label className="flex items-center gap-1">{t('labs.restricted')} <Switch checked={!!sp.restricted} onCheckedChange={(v) => save(sp, { restricted: v ? 1 : 0 })} /></label>
            <button onClick={async () => { await run(() => api.del(`/labs/${lab.id}/spaces/${sp.id}`)); s.refreshLab() }} className="cursor-pointer text-dim hover:text-fg"><Trash2 className="size-3.5" /></button>
            {!!sp.restricted && <p className="w-full text-[11px] text-dim">{t('labs.allowedRoles')}: {sp.access_roles.map(roleLabel).join(', ') || '—'}</p>}
          </div>
        ))}
      </div>
      <form onSubmit={add} className="mt-3 grid grid-cols-3 gap-2">
        <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder={t('labs.spaceName')} className="col-span-3" required />
        <Input type="number" step="any" value={f.x} onChange={(e) => setF({ ...f, x: e.target.value })} placeholder="x" required />
        <Input type="number" step="any" value={f.z} onChange={(e) => setF({ ...f, z: e.target.value })} placeholder="z" required />
        <Input value={f.hazard} onChange={(e) => setF({ ...f, hazard: e.target.value })} placeholder={t('labs.hazard')} />
        <Input type="number" step="any" value={f.w} onChange={(e) => setF({ ...f, w: e.target.value })} placeholder="w" />
        <Input type="number" step="any" value={f.d} onChange={(e) => setF({ ...f, d: e.target.value })} placeholder="d" />
        <Input value={f.roles} onChange={(e) => setF({ ...f, roles: e.target.value })} placeholder={t('labs.rolesPlaceholder')} />
        <Button size="sm" type="submit" className="col-span-3">{t('labs.addSpace')}</Button>
      </form>
    </Section>
  )
}

const POINT_KINDS = ['exit', 'eyewash', 'shower', 'firstaid', 'extinguisher'] as const

function PointsEditor() {
  const s = useLab()
  const t = useT()
  const run = useAction()
  const lab = s.lab!
  const [f, setF] = useState({ kind: 'exit', label: '', x: '', z: '' })
  const savePoints = async (points: Point[]) => {
    await run(() => api.patch(`/labs/${lab.id}`, { points }), t('labs.saved'))
    s.refreshLab()
  }
  return (
    <Section title={t('labs.points')} icon={<MapPin className="size-4 text-accent" />}>
      <div className="space-y-1">
        {lab.points.map((p) => (
          <div key={p.id} className="flex items-center gap-2 rounded-lg border border-line px-2 py-1.5 text-xs">
            <span className="w-24 text-dim">{t(`point.${p.kind}` as TKey)}</span>
            <span className="flex-1">{p.label}</span>
            <span className="font-mono text-dim">{p.x}, {p.z}</span>
            <button onClick={() => savePoints(lab.points.filter((x) => x.id !== p.id))} className="cursor-pointer text-dim hover:text-fg"><Trash2 className="size-3.5" /></button>
          </div>
        ))}
      </div>
      <form className="mt-3 grid grid-cols-4 gap-2" onSubmit={(e) => {
        e.preventDefault()
        savePoints([...lab.points, { id: `p-${Date.now().toString(36)}`, kind: f.kind, label: f.label || t(`point.${f.kind}` as TKey), x: +f.x, z: +f.z }])
        setF({ kind: 'exit', label: '', x: '', z: '' })
      }}>
        <Select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} className="col-span-2">
          {POINT_KINDS.map((k) => <option key={k} value={k}>{t(`point.${k}`)}</option>)}
        </Select>
        <Input type="number" step="any" value={f.x} onChange={(e) => setF({ ...f, x: e.target.value })} placeholder="x" required />
        <Input type="number" step="any" value={f.z} onChange={(e) => setF({ ...f, z: e.target.value })} placeholder="z" required />
        <Input value={f.label} onChange={(e) => setF({ ...f, label: e.target.value })} placeholder={t('labs.pointLabel')} className="col-span-3" />
        <Button size="sm" type="submit" className="h-9">{t('labs.add')}</Button>
      </form>
    </Section>
  )
}

const KINDS = ['instrument', 'bench', 'hood', 'freezer', 'storage'] as const

function AssetsEditor() {
  const s = useLab()
  const t = useT()
  const run = useAction()
  const lab = s.lab!
  const [edit, setEdit] = useState<Record<string, Partial<Equipment>>>({})
  const [f, setF] = useState({ id: '', name: '', kind: 'instrument', category: '', x: '', z: '', w: '1', d: '1', h: '1', storage_class: '' })
  const save = async (a: Equipment) => {
    const patch = edit[a.id]
    if (!patch) return
    await run(() => api.patch(`/assets/${a.id}`, patch), t('labs.saved'))
    setEdit({ ...edit, [a.id]: undefined as never })
    s.refreshLab()
  }
  const add = async (e: React.FormEvent) => {
    e.preventDefault()
    await run(() => api.post(`/labs/${lab.id}/assets`, {
      id: f.id.toUpperCase(), name: f.name, kind: f.kind, category: f.category || t('labs.defaultCategory'),
      x: +f.x, z: +f.z, w: +f.w, d: +f.d, h: +f.h, storage_class: f.storage_class || null,
    }), t('labs.assetCreated'))
    setF({ id: '', name: '', kind: 'instrument', category: '', x: '', z: '', w: '1', d: '1', h: '1', storage_class: '' })
    s.refreshLab()
  }
  const num = (a: Equipment, k: 'x' | 'z' | 'w' | 'd' | 'h') => (
    <Input type="number" step="any" className="h-7 w-16 px-1.5 text-xs" value={String(edit[a.id]?.[k] ?? a[k])}
      onChange={(e) => setEdit({ ...edit, [a.id]: { ...(edit[a.id] ?? {}), [k]: +e.target.value } })} />
  )
  return (
    <Section title={t('labs.assets', { n: lab.equipment.length })} icon={<Box className="size-4 text-accent" />} className="md:col-span-2">
      <div className="max-h-72 overflow-auto rounded-lg border border-line">
        <table className="w-full min-w-[560px] text-left text-xs">
          <thead className="sticky top-0 bg-surface text-[10px] uppercase text-dim"><tr><th className="p-1.5">ID</th><th>{t('labs.name')}</th><th>{t('labs.kind')}</th><th>x</th><th>z</th><th>w</th><th>d</th><th>h</th><th /></tr></thead>
          <tbody>
            {lab.equipment.map((a) => (
              <tr key={a.id} className="border-t border-line">
                <td className="p-1.5 font-mono">{a.id}</td>
                <td>{a.name}</td>
                <td className="text-dim">{t(`kind.${a.kind}` as TKey)}</td>
                <td>{num(a, 'x')}</td><td>{num(a, 'z')}</td><td>{num(a, 'w')}</td><td>{num(a, 'd')}</td><td>{num(a, 'h')}</td>
                <td className="whitespace-nowrap text-right">
                  {edit[a.id] && <Button size="sm" variant="ghost" onClick={() => save(a)}>{t('mat.save')}</Button>}
                  <Button size="sm" variant="ghost" onClick={async () => { if (window.confirm(t('labs.confirmDelete', { id: a.id }))) { await run(() => api.del(`/assets/${a.id}`)); s.refreshLab() } }}><Trash2 /></Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form onSubmit={add} className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
        <Input value={f.id} onChange={(e) => setF({ ...f, id: e.target.value })} placeholder="ID (HPLC-05)" required />
        <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder={t('labs.name')} required className="sm:col-span-2" />
        <Select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
          {KINDS.map((k) => <option key={k} value={k}>{t(`kind.${k}`)}</option>)}
        </Select>
        <Input value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} placeholder={t('labs.category')} />
        {(['x', 'z', 'w', 'd', 'h'] as const).map((k) => (
          <Input key={k} type="number" step="any" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} placeholder={k} required />
        ))}
        {f.kind === 'storage' || f.kind === 'freezer' ? (
          <Select value={f.storage_class} onChange={(e) => setF({ ...f, storage_class: e.target.value })} className="sm:col-span-2">
            <option value="">{t('labs.storageClass')}</option>
            {['general', 'flammables', 'acids', 'cold', 'frozen'].map((c) => <option key={c} value={c}>{t(`storage.${c}` as TKey)}</option>)}
          </Select>
        ) : <span className="hidden sm:block sm:col-span-2" />}
        <Button size="sm" type="submit" className="h-9 sm:col-span-3">{t('labs.addAsset')}</Button>
      </form>
    </Section>
  )
}

function PeopleTab() {
  const s = useLab()
  const t = useT()
  const run = useAction()
  const [roles, setRoles] = useState<Role[]>([])
  const [f, setF] = useState({ name: '', role: 'intern', mentor_id: '' })
  useEffect(() => { api.get<Role[]>('/roles').then(setRoles) }, [s.users.length])
  const update = async (uid: string, patch: Record<string, unknown>) => {
    await run(() => api.patch(`/users/${uid}`, patch), t('labs.saved'))
    s.refreshUsers()
  }
  const add = async (e: React.FormEvent) => {
    e.preventDefault()
    const id = 'u-' + f.name.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
    await run(() => api.post('/users', { id, name: f.name, role: f.role, lab_id: s.labId, mentor_id: f.mentor_id || null }), t('people.created'))
    setF({ name: '', role: 'intern', mentor_id: '' })
    s.refreshUsers()
  }
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Section title={t('people.users')} icon={<Users className="size-4 text-accent" />} className="md:col-span-2">
        <div className="max-h-80 overflow-auto rounded-lg border border-line">
          <table className="w-full min-w-[560px] text-left text-xs">
            <thead className="sticky top-0 bg-surface text-[10px] uppercase text-dim"><tr><th className="p-1.5">{t('labs.name')}</th><th>{t('people.role')}</th><th>{t('people.access')}</th><th>{t('people.mentor')}</th><th>{t('people.skills')}</th><th>XP</th></tr></thead>
            <tbody>
              {s.users.map((u) => (
                <tr key={u.id} className="border-t border-line">
                  <td className="p-1.5">{u.name}</td>
                  <td><Select className="h-7 text-xs" value={u.role} onChange={(e) => update(u.id, { role: e.target.value })}>{roles.map((r) => <option key={r.id} value={r.id}>{roleLabel(r.id)}</option>)}</Select></td>
                  <td><Select className="h-7 text-xs" value={u.access} onChange={(e) => update(u.id, { access: e.target.value })}>{(['worker', 'leader', 'admin'] as const).map((a) => <option key={a} value={a}>{t(`access.${a}`)}</option>)}</Select></td>
                  <td><Select className="h-7 text-xs" value={(u as unknown as { mentor_id?: string }).mentor_id ?? ''} onChange={(e) => update(u.id, { mentor_id: e.target.value || null })}><option value="">—</option>{s.users.filter((x) => x.id !== u.id).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</Select></td>
                  <td><Input className="h-7 w-44 text-xs" defaultValue={u.skills.join(', ')} onBlur={(e) => { const skills = e.target.value.split(',').map((x) => x.trim().toLowerCase()).filter(Boolean); if (skills.join(',') !== u.skills.join(',')) update(u.id, { skills }) }} /></td>
                  <td className="font-mono">{u.xp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <form onSubmit={add} className="mt-3 flex flex-wrap gap-2">
          <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder={t('people.fullName')} className="flex-1" required />
          <Select value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>{roles.map((r) => <option key={r.id} value={r.id}>{roleLabel(r.id)}</option>)}</Select>
          <Select value={f.mentor_id} onChange={(e) => setF({ ...f, mentor_id: e.target.value })}><option value="">{t('people.mentor')}</option>{s.users.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</Select>
          <Button size="sm" type="submit" className="h-9"><Plus /> {t('people.add')}</Button>
        </form>
      </Section>
      {roles.map((r) => (
        <Section key={r.id} title={`${roleLabel(r.id)} · ${t(`access.${r.access}` as TKey)}`}>
          <p className="text-xs text-dim">{r.description}</p>
          <ul className="mt-2 list-disc space-y-0.5 pl-4 text-xs">{r.responsibilities.map((x) => <li key={x}>{x}</li>)}</ul>
          <p className="mt-2 text-[11px] text-muted">{r.people.join(', ') || '—'}</p>
        </Section>
      ))}
    </div>
  )
}

function PointsTab() {
  const s = useLab()
  const t = useT()
  const run = useAction()
  const [rules, setRules] = useState<Rule[]>([])
  const [challenges, setChallenges] = useState<Challenge[]>([])
  const today = new Date().toISOString().slice(0, 10)
  const week = new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10)
  const [f, setF] = useState({ title: '', metric: 'expiring_reagents_flagged', target: '3', starts: today, ends: week, reward_xp: '50' })
  const load = useCallback(() => {
    api.get<Rule[]>('/point-rules').then(setRules)
    api.get<Challenge[]>(`/challenges?lab_id=${s.labId}`).then(setChallenges)
  }, [s.labId])
  useEffect(() => { load() }, [load])
  const saveRule = async (r: Rule, patch: Partial<Rule>) => {
    await run(() => api.put(`/point-rules/${r.id}`, patch), t('labs.saved'))
    load()
  }
  const addChallenge = async (e: React.FormEvent) => {
    e.preventDefault()
    await run(() => api.post('/challenges', { lab_id: s.labId, title: f.title, metric: f.metric, target: +f.target, starts: f.starts, ends: f.ends, reward_xp: +f.reward_xp }), t('points.challengeCreated'))
    setF({ ...f, title: '' })
    load(); s.refreshQuests()
  }
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Section title={t('points.rules')} icon={<Trophy className="size-4 text-accent" />}>
        <p className="mb-2 text-xs text-dim">{t('points.rulesHint')}</p>
        <div className="space-y-1.5">
          {rules.map((r) => (
            <div key={r.id} className="flex items-center gap-2 text-xs">
              <Switch checked={!!r.active} onCheckedChange={(v) => saveRule(r, { active: v ? 1 : 0 })} />
              <span className="flex-1">{r.label}</span>
              <Input type="number" className="h-7 w-20 text-xs" defaultValue={r.points} onBlur={(e) => { if (+e.target.value !== r.points) saveRule(r, { points: +e.target.value }) }} />
              <Select className="h-7 text-xs" value={r.currency} onChange={(e) => saveRule(r, { currency: e.target.value })}>
                <option value="xp">XP</option><option value="esg">ESG</option><option value="social">{t('points.social')}</option>
              </Select>
            </div>
          ))}
        </div>
      </Section>
      <Section title={t('points.challenges')} icon={<Users className="size-4 text-accent" />}>
        <div className="space-y-2">
          {challenges.map((c) => (
            <div key={c.id} className="rounded-lg border border-line p-2.5 text-xs">
              <div className="flex items-center justify-between"><span className="font-medium">{c.title}</span>{c.completed ? <Badge variant="solid">{t('points.completed')}</Badge> : c.active ? <Badge variant="accent">{t('points.active')}</Badge> : <Badge>{t('points.inactive')}</Badge>}</div>
              <div className="mt-1.5 flex items-center gap-2"><div className="h-1 flex-1 rounded-full bg-white/10"><div className="h-full rounded-full bg-accent" style={{ width: `${c.progress * 100}%` }} /></div><span className="font-mono">{c.value}/{c.target}</span></div>
              <p className="mt-1 text-dim">{t(`metric.${c.metric}` as TKey)}</p>
            </div>
          ))}
        </div>
        <form onSubmit={addChallenge} className="mt-3 grid grid-cols-2 gap-2">
          <Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder={t('points.challengeTitle')} className="col-span-2" required />
          <Select value={f.metric} onChange={(e) => setF({ ...f, metric: e.target.value })} className="col-span-2">
            {['expiring_reagents_flagged', 'esg_quests', 'near_miss_reports', 'help_quests', 'zero_expired'].map((m) => <option key={m} value={m}>{t(`metric.${m}` as TKey)}</option>)}
          </Select>
          <Input type="number" value={f.target} onChange={(e) => setF({ ...f, target: e.target.value })} placeholder={t('points.target')} />
          <Input type="number" value={f.reward_xp} onChange={(e) => setF({ ...f, reward_xp: e.target.value })} placeholder="XP" />
          <Input type="date" value={f.starts} onChange={(e) => setF({ ...f, starts: e.target.value })} />
          <Input type="date" value={f.ends} onChange={(e) => setF({ ...f, ends: e.target.value })} />
          <Button size="sm" type="submit" className="col-span-2">{t('points.addChallenge')}</Button>
        </form>
      </Section>
    </div>
  )
}

export default function AdminPanel() {
  const s = useLab()
  const t = useT()
  const me = s.me()
  const isAdmin = me?.access === 'admin'
  return (
    <Dialog open={s.adminOpen} onOpenChange={(o) => s.set({ adminOpen: o })}>
      <DialogContent className="w-[min(1100px,97vw)]">
        <div className="border-b border-line p-5 pr-14 max-sm:p-4 max-sm:pr-14">
          <DialogTitle className="font-display text-xl font-semibold max-sm:text-lg">{t('admin.title', { lab: s.lab?.name ?? '' })}</DialogTitle>
          <p className="text-xs text-dim">{t('admin.subtitle')}</p>
        </div>
        <Tabs value={s.adminTab} onValueChange={(v) => s.set({ adminTab: v })} className="flex min-h-0 flex-1 flex-col">
          <div className="px-5 pt-3 max-sm:px-4">
            <TabsList className="w-full">
              <TabsTrigger value="overview"><LayoutDashboard /> {t('admin.tab.overview')}</TabsTrigger>
              {isAdmin && <TabsTrigger value="labs"><Building2 /> {t('admin.tab.labs')}</TabsTrigger>}
              {isAdmin && <TabsTrigger value="people"><Users /> {t('admin.tab.people')}</TabsTrigger>}
              <TabsTrigger value="points"><Trophy /> {t('admin.tab.points')}</TabsTrigger>
            </TabsList>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-5 max-sm:p-4">
            <TabsContent value="overview"><Overview /></TabsContent>
            {isAdmin && <TabsContent value="labs"><LabsTab /></TabsContent>}
            {isAdmin && <TabsContent value="people"><PeopleTab /></TabsContent>}
            <TabsContent value="points"><PointsTab /></TabsContent>
          </div>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}
