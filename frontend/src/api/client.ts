const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1'

export async function api<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (init?.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(body.detail ?? `Request failed with ${response.status}`)
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

export const percent = (value: number, decimals?: number) => {
  const precision = decimals ?? (value < 0.01 ? 1 : 0)
  return `${(value * 100).toFixed(precision)}%`
}
