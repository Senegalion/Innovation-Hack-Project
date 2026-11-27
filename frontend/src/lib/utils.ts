import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { locale } from '@/lib/i18n'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export const fmtDate = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleDateString(locale(), { day: '2-digit', month: 'short', year: 'numeric' }) : '—'

export const fmtTime = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' }) : ''

export const daysUntil = (iso?: string | null) =>
  iso ? Math.round((new Date(iso).setHours(0, 0, 0, 0) - new Date().setHours(0, 0, 0, 0)) / 86400000) : null
