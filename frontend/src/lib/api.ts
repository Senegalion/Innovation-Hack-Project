import { useLang } from '@/lib/i18n'

function currentUser(): string {
  try {
    return JSON.parse(localStorage.getItem('smartlab.me') ?? '"u-tomek"')
  } catch {
    return 'u-tomek'
  }
}

function baseHeaders(): Record<string, string> {
  return { 'X-User-Id': currentUser(), 'Accept-Language': useLang.getState().lang }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const isForm = init?.body instanceof FormData
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      ...baseHeaders(),
      ...(init?.headers ?? {}),
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export const api = {
  get: <T,>(path: string) => req<T>(path),
  post: <T,>(path: string, body: unknown) => req<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  put: <T,>(path: string, body: unknown) => req<T>(path, { method: 'PUT', body: JSON.stringify(body) }),
  patch: <T,>(path: string, body: unknown) => req<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  del: <T,>(path: string) => req<T>(path, { method: 'DELETE' }),
  upload: <T,>(path: string, fields: Record<string, string | Blob | null | undefined>) => {
    const form = new FormData()
    for (const [k, v] of Object.entries(fields)) if (v !== null && v !== undefined && v !== '') form.append(k, v)
    return req<T>(path, { method: 'POST', body: form })
  },
}
