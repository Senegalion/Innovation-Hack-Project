import { useLang } from '@/lib/i18n'

function currentUser(): string {
  try {
    return JSON.parse(localStorage.getItem('smartlab.me') ?? '"u-tomek"')
  } catch {
    return 'u-tomek'
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': currentUser(),
      'Accept-Language': useLang.getState().lang,
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
}
