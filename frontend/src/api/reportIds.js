export function normalizeReportId(value) {
  const raw = Array.isArray(value) ? value[0] : value
  const text = String(raw || '').trim()
  const match = text.match(/\b(?:f?report_[A-Za-z0-9]+)\b/)
  return match ? match[0] : text
}

export function firstQueryValue(value) {
  return Array.isArray(value) ? value[0] : value
}
