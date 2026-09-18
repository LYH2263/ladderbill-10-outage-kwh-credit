// 后端失败时统一抛出带可读 message 的错误；422 信用超额等场景保留 detail 字段
async function parseError(r) {
  let detail = null
  try {
    const body = await r.json()
    detail = body.detail ?? body
  } catch {
    /* 非 JSON 错误体，按纯文本处理 */
  }
  const err = new Error(
    (detail && (detail.message || (typeof detail === 'string' ? detail : null))) ||
      `请求失败 (${r.status})`
  )
  err.status = r.status
  err.detail = detail
  return err
}

export async function getJSON(path) {
  const r = await fetch(path)
  if (!r.ok) throw await parseError(r)
  return r.json()
}
export async function postJSON(path, body) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) throw await parseError(r)
  return r.json()
}
