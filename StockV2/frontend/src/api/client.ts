const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api/v1'
const API_KEY = import.meta.env.VITE_API_KEY ?? 'changeme'

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
      ...options.headers,
    },
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch { /* ignore parse errors */ }
    throw new Error(detail)
  }
  return res.json()
}
