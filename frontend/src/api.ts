// Public URLs only. Authentication is supplied by the gateway's HttpOnly cookie.
export const apiBase = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')
export const eventURL = import.meta.env.VITE_SSE_URL || `${apiBase}/events`

export async function post(path: string, body?: unknown) {
  const response = await fetch(apiBase + path, {
    method: 'POST', credentials: 'include',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body ?? {}),
  })
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail))
  return data
}
