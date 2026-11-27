import { ArrowLeft, ArrowRight, AtSign, Cpu, FileText, FlaskConical, Hash, HelpCircle, ImagePlus, MessageSquarePlus, Package, Paperclip, UserPlus, Users, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Avatar, roleLabel } from '@/components/Hud'
import { Input, Select } from '@/components/ui/input'
import { api } from '@/lib/api'
import { useT } from '@/lib/i18n'
import { cn, fmtTime } from '@/lib/utils'
import { useLab } from '@/store'
import type { Attachment, Channel, Message } from '@/types'

const dmId = (a: string, b: string) => `dm:${[a, b].sort().join(':')}`

export function ChannelIcon({ c }: { c: Channel }) {
  if (c.kind === 'lab') return <Hash className="size-4 text-dim" />
  if (c.kind === 'equipment') return <Cpu className="size-4 text-dim" />
  if (c.kind === 'group') return <Users className="size-4 text-dim" />
  return <AtSign className="size-4 text-dim" />
}

export function MessageExtras({ m }: { m: Message }) {
  const s = useLab()
  const lab = s.lab
  const share = m.share
  const shareName = share && lab
    ? share.type === 'material' ? lab.materials.find((x) => x.id === share.id)?.name
      : share.type === 'sample' ? `${share.id} ${lab.samples.find((x) => x.id === share.id)?.label ?? ''}`
        : lab.equipment.find((x) => x.id === share.id)?.name
    : null
  return (
    <>
      {share && (
        <button onClick={() => share.type === 'material' ? s.set({ materialId: share.id }) : share.type === 'sample' ? s.set({ sampleId: share.id }) : s.focus(share.id, true)}
          className="mt-1 flex cursor-pointer items-center gap-1.5 rounded-lg border border-line bg-canvas-edge px-2 py-1 text-xs text-dim hover:border-accent/60 hover:text-fg">
          {share.type === 'material' ? <Package className="size-3.5 text-accent" /> : share.type === 'sample' ? <FlaskConical className="size-3.5 text-accent" /> : <Cpu className="size-3.5 text-accent" />}
          {shareName ?? share.id}
        </button>
      )}
      {(m.attachments ?? []).map((a) => a.content_type.startsWith('image/') ? (
        <a key={a.id} href={a.url} target="_blank" rel="noreferrer" className="mt-1 block">
          <img src={a.url} alt={a.title} className="max-h-40 rounded-lg border border-line object-cover" />
        </a>
      ) : (
        <a key={a.id} href={a.url} target="_blank" rel="noreferrer" className="mt-1 flex items-center gap-1.5 rounded-lg border border-line bg-canvas-edge px-2 py-1 text-xs text-dim hover:text-fg">
          <FileText className="size-3.5 text-accent" />{a.title}
        </a>
      ))}
    </>
  )
}

export default function ChatDrawer() {
  const s = useLab()
  const t = useT()
  const { chatOpen, channels, activeChannel, messages, unread, users, meId, lab } = s
  const [text, setText] = useState('')
  const [ref, setRef] = useState<string>('')
  const [help, setHelp] = useState(false)
  const [newDm, setNewDm] = useState(false)
  const [atts, setAtts] = useState<Attachment[]>([])
  const [uploading, setUploading] = useState(false)
  const [groupName, setGroupName] = useState('')
  const [groupMembers, setGroupMembers] = useState<string[]>([])
  const [inviting, setInviting] = useState(false)
  const bottom = useRef<HTMLDivElement>(null)
  const current = channels.find((c) => c.id === activeChannel)
  const msgs = activeChannel ? messages[activeChannel] ?? [] : []

  useEffect(() => {
    if (chatOpen && !activeChannel && lab) s.openChannel(`lab:${lab.id}`)
  }, [chatOpen, activeChannel, lab])
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs.length, activeChannel])

  if (!chatOpen || !lab) return null
  const others = users.filter((u) => u.id !== meId)

  const send = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!text.trim() || !activeChannel) return
    const [kind, id] = ref ? ref.split(':') : ['', '']
    await api.post('/messages', {
      channel: activeChannel, sender_id: meId, text, help_request: help,
      equipment_ref: kind === 'machine' ? id : null,
      share: kind && kind !== 'machine' ? { type: kind, id } : null,
      attachments: atts.map((a) => a.id),
    })
    if (help) s.toast(t('chat.helpPosted'))
    setText('')
    setRef('')
    setHelp(false)
    setAtts([])
    if (!channels.some((c) => c.id === activeChannel)) s.loadChannels()
    s.refreshQuests()
  }

  const startDm = (uid: string) => {
    setNewDm(false)
    s.openChannel(dmId(meId, uid))
  }

  const attach = async (file: File) => {
    setUploading(true)
    try {
      const d = await api.upload<{ id: number; title: string; kind: string; content_type: string }>('/documents', {
        file, lab_id: lab.id, kind: file.type.startsWith('image/') ? 'image' : 'auto', process: 'false',
      })
      setAtts((a) => [...a, { id: d.id, title: d.title, kind: d.kind, content_type: d.content_type, url: `/api/documents/${d.id}/download` }])
    } catch (err) {
      s.toast((err as Error).message, 'plain')
    } finally {
      setUploading(false)
    }
  }

  const createGroup = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!groupName.trim()) return
    const c = await api.post<{ id: string }>('/channels', { lab_id: lab.id, name: groupName, members: groupMembers })
    setGroupName('')
    setGroupMembers([])
    setNewDm(false)
    await s.loadChannels()
    s.openChannel(c.id)
  }

  const invite = async (uid: string) => {
    if (!current) return
    await api.post(`/channels/${current.id}/invite`, { user_ids: [uid] })
    setInviting(false)
    s.toast(t('chat.invitedToast', { name: users.find((u) => u.id === uid)?.name ?? uid }))
    await s.loadChannels()
    s.openChannel(current.id)
  }

  return (
    <aside className="pointer-events-auto absolute bottom-0 left-0 top-20 z-30 flex w-[min(380px,100%)] flex-col border-r border-t border-line bg-surface/97 backdrop-blur-md sm:rounded-tr-2xl">
      <div className="flex h-14 items-center gap-2 border-b border-line px-4">
        <h2 className="flex-1 text-base font-semibold">{t('chat.title')}</h2>
        <span className="rounded-md border border-line px-1.5 py-0.5 font-mono text-[10px] text-dim">{lab.code}</span>
        <div className="flex -space-x-2">
          {users.filter((u) => u.online && u.lab_id === lab.id).slice(0, 4).map((u) => (
            <Avatar key={u.id} initials={u.initials} online className="size-7 text-[10px]" />
          ))}
        </div>
        <button onClick={() => s.set({ chatOpen: false })} className="cursor-pointer rounded-lg p-1.5 text-dim hover:bg-hover hover:text-fg max-sm:p-2.5"><X className="size-4" /></button>
      </div>

      <div className="flex gap-1.5 overflow-x-auto border-b border-line px-3 py-2">
        {channels.map((c) => (
          <button key={c.id} onClick={() => s.openChannel(c.id)}
            className={cn('flex shrink-0 cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs transition-colors',
              activeChannel === c.id ? 'border-accent/60 bg-accent/10 text-fg' : 'border-line text-dim hover:text-fg')}>
            <ChannelIcon c={c} />
            <span className="max-w-28 truncate">{c.kind === 'lab' ? t('chat.allLab') : c.title}</span>
            {!!unread[c.id] && activeChannel !== c.id && <span className="size-2 rounded-full bg-accent" />}
          </button>
        ))}
        <button onClick={() => setNewDm(!newDm)} className="flex shrink-0 cursor-pointer items-center gap-1 rounded-lg border border-dashed border-line-strong px-2.5 py-1.5 text-xs text-dim hover:text-fg">
          <MessageSquarePlus className="size-3.5" /> {t('common.new')}
        </button>
      </div>

      {newDm ? (
        <div className="flex-1 overflow-y-auto p-3">
          <button onClick={() => setNewDm(false)} className="mb-2 flex cursor-pointer items-center gap-1 text-xs text-dim hover:text-fg"><ArrowLeft className="size-3.5" /> {t('common.back')}</button>
          <form onSubmit={createGroup} className="mb-4 space-y-2 rounded-xl border border-line p-3">
            <p className="text-xs uppercase tracking-wider text-dim">{t('chat.newGroup')}</p>
            <Input value={groupName} onChange={(e) => setGroupName(e.target.value)} placeholder={t('chat.groupName')} />
            <div className="flex flex-wrap gap-1.5">
              {others.map((u) => (
                <button type="button" key={u.id} onClick={() => setGroupMembers((m) => m.includes(u.id) ? m.filter((x) => x !== u.id) : [...m, u.id])}
                  className={cn('cursor-pointer rounded-md border px-2 py-1 text-[11px]', groupMembers.includes(u.id) ? 'border-accent bg-accent/10 text-accent' : 'border-line text-dim')}>
                  {u.name.replace('Dr. ', '')}
                </button>
              ))}
            </div>
            <button type="submit" disabled={!groupName.trim()} className="w-full cursor-pointer rounded-lg bg-accent py-1.5 text-xs font-medium text-accent-ink disabled:opacity-40">{t('chat.createGroup')}</button>
          </form>
          <p className="mb-2 text-xs uppercase tracking-wider text-dim">{t('chat.directMessage')}</p>
          {others.map((u) => (
            <button key={u.id} onClick={() => startDm(u.id)} className="flex w-full cursor-pointer items-center gap-3 rounded-lg p-2 text-left hover:bg-hover">
              <Avatar initials={u.initials} online={!!u.online} />
              <div><div className="text-sm">{u.name}</div><div className="text-xs text-dim">{roleLabel(u.role)}</div></div>
            </button>
          ))}
          <p className="mb-2 mt-4 text-xs uppercase tracking-wider text-dim">{t('chat.equipmentThread')}</p>
          {lab.equipment.filter((e) => e.kind !== 'bench').map((e) => (
            <button key={e.id} onClick={() => { setNewDm(false); s.openChannel(`eq:${e.id}`) }} className="flex w-full cursor-pointer items-center gap-3 rounded-lg p-2 text-left text-sm hover:bg-hover">
              <Cpu className="size-4 text-dim" /> {e.name}
            </button>
          ))}
        </div>
      ) : (
        <>
          <div className="flex items-center justify-between px-4 pt-3 text-xs text-dim">
            <span>{current?.kind === 'equipment' ? t('chat.deviceDiscussion') : current?.kind === 'dm' ? t('chat.directMessage') : current?.kind === 'group' ? t('chat.group') : activeChannel?.startsWith('dm:') ? t('chat.newConversation') : t('chat.room')}</span>
            {current?.equipment_id && (
              <button onClick={() => s.focus(current.equipment_id!, true)} className="cursor-pointer text-accent hover:underline">{t('chat.showOnMap')}</button>
            )}
            {current?.kind === 'group' && (
              <button onClick={() => setInviting(!inviting)} className="flex cursor-pointer items-center gap-1 text-accent hover:underline"><UserPlus className="size-3.5" />{t('chat.invite')}</button>
            )}
          </div>
          {current?.kind === 'group' && (
            <div className="flex flex-wrap gap-1 px-4 pt-2">
              {(current.members ?? []).map((id) => <Avatar key={id} initials={users.find((u) => u.id === id)?.initials ?? '?'} className="size-6 text-[9px]" />)}
            </div>
          )}
          {inviting && current?.kind === 'group' && (
            <div className="mx-4 mt-2 flex flex-wrap gap-1.5 rounded-lg border border-line p-2">
              {others.filter((u) => !(current.members ?? []).includes(u.id)).map((u) => (
                <button key={u.id} onClick={() => invite(u.id)} className="cursor-pointer rounded-md border border-line px-2 py-1 text-[11px] text-dim hover:border-accent hover:text-fg">+ {u.name.replace('Dr. ', '')}</button>
              ))}
            </div>
          )}
          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
            {msgs.length === 0 && <p className="pt-8 text-center text-sm text-muted">{t('chat.empty')}</p>}
            {msgs.map((m) => {
              const mine = m.sender_id === meId
              const u = users.find((x) => x.id === m.sender_id)
              const eq = m.equipment_ref ? lab.equipment.find((e) => e.id === m.equipment_ref) : null
              return (
                <div key={m.id} className={cn('flex gap-2', mine && 'flex-row-reverse')}>
                  {!mine && <Avatar initials={u?.initials ?? 'SL'} className="size-7 text-[10px]" />}
                  <div className={cn('max-w-[80%]', mine && 'items-end text-right')}>
                    <div className="mb-0.5 flex items-baseline gap-1.5 text-[11px] text-dim" style={{ justifyContent: mine ? 'flex-end' : undefined }}>
                      {!mine && <span className="font-medium text-fg">{m.sender ?? 'SMARTLAB'}</span>}
                      {!mine && u && <span>{roleLabel(u.role)}</span>}
                      <span className="font-mono">{fmtTime(m.at)}</span>
                    </div>
                    <div className={cn('inline-block rounded-2xl px-3 py-2 text-left text-sm',
                      mine ? 'rounded-tr-sm bg-accent text-accent-ink' : 'rounded-tl-sm border border-line bg-elev text-fg')}>
                      {m.help_request ? <span className="mr-1 font-semibold">{t('chat.helpTag')}</span> : null}
                      {m.text}
                    </div>
                    {eq && (
                      <button onClick={() => s.focus(eq.id, true)}
                        className="mt-1 flex cursor-pointer items-center gap-1.5 rounded-lg border border-line bg-canvas-edge px-2 py-1 text-xs text-dim hover:border-accent/60 hover:text-fg">
                        <Cpu className="size-3.5 text-accent" /> {eq.name}
                      </button>
                    )}
                    <MessageExtras m={m} />
                  </div>
                </div>
              )
            })}
            <div ref={bottom} />
          </div>
          <form onSubmit={send} className="space-y-2 border-t border-line p-3">
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <Paperclip className="size-3.5 text-dim" />
              <Select value={ref} onChange={(e) => setRef(e.target.value)} className="h-7 min-w-0 flex-1 text-xs max-sm:h-10 max-sm:basis-[calc(100%-1.75rem)]">
                <option value="">{t('chat.share')}</option>
                <optgroup label={t('chat.shareEquipmentGroup')}>
                  {lab.equipment.map((e) => <option key={e.id} value={`machine:${e.id}`}>{e.name}</option>)}
                </optgroup>
                <optgroup label={t('chat.shareMaterialGroup')}>
                  {lab.materials.map((m) => <option key={m.id} value={`material:${m.id}`}>{m.name}</option>)}
                </optgroup>
                <optgroup label={t('chat.shareSampleGroup')}>
                  {lab.samples.map((x) => <option key={x.id} value={`sample:${x.id}`}>{x.id} {x.label}</option>)}
                </optgroup>
              </Select>
              <label className={cn('flex cursor-pointer items-center gap-1 rounded-md border border-line px-1.5 py-1 text-[10px] text-dim hover:text-fg max-sm:px-2.5 max-sm:py-2 max-sm:text-xs', uploading && 'opacity-50')}>
                <ImagePlus className="size-3" /> {t('chat.attach')}
                <input type="file" className="hidden" disabled={uploading} onChange={(e) => { const f = e.target.files?.[0]; if (f) attach(f); e.target.value = '' }} />
              </label>
              {['@service', '@leader', '@manager'].map((tag) => (
                <button type="button" key={tag} onClick={() => setText((t) => `${t}${t && !t.endsWith(' ') ? ' ' : ''}${tag} `)}
                  className="cursor-pointer rounded-md border border-line px-1.5 py-1 font-mono text-[10px] text-dim hover:text-fg max-sm:px-2.5 max-sm:py-2 max-sm:text-xs">{tag}</button>
              ))}
              {activeChannel?.startsWith('eq:') && (
                <button type="button" onClick={() => setHelp(!help)}
                  className={cn('flex cursor-pointer items-center gap-1 rounded-md border px-1.5 py-1 text-[10px] max-sm:px-2.5 max-sm:py-2 max-sm:text-xs', help ?'border-accent bg-accent/10 text-accent' : 'border-line text-dim')}>
                  <HelpCircle className="size-3" /> {t('chat.askHelp')}
                </button>
              )}
            </div>
            {atts.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {atts.map((a) => (
                  <span key={a.id} className="flex items-center gap-1 rounded-md border border-line bg-canvas-edge px-2 py-0.5 text-[11px] text-dim">
                    <Paperclip className="size-3" />{a.title}
                    <button type="button" onClick={() => setAtts(atts.filter((x) => x.id !== a.id))} className="cursor-pointer hover:text-fg"><X className="size-3" /></button>
                  </span>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <Input value={text} onChange={(e) => setText(e.target.value)} placeholder={t('chat.placeholder')} className="rounded-full max-sm:h-11" />
              <button type="submit" className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full bg-accent text-accent-ink hover:bg-accent-hover max-sm:size-11" aria-label={t('chat.send')}>
                <ArrowRight className="size-4" />
              </button>
            </div>
          </form>
        </>
      )}
    </aside>
  )
}
