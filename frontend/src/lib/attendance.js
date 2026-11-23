import { useEffect, useMemo, useState } from 'react'

/** "04:07:09" for a millisecond duration. */
export function fmtCountdown(ms) {
  const total = Math.max(0, Math.ceil(ms / 1000))
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  return [h, m, s].map((n) => String(n).padStart(2, '0')).join(':')
}

/**
 * Live countdown to when check-out opens, from a `/attendance/today` response.
 * The server sends `checkout_allowed_at` (check-in + minimum duty hours) and `server_now`,
 * so the timer follows the server clock even if the phone's clock is off.
 */
export function useCheckoutCountdown(today) {
  const allowedAt = today?.checkout_allowed_at ? Date.parse(today.checkout_allowed_at) : null
  const offset = useMemo(
    () => (today?.server_now ? Date.parse(today.server_now) - Date.now() : 0),
    [today],
  )
  const [now, setNow] = useState(() => Date.now())
  const pending = Boolean(today?.checked_in && !today?.checked_out && allowedAt)
  const remainingMs = pending ? Math.max(0, allowedAt - (now + offset)) : 0
  const ticking = pending && remainingMs > 0

  useEffect(() => {
    if (!ticking) return undefined
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [ticking])

  const minHours = today?.min_work_hours || 5
  const totalMs = minHours * 3600 * 1000
  return {
    locked: ticking,
    remainingMs,
    minHours,
    allowedAt: allowedAt ? new Date(allowedAt) : null,
    progressPct: pending ? Math.round(Math.min(100, ((totalMs - remainingMs) / totalMs) * 100)) : 0,
  }
}
