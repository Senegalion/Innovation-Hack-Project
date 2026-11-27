export type Status = 'ok' | 'maint' | 'alert' | 'off'
export type Layer = 'infra' | 'inventory' | 'safety' | 'social' | 'quests'

export interface Badge { name: string; icon: string; desc: string; count: number }
export interface User {
  id: string; name: string; initials: string; role: string; access: 'admin' | 'leader' | 'worker'
  skills: string[]; xp: number; online: number; lab_id: string
  level: number; level_progress: number; quests_done: number; badges: Badge[]
}

export interface LabSummary {
  id: string; code: string; name: string; building: string; manager: string; alerts: number; maint: number
}

export interface Point { id: string; kind: string; label: string; x: number; z: number }
export interface Zone { id: string; label: string; x: number; z: number; w: number; d: number }

export interface Equipment {
  id: string; lab_id: string; name: string; category: string; kind: string; status: Status
  x: number; z: number; w: number; d: number; h: number; serial: string
  responsible_id: string | null; responsible: string | null
  last_check: string | null; uncertainty: string; last_service: string | null; next_service: string | null
  cert_expiry: string | null; reading: string; manual: string; notes: string
  last_used_by?: string | null; last_serviced_by?: string | null; open_incidents?: number
}

export interface Forecast {
  planned_use_30d: number; projected_after_plan: number; below_min_on: string | null; runs_out_on: string | null
  order_by: string | null; days_to_expiry: number | null; alerts: string[]
}

export interface Material {
  id: string; lab_id: string; name: string; cas: string; catalog_no: string; lot: string; location_id: string
  quantity: number; unit: string; min_stock: number; lead_time_days: number; delivered: string | null
  expires: string | null; hazards: string[]; sds: number; responsible: string | null; notes: string
  forecast: Forecast
}

export interface Experiment {
  id: string; code: string; title: string; lead: string; dates: string[]
  usage: { material_id: string; amount: number }[]; equipment_ids: string[]
}

export interface Sample {
  id: string; label: string; experiment_id: string | null; location_id: string; owner_id: string; status: string
  collected: string | null
}

export interface LabDetail extends LabSummary {
  width: number; depth: number; entrance: [number, number]; glb_url: string | null
  points: Point[]; zones: Zone[]; equipment: Equipment[]; materials: Material[]
  experiments: Experiment[]; samples: Sample[]
}

export interface LogEntry { id: number; kind: string; note: string; at: string; user: string | null; amount?: number }
export interface Incident {
  id: number; lab_id: string; equipment_id: string | null; equipment?: string | null; category: string
  priority: 'low' | 'medium' | 'high' | 'critical'; description: string; status: string; resolution: string
  reporter: string; resolver: string | null; at: string
}
export interface Helper {
  user_id: string; name: string; role: string; online: boolean; score: number; reasons: string[]; match: string
}
export interface EquipmentDetail extends Equipment {
  logs: LogEntry[]; incidents: Incident[]; helpers: Helper[]
  knowledge: { problem: string; cause?: string; solution: string; by: string; date: string }[]
  materials: Material[]; samples: Sample[]
}
export interface MaterialDetail extends Material {
  location: string; logs: LogEntry[]; used_in: { code: string; title: string; next: string | null }[]
}

export interface Quest {
  id: number; lab_id: string; title: string; description: string
  source: 'system' | 'calendar' | 'inventory' | 'leader' | 'social'
  category: 'daily' | 'weekly' | 'emergency' | 'team' | 'esg' | 'knowledge'
  priority: 'low' | 'medium' | 'high' | 'critical'; xp: number; minutes: number
  target_id: string | null; material_id: string | null; experiment_id: string | null; due: string | null
  assignee_id: string | null; assignee: string | null; status: string; location: string | null
  created_by_name: string | null; reason?: string | null
}
export interface QuestBoard {
  mine: Quest[]; pool: Quest[]; done: Quest[]
  projects: { id: string; code: string; title: string; lead: string; next_run: string | null; quests: Quest[] }[]
  challenges?: Challenge[]
}
export interface Challenge {
  id: number; title: string; description: string; metric: string; target: number; value: number
  progress: number; completed: boolean; active: boolean
}

export interface Channel {
  id: string; kind: 'lab' | 'equipment' | 'dm' | 'group'; title: string; last_id: number; last_text: string
  last_at: string | null; equipment_id?: string; user_id?: string
}
export interface Message {
  id: number; channel: string; sender_id: string; sender: string | null; text: string
  equipment_ref: string | null; mentions: string[]; help_request: number; at: string
}

export interface Route {
  order: string[]; points: [number, number][]; distance_m: number; minutes: number
  unreachable?: { id: string; reason: string }[]
}
