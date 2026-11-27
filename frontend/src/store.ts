import { create } from 'zustand'
import { api } from '@/lib/api'
import { t, type TKey } from '@/lib/i18n'
import type { Channel, LabDetail, LabSummary, Layer, Message, QuestBoard, Route, User } from '@/types'

type CameraAction = { type: 'rotate'; value: number } | { type: 'zoom'; value: number } | { type: 'reset' } | { type: 'focus'; id: string }
export type CameraCmd = CameraAction & { n: number }

export interface Toast { id: number; text: string; tone?: 'accent' | 'plain' }

const ls = {
  get: <T,>(k: string, fallback: T): T => {
    try {
      const v = localStorage.getItem(k)
      return v ? (JSON.parse(v) as T) : fallback
    } catch {
      return fallback
    }
  },
  set: (k: string, v: unknown) => {
    try {
      localStorage.setItem(k, JSON.stringify(v))
    } catch {
    }
  },
}

interface State {
  users: User[]
  meId: string
  labs: LabSummary[]
  labId: string
  lab: LabDetail | null
  quests: QuestBoard | null
  chatOpen: boolean
  sideOpen: boolean
  sideTab: string
  equipmentId: string | null
  materialId: string | null
  reportFor: string | null | undefined
  adminOpen: boolean
  scanOpen: boolean
  onboardingOpen: boolean
  layer: Layer
  showLabels: boolean
  highlightId: string | null
  route: Route | null
  cameraCmd: CameraCmd | null
  toasts: Toast[]
  channels: Channel[]
  activeChannel: string | null
  messages: Record<string, Message[]>
  unread: Record<string, number>

  me: () => User | undefined
  init: () => Promise<void>
  setMe: (id: string) => void
  selectLab: (id: string) => Promise<void>
  refreshLab: () => Promise<void>
  refreshQuests: () => Promise<void>
  refreshUsers: () => Promise<void>
  loadChannels: () => Promise<void>
  openChannel: (id: string) => Promise<void>
  receive: (m: Message) => void
  set: (p: Partial<State>) => void
  camera: (cmd: CameraAction) => void
  focus: (id: string, open?: boolean) => void
  toast: (text: string, tone?: Toast['tone']) => void
}

let nonce = 0

export const useLab = create<State>((set, get) => ({
  users: [],
  meId: ls.get('smartlab.me', 'u-tomek'),
  labs: [],
  labId: ls.get('smartlab.lab', 'lab-204'),
  lab: null,
  quests: null,
  chatOpen: false,
  sideOpen: typeof window !== 'undefined' && window.innerWidth >= 768,
  sideTab: 'quests',
  equipmentId: null,
  materialId: null,
  reportFor: undefined,
  adminOpen: false,
  scanOpen: false,
  onboardingOpen: !ls.get('smartlab.onboarded', false) && !location.search.includes('tour=0'),
  layer: 'infra',
  showLabels: true,
  highlightId: null,
  route: null,
  cameraCmd: null,
  toasts: [],
  channels: [],
  activeChannel: null,
  messages: {},
  unread: {},

  me: () => get().users.find((u) => u.id === get().meId),

  init: async () => {
    const [users, labs] = await Promise.all([api.get<User[]>('/users'), api.get<LabSummary[]>('/labs')])
    set({ users, labs })
    await get().selectLab(get().labId)
  },

  setMe: (id) => {
    ls.set('smartlab.me', id)
    set({ meId: id, messages: {}, activeChannel: null, route: null })
    get().refreshQuests()
    get().loadChannels()
  },

  selectLab: async (id) => {
    ls.set('smartlab.lab', id)
    set({ labId: id, equipmentId: null, materialId: null, route: null, highlightId: null, activeChannel: null })
    const lab = await api.get<LabDetail>(`/labs/${id}`)
    set({ lab })
    get().camera({ type: 'reset' })
    await Promise.all([get().refreshQuests(), get().loadChannels()])
  },

  refreshLab: async () => {
    const [lab, labs] = await Promise.all([
      api.get<LabDetail>(`/labs/${get().labId}`),
      api.get<LabSummary[]>('/labs'),
    ])
    set({ lab, labs })
  },

  refreshQuests: async () => {
    const quests = await api.get<QuestBoard>(`/quests?lab_id=${get().labId}&user_id=${get().meId}`)
    set({ quests })
  },

  refreshUsers: async () => set({ users: await api.get<User[]>('/users') }),

  loadChannels: async () => {
    const { meId, labId } = get()
    const channels = await api.get<Channel[]>(`/channels?user_id=${meId}&lab_id=${labId}`)
    const read = ls.get<Record<string, number>>(`smartlab.read.${meId}`, {})
    const unread: Record<string, number> = {}
    channels.forEach((c) => {
      if (c.last_id > (read[c.id] ?? 0)) unread[c.id] = 1
    })
    set({ channels, unread })
  },

  openChannel: async (id) => {
    const msgs = await api.get<Message[]>(`/messages?channel=${encodeURIComponent(id)}`)
    const { meId, unread } = get()
    const read = ls.get<Record<string, number>>(`smartlab.read.${meId}`, {})
    read[id] = msgs.at(-1)?.id ?? 0
    ls.set(`smartlab.read.${meId}`, read)
    set({ activeChannel: id, messages: { ...get().messages, [id]: msgs }, unread: { ...unread, [id]: 0 } })
  },

  receive: (m) => {
    const s = get()
    const relevant =
      m.channel === `lab:${s.labId}` ||
      m.channel.startsWith('eq:') ||
      (m.channel.startsWith('dm:') && m.channel.split(':').includes(s.meId))
    if (!relevant) return
    const list = s.messages[m.channel]
    const messages = list ? { ...s.messages, [m.channel]: [...list, m] } : s.messages
    const viewing = s.chatOpen && s.activeChannel === m.channel
    const unread = { ...s.unread }
    if (viewing) {
      const read = ls.get<Record<string, number>>(`smartlab.read.${s.meId}`, {})
      read[m.channel] = m.id
      ls.set(`smartlab.read.${s.meId}`, read)
    } else if (m.sender_id !== s.meId) {
      unread[m.channel] = (unread[m.channel] ?? 0) + 1
    }
    set({ messages, unread })
    if (m.mentions.includes(s.meId) && m.sender_id !== s.meId) s.toast(t('chat.mentioned', { who: m.sender ?? 'SMARTLAB', text: m.text }))
    if (!s.channels.some((c) => c.id === m.channel)) s.loadChannels()
  },

  set: (p) => {
    if ('onboardingOpen' in p && p.onboardingOpen === false) ls.set('smartlab.onboarded', true)
    set(p)
  },

  camera: (cmd) => set({ cameraCmd: { ...cmd, n: ++nonce } }),

  focus: (id, open = false) => {
    set({ highlightId: id, ...(open ? { equipmentId: id } : {}) })
    get().camera({ type: 'focus', id })
  },

  toast: (text, tone = 'accent') => {
    const id = ++nonce
    set({ toasts: [...get().toasts, { id, text, tone }] })
    setTimeout(() => set({ toasts: get().toasts.filter((t) => t.id !== id) }), 4500)
  },
}))

export function connectRealtime() {
  let ws: WebSocket | null = null
  let stopped = false
  const open = () => {
    ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`)
    ws.onmessage = (ev) => {
      const data = JSON.parse(ev.data)
      const s = useLab.getState()
      if (data.type === 'message') s.receive(data.message)
      if (data.type === 'refresh' && data.lab_id === s.labId) {
        s.refreshLab()
        s.refreshUsers()
      }
      if (data.type === 'quests' && data.lab_id === s.labId) s.refreshQuests()
      if (data.type === 'notification' && data.user_id === s.meId && data.kind !== 'mention') s.toast(data.title, 'plain')
      if (data.type === 'incident' && data.lab_id === s.labId) {
        const cat = data.category ? t(`report.cat.${data.category}` as TKey) : ''
        s.toast(`🚨 ${t(`priority.${data.priority}` as TKey).toUpperCase()} — ${data.who ?? t('common.anonymous')}: ${cat} · ${data.where ?? ''}`)
        s.refreshQuests()
      }
    }
    ws.onclose = () => {
      if (!stopped) setTimeout(open, 2000)
    }
  }
  open()
  return () => {
    stopped = true
    ws?.close()
  }
}
