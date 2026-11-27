import { ArrowLeft, ArrowRight, AtSign, Cpu, Hash, HelpCircle, MessageSquarePlus, Paperclip, Users, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Avatar, roleLabel } from '@/components/Hud'
import { Input, Select } from '@/components/ui/input'
import { api } from '@/lib/api'
import { useT } from '@/lib/i18n'
import { cn, fmtTime } from '@/lib/utils'
import { useLab } from '@/store'
import type { Channel } from '@/types'

const dmId = (a: string, b: string) => `dm:${[a, b].sort().join(':')}`

export function ChannelIcon({ c }: { c: Channel }) {
  if (c.kind === 'lab') return <Hash className="size-4 text-dim" />
  if (c.kind === 'equipment') return <Cpu className="size-4 text-dim" />
  if (c.kind === 'group') return <Users className="size-4 text-dim" />
  return <AtSign className="size-4 text-dim" />
}

export default function ChatDrawer() {
  const s = useLab()
  const t = useT()
  const { chatOpen, channels, activeChannel, messages, unread, users, meId, lab } = s
  const [text, setText] = useState('')
  const [ref, setRef] = useState<string>('')
  const [help, setHelp] = useState(false)
  const [newDm, setNewDm] = useState(false)
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
    await api.post('/messages', {
      channel: activeChannel, sender_id: meId, text, equipment_ref: ref || null, help_request: help,
    })
    if (help) s.toast(t('chat.helpPosted'))
    setText('')
    setRef('')
    setHelp(false)
    if (!channels.some((c) => c.id === activeChannel)) s.loadChannels()
    s.refreshQuests()
  }

  const startDm = (uid: string) => {
    setNewDm(false)
    s.openChannel(dmId(meId, uid))
  }

  return (
    <aside className="pointer-events-auto absolute bottom-0 left-0 top-20 z-30 flex w-[min(380px,100vw)] flex-col border-r border-t border-line bg-surface/97 backdrop-blur-md sm:rounded-tr-2xl">
      <div className="flex h-14 items-center gap-2 border-b border-line px-4">
        <h2 className="flex-1 text-base font-semibold">{t('chat.title')}</h2>
        <span className="rounded-md border border-line px-1.5 py-0.5 font-mono text-[10px] text-dim">{lab.code}</span>
        <div className="flex -space-x-2">
          {users.filter((u) => u.online && u.lab_id === lab.id).slice(0, 4).map((u) => (
            <Avatar key={u.id} initials={u.initials} online className="size-7 text-[10px]" />
          ))}
        </div>
        <button onClick={() => s.set({ chatOpen: false })} className="cursor-pointer rounded-lg p-1.5 text-dim hover:bg-hover hover:text-fg"><X className="size-4" /></button>
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
          </div>
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
                  </div>
                </div>
              )
            })}
            <div ref={bottom} />
          </div>
          <form onSubmit={send} className="space-y-2 border-t border-line p-3">
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <Paperclip className="size-3.5 text-dim" />
              <Select value={ref} onChange={(e) => setRef(e.target.value)} className="h-7 flex-1 text-xs">
                <option value="">{t('chat.shareEquipment')}</option>
                {lab.equipment.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
              </Select>
              {['@service', '@leader', '@manager'].map((tag) => (
                <button type="button" key={tag} onClick={() => setText((t) => `${t}${t && !t.endsWith(' ') ? ' ' : ''}${tag} `)}
                  className="cursor-pointer rounded-md border border-line px-1.5 py-1 font-mono text-[10px] text-dim hover:text-fg">{tag}</button>
              ))}
              {activeChannel?.startsWith('eq:') && (
                <button type="button" onClick={() => setHelp(!help)}
                  className={cn('flex cursor-pointer items-center gap-1 rounded-md border px-1.5 py-1 text-[10px]', help ? 'border-accent bg-accent/10 text-accent' : 'border-line text-dim')}>
                  <HelpCircle className="size-3" /> {t('chat.askHelp')}
                </button>
              )}
            </div>
            <div className="flex gap-2">
              <Input value={text} onChange={(e) => setText(e.target.value)} placeholder={t('chat.placeholder')} className="rounded-full" />
              <button type="submit" className="flex size-9 shrink-0 cursor-pointer items-center justify-center rounded-full bg-accent text-accent-ink hover:bg-accent-hover" aria-label={t('chat.send')}>
                <ArrowRight className="size-4" />
              </button>
            </div>
          </form>
        </>
      )}
    </aside>
  )
}
