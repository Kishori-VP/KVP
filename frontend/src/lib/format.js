import { getLang, locale, t } from './i18n'

export const TIMEZONE_IST = 'Asia/Kolkata'

/**
 * Format a calendar date in Indian Standard Time (IST).
 * Returns e.g. "21 Oct 2026"
 */
export function fmtDate(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleDateString(locale(), {
    timeZone: TIMEZONE_IST,
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

/**
 * Format a timestamp into date & time in Indian Standard Time (IST).
 * Returns e.g. "21 Oct 2026, 01:25 PM"
 */
export function fmtDateTime(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleString(locale(), {
    timeZone: TIMEZONE_IST,
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  })
}

/**
 * Format time only in Indian Standard Time (IST).
 * Returns e.g. "01:25 PM"
 */
export function fmtTime(value) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  return d.toLocaleTimeString(locale(), {
    timeZone: TIMEZONE_IST,
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  })
}

export function fmtNum(n) {
  if (n === null || n === undefined || n === '') return '—'
  return typeof n === 'number' ? n.toLocaleString(locale()) : n
}

export function humanize(code) {
  if (!code) return '—'
  return t(String(code).replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase()))
}

/**
 * Today's calendar date evaluated strictly in Indian Standard Time (IST) as "YYYY-MM-DD".
 */
export function todayISO() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: TIMEZONE_IST,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date())
}

/**
 * Shift an ISO calendar date ("YYYY-MM-DD") by `days` within Indian Standard Time.
 */
export function addDaysISO(iso, days) {
  if (!iso) return todayISO()
  const parts = String(iso).slice(0, 10).split('-').map(Number)
  if (parts.length < 3 || parts.some(isNaN)) return todayISO()
  const [y, m, d] = parts
  const date = new Date(Date.UTC(y, m - 1, d + days, 12, 0, 0))
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: TIMEZONE_IST,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date)
}

/** Village display: name in the current language with the other in brackets. */
export function villageName(v) {
  if (!v) return '—'
  if (!v.name_mr) return v.name
  return getLang() === 'mr' ? `${v.name_mr} (${v.name})` : `${v.name} (${v.name_mr})`
}
