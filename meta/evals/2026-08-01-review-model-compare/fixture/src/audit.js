const entries = []

export async function record(event, detail) {
  entries.push({ event, detail, at: new Date().toISOString() })
}

export function _entries() {
  return entries
}

export function summary() {
  return entries.map((e) => `${e.at} ${e.event}`).join('\n')
}
