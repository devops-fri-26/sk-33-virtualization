// Called when the server says the session is over (expired, logged out everywhere, account disabled).
let onUnauthorized = null
export const setUnauthorizedHandler = (fn) => (onUnauthorized = fn)

const FIELD_ERRORS = { email: 'Enter a valid email address.', password: 'The password must have 8 to 256 characters.' }

// The server's error as one readable line. `detail` is a string, or for invalid input a list like
// [{ loc: ['body', 'email'], msg: 'String should match pattern …' }].
function errorText(res, data) {
  const detail = data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail) && detail.length) {
    return detail.map((e) => FIELD_ERRORS[e.loc?.at(-1)] ?? `${e.loc?.at(-1) ?? 'Input'}: ${e.msg}`).join(' ')
  }
  if (res.status === 413) return 'Too big to upload.'
  return res.statusText || `Something went wrong (HTTP ${res.status}).` // statusText is empty over HTTP/2
}

// Small fetch wrapper: JSON, cookie auth, throws on error.
export async function api(path, { method = 'GET', body, form } = {}) {
  const res = await fetch(`/api${path}`, {
    method,
    credentials: 'include',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: form ?? (body ? JSON.stringify(body) : undefined),
  })
  if (!res.ok) {
    if (res.status === 401 && !path.startsWith('/auth/')) onUnauthorized?.()
    throw new Error(errorText(res, await res.json().catch(() => null)))
  }
  return res.status === 204 ? null : res.json()
}

export const streamUrl = (id) => `/api/tracks/${id}/stream`
export const coverUrl = (album) => (album?.cover ? `/api/covers/${album.cover}` : null)
// A track's picture: its own (tracks without an album have one), else its album's cover.
export const trackCoverUrl = (track) => (track?.cover ? `/api/covers/${track.cover}` : coverUrl(track?.album))
export const fmtTime = (s) => (s ? `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}` : '0:00')
export const fmtSize = (b) =>
  b >= 1024 ** 3 ? `${(b / 1024 ** 3).toFixed(1)} GB` : b >= 1024 ** 2 ? `${Math.round(b / 1024 ** 2)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`
// Storage amounts: "0 GB", "640 MB", "9.8 GB", "10 GB".
export const GB = 1024 ** 3
export const fmtBytes = (b) =>
  b >= GB ? `${+(b / GB).toFixed(1)} GB` : b >= 1024 ** 2 ? `${Math.round(b / 1024 ** 2)} MB` : b > 0 ? `${Math.max(1, Math.round(b / 1024))} KB` : '0 GB'
export function fmtTotal(s) {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return h ? `${h} hr ${m} min` : `${m} min ${Math.round(s % 60)} sec`
}
