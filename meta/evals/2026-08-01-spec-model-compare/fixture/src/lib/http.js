import { request as undiciRequest } from 'undici'

export async function request(url, { query, timeoutMs = 2000 } = {}) {
  const qs = query ? '?' + new URLSearchParams(query).toString() : ''
  const res = await undiciRequest(url + qs, { headersTimeout: timeoutMs })
  return { status: res.statusCode, body: await res.body.json() }
}
