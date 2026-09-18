export async function getJSON(path) {
  const r = await fetch(path)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}
export async function postJSON(path, body) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

// FastAPI validation/business errors come back as {detail: ...}.
// Business errors carry a readable Chinese message in detail.message.
export function errorMessage(e) {
  try {
    const j = JSON.parse(e.message)
    if (j.detail) {
      if (typeof j.detail === 'string') return j.detail
      if (j.detail.message) return j.detail.message
      return JSON.stringify(j.detail)
    }
    return e.message
  } catch {
    return e.message
  }
}

export function fmtTime(s) {
  return s ? String(s).replace('T', ' ').slice(0, 16) : ''
}
