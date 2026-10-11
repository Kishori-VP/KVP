import { getLang, locale, t } from './i18n'

export function fmtDate(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleDateString(locale(), { day: '2-digit', month: 'short', year: 'numeric' })
}

export function fmtDateTime(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleString(locale(), { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function fmtNum(n) {
  if (n === null || n === undefined || n === '') return '—'
  return typeof n === 'number' ? n.toLocaleString(locale()) : n
}

export function humanize(code) {
  if (!code) return '—'
  return t(String(code).replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase()))
}

export function todayISO() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function addDaysISO(iso, days) {
  const d = new Date(`${iso}T00:00:00`)
  d.setDate(d.getDate() + days)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Village display: name in the current language with the other in brackets. */
export function villageName(v) {
  if (!v) return '—'
  if (!v.name_mr) return v.name
  return getLang() === 'mr' ? `${v.name_mr} (${v.name})` : `${v.name} (${v.name_mr})`
}
