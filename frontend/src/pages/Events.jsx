import { ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { GroupedBars } from '../components/charts'
import { GroupMultiSelect, LookupSelect, VillageSelect, VolunteerSelect } from '../components/pickers'
import { Button, Card, Checkbox, ErrorBox, Field, Input, Modal, PageHeader, Pagination, Select, Spinner, StatusBadge, Table, Tabs, Textarea, cx } from '../components/ui'
import api from '../lib/api'
import { fmtDate, fmtDateTime, humanize, todayISO } from '../lib/format'
import { lookupLabel, useAction, useFetch, useLookups } from '../lib/hooks'
import { locale, t } from '../lib/i18n'
import { useAuth } from '../lib/auth'

export function EventForm({ onSaved, onCancel }) {
  const [f, setF] = useState({ event_date: todayISO(), start_time: '10:00', group_ids: [], expected_participants: 0, is_historical: false, notify_participants: false })
  const { busy, error, run } = useAction()
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }))
  const submit = () => run(async () => {
    const r = await api.post('/events', {
      ...f, end_time: f.end_time || null, responsible_volunteer_id: f.responsible_volunteer_id || null,
      expected_participants: Number(f.expected_participants || 0), planned_budget: f.planned_budget ? Number(f.planned_budget) : null,
    })
    onSaved(r.data)
  }).catch(() => {})
  return (
    <div className="space-y-3">
      <ErrorBox message={error} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t('Title *')} className="sm:col-span-2"><Input value={f.title || ''} onChange={(e) => set('title', e.target.value)} /></Field>
        <Field label={t('Event type *')}><LookupSelect type="event_type" value={f.event_type} onChange={(v) => set('event_type', v)} /></Field>
        <Field label={t('Village *')}><VillageSelect value={f.village_id} onChange={(v) => { set('village_id', v); set('group_ids', []); set('responsible_volunteer_id', '') }} placeholder={t('Select village')} /></Field>
        <Field label={t('Date *')}><Input type="date" value={f.event_date} onChange={(e) => set('event_date', e.target.value)} /></Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label={t('Start')}><Input type="time" value={f.start_time} onChange={(e) => set('start_time', e.target.value)} /></Field>
          <Field label={t('End')}><Input type="time" value={f.end_time || ''} onChange={(e) => set('end_time', e.target.value)} /></Field>
        </div>
        <Field label={t('Location')}><Input placeholder={t('e.g. ZP school hall')} value={f.location_name || ''} onChange={(e) => set('location_name', e.target.value)} /></Field>
        <Field label={t('Responsible volunteer')}><VolunteerSelect villageId={f.village_id} value={f.responsible_volunteer_id} onChange={(v) => set('responsible_volunteer_id', v)} placeholder={t('None')} /></Field>
        <Field label={t('Expected participants')}><Input type="number" min={0} value={f.expected_participants} onChange={(e) => set('expected_participants', e.target.value)} /></Field>
        <Field label={t('Planned budget (₹)')}><Input type="number" min={0} value={f.planned_budget || ''} onChange={(e) => set('planned_budget', e.target.value)} /></Field>
        <Field label={t('Objective')} className="sm:col-span-2"><Textarea value={f.objective || ''} onChange={(e) => set('objective', e.target.value)} /></Field>
      </div>
      <Field label={t('Invited Kishori Groups')} group><GroupMultiSelect villageId={f.village_id} value={f.group_ids} onChange={(v) => set('group_ids', v)} /></Field>
      <div className="flex flex-wrap gap-4">
        <Checkbox label={t("SMS reminder to invited girls' families the day before")} checked={f.notify_participants} onChange={(e) => set('notify_participants', e.target.checked)} />
        <Checkbox label={t('This is a past event (back-dated entry)')} checked={f.is_historical} onChange={(e) => set('is_historical', e.target.checked)} />
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel}>{t('Cancel')}</Button>
        <Button busy={busy} disabled={!f.title || !f.event_type || !f.village_id} onClick={submit}>{t('Schedule event')}</Button>
      </div>
    </div>
  )
}

function monthGrid(year, month) {
  const first = new Date(year, month, 1)
  const offset = (first.getDay() + 6) % 7 // Monday first
  const days = new Date(year, month + 1, 0).getDate()
  const cells = []
  for (let i = 0; i < offset; i++) cells.push(null)
  for (let d = 1; d <= days; d++) cells.push(`${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`)
  return cells
}

const STATUS_STYLE = { completed: 'bg-green-50 text-green-800', overdue: 'bg-orange-50 text-orange-800', cancelled: 'bg-gray-100 text-gray-500 line-through', today: 'bg-brand-50 text-brand-800', upcoming: 'bg-blue-50 text-blue-800' }
const PER_CELL = 3

function CalendarView({ villageId }) {
  const nav = useNavigate()
  const now = new Date()
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() })
  const [selected, setSelected] = useState(todayISO())
  const cells = monthGrid(ym.y, ym.m)
  const start = cells.find(Boolean)
  const end = cells[cells.length - 1]
  const { data } = useFetch('/events/calendar', { start_date: start, end_date: end, village_id: villageId })
  const byDay = Object.fromEntries((data?.days || []).map((d) => [d.date, d.events]))
  const shift = (n) => setYm(({ y, m }) => { const d = new Date(y, m + n, 1); setSelected(null); return { y: d.getFullYear(), m: d.getMonth() } })
  const label = new Date(ym.y, ym.m, 1).toLocaleDateString(locale(), { month: 'long', year: 'numeric' })
  const today = todayISO()
  const total = (data?.days || []).reduce((n, d) => n + d.events.length, 0)
  const dayEvents = (selected && byDay[selected]) || []
  return (
    <div className="space-y-4">
      <Card title={label} actions={<>
        <Button size="sm" variant="secondary" icon={ChevronLeft} onClick={() => shift(-1)}>{t('Prev')}</Button>
        <Button size="sm" variant="secondary" onClick={() => shift(1)}>{t('Next')} <ChevronRight className="h-4 w-4" /></Button>
      </>}>
        {data && <div className="mb-3 flex flex-wrap items-center gap-2 text-xs"><span className="font-medium text-gray-700">{t('{n} events this month', { n: total })}</span>{Object.entries(data.counts).map(([k, n]) => <span key={k}><StatusBadge value={k} /> {n}</span>)}</div>}
        <div className="grid grid-cols-7 gap-px overflow-hidden rounded-lg border border-gray-200 bg-gray-200 text-xs">
          {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => <div key={d} className="bg-gray-50 px-1 py-1 text-center font-medium text-gray-500 sm:px-2 sm:text-left">{t(d)}</div>)}
          {cells.map((iso, i) => {
            const evs = (iso && byDay[iso]) || []
            return (
              <div key={i} role={iso ? 'button' : undefined} tabIndex={iso ? 0 : undefined} onClick={() => iso && setSelected(iso)}
                onKeyDown={(e) => iso && e.key === 'Enter' && setSelected(iso)}
                className={cx('min-h-20 bg-white p-1 sm:min-h-24', !iso && 'bg-gray-50', iso && 'cursor-pointer hover:bg-gray-50', iso === selected && 'ring-2 ring-inset ring-brand-500')}>
                {iso && <div className={cx('mb-1 text-right', iso === today ? 'font-bold text-brand-700' : 'text-gray-500')}>{Number(iso.slice(8))}</div>}
                {/* phones: just a count; wider screens: the first few events */}
                {evs.length > 0 && <div className="rounded bg-brand-50 px-1 text-center font-semibold text-brand-800 sm:hidden">{evs.length}</div>}
                <div className="hidden sm:block">
                  {evs.slice(0, PER_CELL).map((ev) => (
                    <button key={ev.id} type="button" onClick={(e) => { e.stopPropagation(); nav(`/events/${ev.id}`) }}
                      className={cx('mb-0.5 block w-full truncate rounded px-1 py-0.5 text-left', STATUS_STYLE[ev.display_status])}
                      title={`${ev.title} · ${ev.village_name} · ${humanize(ev.display_status)}`}>
                      {ev.start_time} {ev.title}
                    </button>
                  ))}
                  {evs.length > PER_CELL && <div className="px-1 font-medium text-brand-700">{t('+{n} more', { n: evs.length - PER_CELL })}</div>}
                </div>
              </div>
            )
          })}
        </div>
      </Card>
      {selected && <Card title={`${t('Events on')} ${fmtDate(selected)} · ${dayEvents.length}`}>
        {dayEvents.length ? <div className="divide-y divide-gray-100">{dayEvents.map((ev) => (
          <Link key={ev.id} to={`/events/${ev.id}`} className="flex items-start justify-between gap-3 py-2 hover:text-brand-700">
            <div className="min-w-0"><div className="truncate font-medium text-gray-900">{ev.title}</div>
              <div className="text-xs text-gray-500">{ev.start_time || ''}{ev.end_time ? `–${ev.end_time}` : ''} · {ev.village_name}</div></div>
            <StatusBadge value={ev.display_status} />
          </Link>
        ))}</div> : <p className="text-sm text-gray-500">{t('No events on this day.')}</p>}
      </Card>}
    </div>
  )
}

/** The KVP programme year starts on 1 July. */
function programmeYearStart() {
  const d = new Date()
  return `${d.getMonth() >= 6 ? d.getFullYear() : d.getFullYear() - 1}-07-01`
}

function PlannedVsConducted() {
  const [range, setRange] = useState({ start_date: programmeYearStart(), end_date: todayISO(), group_by: 'month' })
  const { data } = useFetch('/events/planned-vs-conducted', range)
  return (
    <Card title={t('Planned vs conducted')} actions={<>
      <Input type="date" value={range.start_date} onChange={(e) => setRange({ ...range, start_date: e.target.value })} />
      <Input type="date" value={range.end_date} onChange={(e) => setRange({ ...range, end_date: e.target.value })} />
      <Select options={['month', 'event_type', 'village', 'volunteer']} value={range.group_by} onChange={(e) => setRange({ ...range, group_by: e.target.value })} />
    </>}>
      {!data ? <Spinner /> : (
        <>
          <div className="mb-3 text-sm text-gray-700">
            {t('Planned')} <b>{data.totals.planned}</b> · {t('conducted as planned')} <b>{data.totals.conducted_as_planned}</b> · {t('unplanned conducted')} <b>{data.totals.unplanned_conducted}</b> ·
            {' '}{t('cancelled')} <b>{data.totals.cancelled}</b> · {t('overdue')} <b>{data.totals.overdue}</b> · {t('completion rate')} <b>{data.totals.completion_rate != null ? `${Math.round(data.totals.completion_rate * 100)}%` : '—'}</b>
          </div>
          <GroupedBars data={data.rows} xKey="label" series={[{ key: 'planned', label: t('Planned') }, { key: 'conducted', label: t('Conducted') }, { key: 'cancelled', label: t('Cancelled') }]} />
        </>
      )}
    </Card>
  )
}

export default function Events() {
  const nav = useNavigate()
  const { user } = useAuth()
  const isVolunteer = user?.role === 'volunteer'
  const types = useLookups('event_type')
  const [tab, setTab] = useState('list')
  const [f, setF] = useState({ status: '', village_id: '', event_type: '' })
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const { data, error, loading } = useFetch(tab === 'list' ? '/events' : null, { ...f, page, page_size: 25 })
  return (
    <div>
      <PageHeader title={t('Events')} subtitle={t('Village events, attendance and post-event reporting')} actions={!isVolunteer && <Button icon={Plus} onClick={() => setCreating(true)}>{t('Schedule event')}</Button>} />
      <Tabs tabs={[{ value: 'list', label: t('List') }, { value: 'calendar', label: t('Calendar') }, ...(!isVolunteer ? [{ value: 'pvc', label: t('Planned vs conducted') }] : [])]} value={tab} onChange={setTab} />
      {tab === 'list' && (
        <Card padded={false}>
          <div className="grid gap-2 border-b border-gray-100 p-3 sm:grid-cols-3">
            <Select options={['upcoming', 'today', 'overdue', 'completed', 'cancelled']} placeholder={t('Any status')} value={f.status} onChange={(e) => { setF({ ...f, status: e.target.value }); setPage(1) }} />
            <VillageSelect value={f.village_id} onChange={(v) => { setF({ ...f, village_id: v }); setPage(1) }} />
            <LookupSelect type="event_type" value={f.event_type} onChange={(v) => { setF({ ...f, event_type: v }); setPage(1) }} placeholder={t('Any type')} />
          </div>
          <ErrorBox message={error} />
          {loading && !data ? <Spinner /> : (
            <>
              <Table onRowClick={(r) => nav(`/events/${r.id}`)} columns={[
                { key: 'start_at', label: t('When'), render: (r) => fmtDateTime(r.start_at), className: 'whitespace-nowrap' },
                { key: 'title', label: t('Event'), className: 'font-medium' },
                { key: 'event_type', label: t('Type'), render: (r) => lookupLabel(types, r.event_type) },
                { key: 'display_status', label: t('Status'), render: (r) => <StatusBadge value={r.display_status} /> },
                { key: 'att', label: t('Present / expected'), render: (r) => `${r.attendance_summary.total_present} / ${r.expected_participants || '—'}` },
                { key: 'report', label: t('Report'), render: (r) => (r.report ? t('Submitted') : '—') },
              ]} rows={data?.items} empty={t('No events yet.')} />
              <Pagination page={page} pageSize={25} total={data?.total} onPage={setPage} />
            </>
          )}
        </Card>
      )}
      {tab === 'calendar' && <CalendarView villageId={f.village_id} />}
      {tab === 'pvc' && <PlannedVsConducted />}
      {!isVolunteer && <Modal open={creating} title={t('Schedule an event')} onClose={() => setCreating(false)} wide>
        <EventForm onCancel={() => setCreating(false)} onSaved={(ev) => nav(`/events/${ev.id}`)} />
      </Modal>}
    </div>
  )
}
