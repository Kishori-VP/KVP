import { CalendarCheck, ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import api, { errorMessage } from '../lib/api'
import { useFetch } from '../lib/hooks'
import { locale, t } from '../lib/i18n'
import { VolunteerSelect } from './pickers'
import { Badge, Button, Checkbox, ErrorBox, Input, Modal, Spinner, cx } from './ui'

const TYPE_LABEL = { kishori: 'Kishori', bal_panchayat: 'Bal Panchayat' }

/** The planner's month, as a {y, m} pair (m is 0-based, like Date). */
const thisMonth = () => {
  const d = new Date()
  return { y: d.getFullYear(), m: d.getMonth() }
}
const monthLabel = (y, m) => new Date(y, m, 1).toLocaleDateString(locale(), { month: 'long', year: 'numeric' })
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

/** Date inputs stay inside the month, and never before today. */
const monthRange = (y, m) => {
  const today = new Date()
  const sameMonth = y === today.getFullYear() && m === today.getMonth()
  return { min: iso(sameMonth ? today : new Date(y, m, 1)), max: iso(new Date(y, m + 1, 0)) }
}

/**
 * Monthly meeting planner: pick the Kishori / Bal Panchayat groups that meet this month, set each
 * meeting's date, time and volunteer, then create them in one go. This replaces the old one-click
 * auto-scheduler, so nothing is written until the admin presses Create.
 */
export default function MonthlyMeetingPlanner({ open, onClose, onCreated }) {
  const [ym, setYm] = useState(thisMonth)
  const [rows, setRows] = useState({}) // group_id -> { on, date, time, volunteer }
  const [q, setQ] = useState('')
  const [bulk, setBulk] = useState({ date: '', time: '' })
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState(null)
  const [done, setDone] = useState(null)
  const { y, m } = ym
  const { data, error, loading, reload } = useFetch(open ? '/events/monthly-planner' : null, { year: y, month: m + 1 })
  const range = monthRange(y, m)
  const isPastMonth = range.max < iso(new Date())

  // Each group starts ticked on its usual slot; groups that already have this month's meeting stay out.
  useEffect(() => {
    if (!data) return
    setRows(Object.fromEntries(data.groups.map((g) => [g.group_id, {
      on: !g.existing_event_id && Boolean(g.suggested_date),
      date: g.suggested_date || '',
      time: g.suggested_time || '10:00',
      volunteer: g.responsible_volunteer_id || '',
    }])))
  }, [data])

  // Messages belong to the month they were shown for; the reload after Create must not clear them.
  useEffect(() => {
    setDone(null)
    setErr(null)
  }, [y, m])

  // Reopening the planner starts fresh on the current month.
  useEffect(() => {
    if (open) {
      setYm(thisMonth())
      setQ('')
      setBulk({ date: '', time: '' })
      setDone(null)
    }
  }, [open])

  const groups = data?.groups || []
  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return groups
    return groups.filter((g) => [g.group_name, g.village_name, g.village_name_mr, g.responsible_volunteer_name]
      .some((s) => s && s.toLowerCase().includes(needle)))
  }, [groups, q])

  const set = (id, patch) => setRows((r) => ({ ...r, [id]: { ...r[id], ...patch } }))
  const selected = groups.filter((g) => rows[g.group_id]?.on && !g.existing_event_id)
  const needDate = selected.filter((g) => !rows[g.group_id]?.date)
  const alreadyPlanned = groups.filter((g) => g.existing_event_id).length

  /** Tick or untick every group the search currently shows, never the ones already planned. */
  const toggleVisible = (on) => setRows((r) => {
    const next = { ...r }
    for (const g of visible) if (!g.existing_event_id) next[g.group_id] = { ...next[g.group_id], on }
    return next
  })

  /** Apply one date or time to every selected group — the common "they all meet that day" case. */
  const applyBulk = (patch) => setRows((r) => {
    const next = { ...r }
    for (const g of selected) next[g.group_id] = { ...next[g.group_id], ...patch }
    return next
  })

  const create = async () => {
    setSaving(true)
    setErr(null)
    try {
      const res = await api.post('/events/monthly-planner', {
        year: y,
        month: m + 1,
        meetings: selected.map((g) => ({
          group_id: g.group_id,
          meeting_date: rows[g.group_id].date,
          start_time: rows[g.group_id].time || '10:00',
          responsible_volunteer_id: rows[g.group_id].volunteer || null,
        })),
      })
      setDone({ ...res.data, month: monthLabel(y, m) })
      onCreated?.()
      reload()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setSaving(false)
    }
  }

  const shift = (n) => setYm(({ y: cy, m: cm }) => {
    const d = new Date(cy, cm + n, 1)
    return { y: d.getFullYear(), m: d.getMonth() }
  })
  const canCreate = selected.length > 0 && needDate.length === 0 && !isPastMonth

  return (
    <Modal
      open={open}
      wide="xl"
      title={t('Plan monthly meetings')}
      onClose={onClose}
      footer={<>
        <Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button>
        <Button icon={CalendarCheck} busy={saving} disabled={!canCreate} onClick={create}>
          {t('Create {n} meetings', { n: selected.length })}
        </Button>
      </>}
    >
      <p className="text-xs text-gray-500">
        {t('Choose the groups, set each meeting date and time, then create them. Nothing is scheduled until you click Create.')}
      </p>

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
        <div className="flex items-center gap-1">
          <Button size="sm" variant="secondary" icon={ChevronLeft} onClick={() => shift(-1)}>{t('Prev')}</Button>
          <span className="px-2 text-sm font-semibold text-gray-900">{monthLabel(y, m)}</span>
          <Button size="sm" variant="secondary" onClick={() => shift(1)}>{t('Next')} <ChevronRight className="h-4 w-4" /></Button>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-600">
          <span>{t('{n} groups', { n: groups.length })}</span>
          {alreadyPlanned > 0 && <span className="text-gray-500">{t('{n} already planned this month', { n: alreadyPlanned })}</span>}
          {needDate.length > 0 && <span className="font-medium text-amber-700">{t('{n} need a date', { n: needDate.length })}</span>}
        </div>
      </div>

      {isPastMonth && <ErrorBox message={t('This month is over. Pick the current or a future month.')} />}
      {error && <ErrorBox message={error} />}
      {err && <ErrorBox message={err} />}

      {done && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800">
          <div className="font-medium">{t('{n} meetings created for {month}.', { n: done.created, month: done.month })}</div>
          {done.skipped?.length > 0 && (
            <div className="mt-1 text-xs text-green-700">
              {t('{n} skipped (already planned):', { n: done.skipped.length })}{' '}
              {done.skipped.map((s) => s.group_name).join(', ')}
            </div>
          )}
        </div>
      )}

      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <Input className="pl-8" placeholder={t('Search group, village or volunteer')} value={q} onChange={(e) => setQ(e.target.value)} />
      </div>

      {selected.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-brand-100 bg-brand-50 px-3 py-2 text-xs">
          <span className="font-medium text-brand-900">{t('For all {n} selected:', { n: selected.length })}</span>
          <div className="w-40">
            <Input
              type="date" min={range.min} max={range.max} value={bulk.date}
              onChange={(e) => {
                setBulk((b) => ({ ...b, date: e.target.value }))
                if (e.target.value) applyBulk({ date: e.target.value })
              }}
            />
          </div>
          <div className="w-28">
            <Input
              type="time" value={bulk.time}
              onChange={(e) => {
                setBulk((b) => ({ ...b, time: e.target.value }))
                if (e.target.value) applyBulk({ time: e.target.value })
              }}
            />
          </div>
        </div>
      )}

      {loading && !data ? <Spinner /> : (
        <div className="overflow-hidden rounded-lg border border-gray-200">
          <div className="flex items-center gap-2 border-b border-gray-200 bg-gray-50 px-3 py-2">
            <Checkbox
              checked={visible.length > 0 && visible.every((g) => g.existing_event_id || rows[g.group_id]?.on)}
              onChange={(e) => toggleVisible(e.target.checked)}
              label={<span className="text-xs font-medium text-gray-600">{t('Group')}</span>}
            />
            <span className="ml-auto hidden text-xs font-medium text-gray-600 sm:block">{t('Village / volunteer')}</span>
          </div>
          <div className="max-h-[45dvh] divide-y divide-gray-100 overflow-y-auto">
            {visible.length === 0 && <div className="px-3 py-6 text-center text-sm text-gray-500">{t('No groups match.')}</div>}
            {visible.map((g) => {
              const row = rows[g.group_id] || {}
              const planned = Boolean(g.existing_event_id)
              const missing = row.on && !row.date
              return (
                <div key={g.group_id} className={cx('px-3 py-2.5 sm:flex sm:items-center sm:gap-3', planned && 'bg-gray-50')}>
                  <div className="min-w-0 flex-1">
                    <Checkbox
                      checked={Boolean(row.on)}
                      disabled={planned || isPastMonth}
                      onChange={(e) => set(g.group_id, { on: e.target.checked })}
                      label={<span className={cx('font-medium', planned ? 'text-gray-500' : 'text-gray-900')}>{g.group_name}</span>}
                    />
                    <div className="mt-0.5 pl-6 text-xs text-gray-500">
                      <Badge tone={g.group_type === 'kishori' ? 'blue' : 'green'}>{t(TYPE_LABEL[g.group_type])}</Badge>{' '}
                      {g.village_name || '—'} · {g.responsible_volunteer_name || t('No volunteer')}
                    </div>
                  </div>
                  {planned ? (
                    <div className="mt-1.5 pl-6 sm:mt-0 sm:w-80 sm:pl-0 sm:text-right">
                      <Badge tone="gray">{t('Already planned')}</Badge>{' '}
                      <span className="text-xs text-gray-500">{g.existing_start_at?.slice(0, 10)}</span>
                    </div>
                  ) : (
                    <div className="mt-1.5 flex items-center gap-2 pl-6 sm:mt-0 sm:w-72 sm:pl-0">
                      <div className="min-w-0 flex-1">
                        <Input
                          type="date" className={cx(missing && 'border-amber-400')}
                          min={range.min} max={range.max} disabled={!row.on}
                          value={row.date || ''} onChange={(e) => set(g.group_id, { date: e.target.value })}
                        />
                      </div>
                      <div className="w-28 shrink-0">
                        <Input
                          type="time" disabled={!row.on}
                          value={row.time || ''} onChange={(e) => set(g.group_id, { time: e.target.value })}
                        />
                      </div>
                    </div>
                  )}
                  {!planned && (
                    <div className="mt-1.5 pl-6 sm:mt-0 sm:w-52 sm:pl-0">
                      {row.on && (
                        <VolunteerSelect
                          villageId={g.village_id} value={row.volunteer}
                          onChange={(v) => set(g.group_id, { volunteer: v })} placeholder={t('No volunteer')}
                        />
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </Modal>
  )
}
