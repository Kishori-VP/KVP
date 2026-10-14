import { Activity, AlertTriangle, CalendarDays, CheckCircle2, ClipboardCheck, FileText, HeartPulse, MapPin, Mic, Phone, Users } from 'lucide-react'
import 'leaflet/dist/leaflet.css'
import { CircleMarker, MapContainer, TileLayer, Tooltip as MapTooltip } from 'react-leaflet'
import { Link } from 'react-router-dom'
import { Button, Card, Empty, ErrorBox, PageHeader, ProgressBar, Spinner, StatTile, StatusBadge, Table } from '../components/ui'
import { fmtDate, fmtDateTime, humanize } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { t } from '../lib/i18n'
import { useState } from 'react'
import { TrendChart } from '../components/charts'

function getVillageName(village) {
  if (!village) return ''

  const isMarathi = localStorage.getItem('kvp_lang') === 'mr'

  if (isMarathi) {
    return (
      village.name_mr ||
      village.marathi_name ||
      village.name_marathi ||
      village.nameMr ||
      village.name ||
      ''
    )
  }

  return village.name_en || village.name || village.name_mr ||
    village.marathi_name || village.name_marathi || village.nameMr || ''
}

const QUICK_LINKS = [
  { to: '/girls', label: 'Girls & groups', description: 'View or register girls', icon: Users },
  { to: '/field', label: 'Record a visit', description: 'Plan a visit or submit today’s report', icon: ClipboardCheck },
  { to: '/events', label: 'Event reports', description: 'Submit attendance and event outcomes', icon: CalendarDays },
  { to: '/field', label: 'Voice entry', description: 'Dictate Marathi field observations', icon: Mic },
  { to: '/contacts', label: 'Village contacts', description: 'Maintain key contact details', icon: Phone },
  { to: '/cases', label: 'Follow-ups', description: 'Review concerns and next actions', icon: HeartPulse },
  { to: '/reports', label: 'My reports', description: 'Review activity and target progress', icon: FileText },
]

function PlannedVsActual() {
  const [period, setPeriod] = useState('weekly')
  const { data, error, loading } = useFetch(
    `/volunteers/me/planned-vs-actual?period=${period}`
  )

  const totals = data?.totals || {}

  const completionRate = totals.completion_rate || 0

  const periods = [
    { value: 'daily', label: 'Daily' },
    { value: 'weekly', label: 'Weekly' },
    { value: 'monthly', label: 'Monthly' },
  ]

  const series = [
    { key: 'visits_planned', label: t('Planned visits') },
    { key: 'visits_completed', label: t('Completed visits') },
    { key: 'events_planned', label: t('Planned events') },
    { key: 'events_conducted', label: t('Events conducted') },
  ]

  return (
    <Card
      title={t('Planned vs actual activity')}
      actions={
        <div className="flex rounded-lg border border-black/10 bg-white p-1">
          {periods.map((item) => (
            <button
              key={item.value}
              type="button"
              onClick={() => setPeriod(item.value)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                period === item.value
                  ? 'bg-brand-700 text-white'
                  : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              {t(item.label)}
            </button>
          ))}
        </div>
      }
    >
      {error && (
        <p className="mb-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {loading && !data ? (
        <Spinner />
      ) : (
        <>
          <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-5">
            <StatTile
              label={t('Planned visits')}
              value={totals.visits_planned || 0}
            />
            <StatTile
              label={t('Completed visits')}
              value={totals.visits_completed || 0}
            />
            <StatTile
              label={t('Planned events')}
              value={totals.events_planned || 0}
            />
            <StatTile
              label={t('Events conducted')}
              value={totals.events_conducted || 0}
            />
            <StatTile
              label={t('Completion rate')}
              value={`${completionRate}%`}
            />
          </div>

          {data?.rows?.length ? (
            <>
              <TrendChart
                data={data.rows}
                series={series}
                xKey="label"
                height={300}
              />

              <div className="mt-4 rounded-lg bg-brand-50 p-3">
                <div className="mb-2 flex items-center justify-between gap-3 text-sm">
                  <span className="font-medium text-brand-900">
                    {t('Overall completion')}
                  </span>
                  <span className="font-semibold text-brand-800">
                    {completionRate}%
                  </span>
                </div>

                <div className="h-2.5 overflow-hidden rounded-full bg-white">
                  <div
                    className="h-full rounded-full bg-brand-600 transition-all"
                    style={{
                      width: `${Math.min(100, completionRate)}%`,
                    }}
                  />
                </div>
              </div>
            </>
          ) : (
            <Empty>
              {t('No planned or completed activities were found for this period.')}
            </Empty>
          )}
        </>
      )}
    </Card>
  )
}

export default function VolunteerDashboard() {
  const { data, error, loading, reload } = useFetch('/volunteers/me/dashboard')
  if (loading && !data) return <Spinner />
  return (
    <div className="space-y-5">
      <PageHeader title={t('My field dashboard')} subtitle={t('Your village, activities, follow-ups and targets in one place.')} />
      <ErrorBox message={error} />
      {data && !data.assigned && (
        <Card title={t('Village assignment needed')}>
          <p className="text-sm text-gray-600">{t('Your account is active, but no village is assigned yet. Contact your Stakeholder to receive an assignment before recording field work.')}</p>
        </Card>
      )}
      {data?.assigned && <>
        <Card className="border-brand-200 bg-brand-50/50">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand-700"><MapPin className="h-4 w-4" />{t('Assigned village')}</div>
              <h2 className="text-xl font-semibold text-gray-900">{getVillageName(data.village)}</h2>
              <p className="mt-1 text-sm text-gray-600">{data.village?.taluka_name || data.village?.district || ''}</p>
              <p className="mt-2 text-xs text-gray-500">{t('{n} active groups', { n: data.groups?.length || 0 })} · {t('Month started {date}', { date: fmtDate(data.month_start) })}</p>
            </div>
            <Button variant="secondary" onClick={reload}>{t('Refresh')}</Button>
          </div>
        </Card>
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
          <StatTile label={t('Assigned girls')} value={data.summary?.girls_total || 0} sub={t('{n} active', { n: data.summary?.girls_active || 0 })} />
          <StatTile label={t('Visits today')} value={data.summary?.home_visits_today || 0} />
          <StatTile label={t('Visits this week')} value={data.summary?.home_visits_this_week || 0} />
          <StatTile label={t('Visits this month')} value={data.summary?.home_visits_this_month || 0} />
          <StatTile label={t('Girls reached this month')} value={data.summary?.girls_covered || 0} />
          <StatTile label={t('Event attendance this month')} value={data.summary?.event_attendance || 0} />
          <StatTile label={t('Open follow-ups')} value={data.open_cases || 0} tone={data.open_cases ? 'alert' : undefined} />
        </div>
        <PlannedVsActual />
        <section>
          <h2 className="mb-3 text-sm font-semibold text-gray-900">{t('Quick actions')}</h2>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {QUICK_LINKS.map(({ to, label, description, icon: Icon }) => (
              <Link key={`${to}-${label}`} to={to} className="group rounded-xl border border-black/10 bg-white p-4 shadow-sm transition hover:border-brand-300 hover:bg-brand-50/40">
                <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-700"><Icon className="h-5 w-5" /></div>
                <div className="font-medium text-gray-900">{t(label)}</div>
                <div className="mt-1 text-sm text-gray-500">{t(description)}</div>
              </Link>
            ))}
          </div>
        </section>
        <div className="grid gap-4 xl:grid-cols-2">
          <Card title={t('Assigned village map')}>
            {data.village?.location?.lat != null && data.village?.location?.lng != null ? <div className="h-64 overflow-hidden rounded-lg border border-black/10">
              <MapContainer center={[data.village.location.lat, data.village.location.lng]} zoom={12} scrollWheelZoom={false} className="h-full w-full">
                <TileLayer attribution="&copy; OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                <CircleMarker center={[data.village.location.lat, data.village.location.lng]} radius={10} pathOptions={{ color: '#ffffff', weight: 2, fillColor: '#0f766e', fillOpacity: 1 }}><MapTooltip>{getVillageName(data.village)}</MapTooltip></CircleMarker>
                {(data.recent_visits || []).filter((visit) => visit.gps?.lat != null && visit.gps?.lng != null).map((visit) => <CircleMarker key={visit.id} center={[visit.gps.lat, visit.gps.lng]} radius={6} pathOptions={{ color: '#ffffff', weight: 1, fillColor: '#2563eb', fillOpacity: 0.9 }}><MapTooltip>{t('Home visit')} · {fmtDate(visit.visit_date)}</MapTooltip></CircleMarker>)}
              </MapContainer>
            </div> : <p className="rounded-lg bg-gray-50 p-4 text-sm text-gray-600">{t('Village coordinates have not been added yet. Ask your Stakeholder to set the village location. GPS-tagged visits will appear on this map when available.')}</p>}
          </Card>
          <Card title={t('Girls by Kishori Group')}>
            {data.groups?.length ? <div className="space-y-3">{data.groups.map((group) => <div key={group.id}><div className="mb-1 flex items-center justify-between gap-2 text-sm"><Link className="font-medium text-gray-800 hover:text-brand-700" to={`/groups/${group.id}`}>{group.name}</Link><span className="text-xs text-gray-500">{group.girl_count || 0} {t('girls')}</span></div><div className="h-2 overflow-hidden rounded-full bg-gray-100"><div className="h-full rounded-full bg-brand-600" style={{ width: `${Math.min(100, (group.girl_count || 0) / Math.max(1, data.summary?.girls_total || 1) * 100)}%` }} /></div></div>)}</div> : <Empty>{t('No active groups in this village yet.')}</Empty>}
          </Card>
        </div>
        {(data.summary?.pending_visits || data.summary?.pending_reports) > 0 && <Card title={t('Submissions awaiting review')}>
          <div className="flex flex-wrap gap-4 text-sm"><span>{t('Home visits')}: <b>{data.summary?.pending_visits || 0}</b></span><span>{t('Daily reports')}: <b>{data.summary?.pending_reports || 0}</b></span><Link to="/field" className="text-brand-700 hover:underline">{t('View my submissions')}</Link></div>
        </Card>}
        <div className="grid gap-4 xl:grid-cols-2">
          <Card title={t('My current targets')} actions={<Link className="text-xs text-brand-700 hover:underline" to="/targets">{t('View all')}</Link>}>
            {data.targets?.length ? <div className="space-y-4">{data.targets.map((target) => (
              <div key={target.id}>
                <div className="mb-1 flex flex-wrap items-center justify-between gap-2 text-sm"><span className="font-medium text-gray-800">{target.title}</span><StatusBadge value={target.progress?.status} /></div>
                <ProgressBar pct={target.progress?.progress_pct} />
                <div className="mt-1 flex justify-between gap-2 text-xs text-gray-500"><span>{target.progress?.achieved || 0} / {target.target_value}</span><span>{t('{n} days left', { n: target.progress?.days_left || 0 })}</span></div>
              </div>
            ))}</div> : <Empty>{t('No active targets assigned for this period.')}</Empty>}
          </Card>
          <Card title={t('Upcoming events')} actions={<Link className="text-xs text-brand-700 hover:underline" to="/events">{t('All events')}</Link>}>
            {data.upcoming_events?.length ? <div className="divide-y divide-gray-100">{data.upcoming_events.map((event) => (
              <Link key={event.id} to={`/events/${event.id}`} className="flex items-start justify-between gap-3 py-3 first:pt-0 last:pb-0 hover:text-brand-700">
                <div><div className="font-medium text-gray-800">{event.title}</div><div className="mt-1 text-xs text-gray-500">{fmtDateTime(event.start_at)}{event.location_name ? ` · ${event.location_name}` : ''}</div></div>
                <StatusBadge value={event.display_status || event.status} />
              </Link>
            ))}</div> : <Empty>{t('No upcoming events are scheduled for your village.')}</Empty>}
          </Card>
        </div>
        {data.overdue_events?.length > 0 && <Card title={t('Event reports overdue')}>
          <div className="mb-3 flex items-center gap-2 text-sm text-amber-800"><AlertTriangle className="h-4 w-4" />{t('These events need a post-event report.')}</div>
          <Table columns={[
            { key: 'title', label: t('Event') }, { key: 'end_at', label: t('Date'), render: (r) => fmtDateTime(r.end_at) },
            { key: 'action', label: '', render: (r) => <Link className="text-brand-700 hover:underline" to={`/events/${r.id}`}>{t('Complete report')}</Link> },
          ]} rows={data.overdue_events} />
        </Card>}
        {data.overdue_cases > 0 && <Card title={t('Overdue follow-ups')}>
          <div className="flex items-center justify-between gap-3"><p className="flex items-center gap-2 text-sm text-amber-800"><AlertTriangle className="h-4 w-4" />{t('{n} case follow-up(s) are past their due date.', { n: data.overdue_cases })}</p><Link className="shrink-0 text-sm text-brand-700 hover:underline" to="/cases">{t('Review cases')}</Link></div>
        </Card>}
        <Card title={t('Upcoming case follow-ups')} actions={<Link className="text-xs text-brand-700 hover:underline" to="/cases">{t('All cases')}</Link>}>
          {data.upcoming_cases?.length ? <div className="divide-y divide-gray-100">{data.upcoming_cases.map((item) => <Link key={item.id} to={`/cases/${item.id}`} className="flex items-start justify-between gap-3 py-3 first:pt-0 last:pb-0"><div><div className="font-medium text-gray-800">{item.case_code} · {item.title}</div><div className="mt-1 text-xs text-gray-500">{item.next_action || t('Follow-up required')}</div></div><div className="shrink-0 text-right"><StatusBadge value={item.severity} /><div className="mt-1 text-xs text-gray-500">{fmtDate(item.due_date)}</div></div></Link>)}</div> : <Empty>{t('No upcoming follow-ups are assigned to you.')}</Empty>}
        </Card>
        <div className="grid gap-4 xl:grid-cols-2">
          <Card title={t('Upcoming home visits')} actions={<Link className="text-xs text-brand-700 hover:underline" to="/field">{t('Plan or record a visit')}</Link>}>
            {data.upcoming_visits?.length ? <div className="divide-y divide-gray-100">{data.upcoming_visits.map((visit) => <div key={visit.id} className="flex items-start justify-between gap-3 py-3 first:pt-0 last:pb-0"><div><div className="font-medium text-gray-800">{humanize(visit.purpose || 'home visit')}</div><div className="mt-1 text-xs text-gray-500">{fmtDate(visit.visit_date)} · {visit.girl_ids?.length || 0} {t('girls')}</div></div><StatusBadge value={visit.status} /></div>)}</div> : <Empty>{t('No home visits are planned.')}</Empty>}
          </Card>
          <Card title={t('Upcoming targets')} actions={<Link className="text-xs text-brand-700 hover:underline" to="/targets">{t('View targets')}</Link>}>
            {data.upcoming_targets?.length ? <div className="space-y-3">{data.upcoming_targets.map((target) => <div key={target.id}><div className="flex items-start justify-between gap-2 text-sm"><span className="font-medium text-gray-800">{target.title}</span><span className="shrink-0 text-xs text-gray-500">{fmtDate(target.period_start)}</span></div><div className="mt-1 text-xs text-gray-500">{t('Target')}: {target.target_value} · {humanize(target.metric || target.target_type)}</div></div>)}</div> : <Empty>{t('No future targets have been assigned yet.')}</Empty>}
          </Card>
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <Card title={t('Village contact checklist')} actions={<Link className="text-xs text-brand-700 hover:underline" to="/contacts">{t('Manage contacts')}</Link>}>
            <div className="space-y-2">{(data.contacts?.mandatory || []).map((contact) => (
              <div key={contact.category} className="flex items-center justify-between gap-3 rounded-lg bg-gray-50 px-3 py-2">
                <span className="text-sm text-gray-700">{t(humanize(contact.category))}</span>
                {contact.verified ? <span className="inline-flex items-center gap-1 text-xs text-green-700"><CheckCircle2 className="h-4 w-4" />{t('Verified')}</span> : <StatusBadge value={contact.present ? 'pending' : 'missing'} />}
              </div>
            ))}</div>
            {!data.contacts?.complete && <p className="mt-3 text-xs text-gray-500">{t('New or changed contact details must be verified by a Stakeholder.')}</p>}
          </Card>
          <Card title={t('Recent field activity')} actions={<Link className="text-xs text-brand-700 hover:underline" to="/field">{t('View records')}</Link>}>
            {[...(data.recent_visits || []).map((x) => ({ ...x, kind: 'visit', when: x.visit_date })), ...(data.recent_reports || []).map((x) => ({ ...x, kind: 'report', when: x.report_date }))]
              .sort((a, b) => new Date(b.when) - new Date(a.when)).slice(0, 6).map((item) => (
                <div key={`${item.kind}-${item.id}`} className="flex items-start gap-3 border-b border-gray-100 py-2 last:border-0">
                  <div className="mt-0.5 rounded-lg bg-gray-100 p-2 text-gray-600">{item.kind === 'visit' ? <MapPin className="h-4 w-4" /> : <Activity className="h-4 w-4" />}</div>
                  <div className="min-w-0 flex-1"><div className="text-sm font-medium text-gray-800">{item.kind === 'visit' ? t('Home visit') : t('Daily activity report')}</div><div className="text-xs text-gray-500">{fmtDate(item.when)} · {item.kind === 'visit' ? humanize(item.status) : (item.activities || []).map(humanize).join(', ')}</div></div>
                  {item.approval?.status && <StatusBadge value={item.approval.status} />}
                </div>
              ))}
            {!data.recent_visits?.length && !data.recent_reports?.length && <Empty>{t('Your saved field activity will appear here.')}</Empty>}
          </Card>
        </div>
        <div className="text-xs text-gray-500">{t('Assignment history is retained when your village changes.')} <Link to="/reports" className="text-brand-700 hover:underline">{t('View reports')}</Link></div>
      </>}
    </div>
  )
}
