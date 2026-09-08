const BASE = '/api'

function qs(params = {}) {
  const p = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    // `false` is a real value, not an absent one: dropping it silently reverted
    // publishing_only / priority_only to their `True` server defaults, which
    // made three UI toggles no-ops. Only null/undefined/'' mean "not set".
    if (v !== null && v !== undefined && v !== '') p.append(k, v)
  })
  const s = p.toString()
  return s ? `?${s}` : ''
}

export async function get(path, params) {
  const res = await fetch(`${BASE}${path}${qs(params)}`)
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status}: ${body.slice(0, 200)}`)
  }
  return res.json()
}

export async function upload(path, formData) {
  const res = await fetch(`${BASE}${path}`, { method: 'POST', body: formData })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.detail || `Upload failed (${res.status})`)
  return body
}

export async function post(path, json) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(json || {}),
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`)
  return body
}
