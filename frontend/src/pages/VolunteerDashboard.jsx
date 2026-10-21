import { Activity, AlertTriangle, CalendarDays, Camera, CheckCircle2, ClipboardCheck, FileText, HeartPulse, MapPin, Mic, Phone, Users, RefreshCw } from 'lucide-react'
import 'leaflet/dist/leaflet.css'
import { CircleMarker, MapContainer, TileLayer, Tooltip as MapTooltip } from 'react-leaflet'
import { Link } from 'react-router-dom'
import { Button, Card, Empty, ErrorBox, PageHeader, ProgressBar, Spinner, StatTile, StatusBadge, Table } from '../components/ui'
import { fmtDate, fmtDateTime, humanize } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { t } from '../lib/i18n'
import { useEffect, useState } from 'react'
import { TrendChart } from '../components/charts'
import NoteCamModal from '../components/NoteCamModal'
import { useAuth } from '../lib/auth'
import api from '../lib/api'

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
            <StatTile label={t('Planned visits')} value={totals.visits_planned || 0} />
            <StatTile label={t('Completed visits')} value={totals.visits_completed || 0} />
            <StatTile label={t('Planned events')} value={totals.events_planned || 0} />
            <StatTile label={t('Events conducted')} value={totals.events_conducted || 0} />
            <StatTile label={t('Completion rate')} value={`${completionRate}%`} />
          </div>

          {data?.rows?.length ? (
            <>
              <TrendChart data={data.rows} series={series} xKey="label" height={300} />
              <div className="mt-4 rounded-lg bg-brand-50 p-3">
                <div className="mb-2 flex items-center justify-between gap-3 text-sm">
                  <span className="font-medium text-brand-900">{t('Overall completion')}</span>
                  <span className="font-semibold text-brand-800">{completionRate}%</span>
                </div>
                <div className="h-2.5 overflow-hidden rounded-full bg-white">
                  <div
                    className="h-full rounded-full bg-brand-600 transition-all"
                    style={{ width: `${Math.min(100, completionRate)}%` }}
                  />
                </div>
              </div>
            </>
          ) : (
            <Empty>{t('No planned or completed activities were found for this period.')}</Empty>
          )}
        </>
      )}
    </Card>
  )
}

export default function VolunteerDashboard() {
  const { user } = useAuth()
  const [selectedVillageId, setSelectedVillageId] = useState('')
  const [noteCamOpen, setNoteCamOpen] = useState(false)
  const [noteCamAction, setNoteCamAction] = useState('CHECK-IN')
  const [todayAttendance, setTodayAttendance] = useState(null)
  const [attLoading, setAttLoading] = useState(false)

  const url = selectedVillageId ? `/volunteers/me/dashboard?village_id=${selectedVillageId}` : '/volunteers/me/dashboard'
  const { data, error, loading, reload } = useFetch(url)

  // Fetch today's attendance status
  const fetchTodayAttendance = async () => {
    setAttLoading(true)
    try {
      const res = await api.get('/attendance/today')
      setTodayAttendance(res.data)
    } catch {
      // ignore
    } finally {
      setAttLoading(false)
    }
  }

  useEffect(() => {
    fetchTodayAttendance()

    const handleUpdate = () => {
      fetchTodayAttendance()
      reload()
    }
    window.addEventListener('kvp:attendance-updated', handleUpdate)

    // Restore pending NoteCam session if mobile browser was suspended/refreshed
    try {
      const saved = sessionStorage.getItem('kvp_notecam_pending')
      if (saved) {
        const item = JSON.parse(saved)
        if (Date.now() - (item.timestamp || 0) < 5 * 60 * 1000) {
          setNoteCamAction(item.action || 'CHECK-IN')
          if (item.villageId) setSelectedVillageId(item.villageId)
          setNoteCamOpen(true)
        }
      }
    } catch {}

    return () => {
      window.removeEventListener('kvp:attendance-updated', handleUpdate)
    }
  }, [])

  const openNoteCam = (action) => {
    setNoteCamAction(action)
    setNoteCamOpen(true)
  }

  const handleNoteCamSuccess = () => {
    fetchTodayAttendance()
    reload()
  }

  if (loading && !data) return <Spinner />

  const villages = data?.villages || (data?.village ? [data.village] : [])

  return (
    <div className="space-y-5 pb-16 lg:pb-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader
          title={t('My field dashboard')}
          subtitle={t('Tai field activities, visits, follow-ups and targets.')}
        />
        <Button size="sm" variant="secondary" icon={RefreshCw} onClick={() => { reload(); fetchTodayAttendance() }}>
          {t('Refresh')}
        </Button>
      </div>

      <ErrorBox message={error} />

      {data && !data.assigned && (
        <Card title={t('Village assignment needed')}>
          <p className="text-sm text-gray-600">
            {t('Your account is active, but no village is assigned yet. Contact your Stakeholder / Admin to receive an assignment before recording field work.')}
          </p>
        </Card>
      )}

      {data?.assigned && (
        <>
          {/* NoteCam Daily Check-In / Check-Out Widget */}
          <div className="relative overflow-hidden rounded-2xl shadow-sm transition">
            {!todayAttendance?.checked_in ? (
              <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-gradient-to-r from-emerald-600 to-teal-700 p-5 text-white">
                <div>
                  <div className="text-xs uppercase font-bold tracking-wider text-emerald-100 flex items-center gap-1.5">
                    <Camera className="h-4 w-4" /> {t('Daily Field Attendance')}
                  </div>
                  <h3 className="text-lg font-bold mt-1">{t('You have not checked in today')}</h3>
                  <p className="text-xs text-emerald-100 mt-0.5">
                    {t('Capture your NoteCam photo with GPS & village stamp to mark attendance.')}
                  </p>
                </div>
                <Button
                  onClick={() => openNoteCam('CHECK-IN')}
                  className="w-full sm:w-auto bg-white text-emerald-800 hover:bg-emerald-50 font-bold px-5 py-2.5 shadow transition active:scale-95"
                >
                  <Camera className="mr-2 h-5 w-5 text-emerald-700" />
                  {t('NoteCam Check-In')}
                </Button>
              </div>
            ) : !todayAttendance?.checked_out ? (
              <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-gradient-to-r from-blue-700 to-indigo-800 p-5 text-white">
                <div className="flex items-center gap-3 min-w-0">
                  {todayAttendance.record?.check_in_photo && (
                    <img
                      src={todayAttendance.record.check_in_photo}
                      alt="Check-in thumbnail"
                      className="h-14 w-14 shrink-0 rounded-xl object-cover border-2 border-white/60 shadow"
                    />
                  )}
                  <div className="min-w-0">
                    <div className="text-xs uppercase font-bold tracking-wider text-blue-200 flex items-center gap-1.5">
                      <CheckCircle2 className="h-4 w-4 text-emerald-400" /> {t('Currently Checked In')}
                    </div>
                    <h3 className="text-base sm:text-lg font-bold mt-0.5 truncate">
                      {t('Checked In at')} {todayAttendance.record?.check_in}
                    </h3>
                    <p className="text-xs text-blue-100 mt-0.5 truncate">
                      📍 {todayAttendance.record?.village_name || getVillageName(data.village)}
                    </p>
                  </div>
                </div>
                <Button
                  onClick={() => openNoteCam('CHECK-OUT')}
                  className="w-full sm:w-auto bg-amber-500 hover:bg-amber-600 text-white font-bold px-5 py-2.5 shadow transition active:scale-95"
                >
                  <Camera className="mr-2 h-5 w-5" />
                  {t('NoteCam Check-Out')}
                </Button>
              </div>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-3 bg-emerald-50 border border-emerald-200 p-4 text-emerald-900">
                <div className="flex items-center gap-3">
                  <CheckCircle2 className="h-6 w-6 text-emerald-600 shrink-0" />
                  <div>
                    <div className="text-xs uppercase font-bold text-emerald-700">{t('Day Attendance Completed')}</div>
                    <div className="text-sm font-semibold mt-0.5">
                      {t('In')}: {todayAttendance.record?.check_in} · {t('Out')}: {todayAttendance.record?.check_out}
                    </div>
                    <div className="text-xs text-emerald-600 mt-0.5">
                      📍 {todayAttendance.record?.village_name || getVillageName(data.village)}
                    </div>
                  </div>
                </div>
                <span className="text-xs font-semibold bg-emerald-100 text-emerald-800 px-3 py-1 rounded-full border border-emerald-300">
                  {t('Present')}
                </span>
              </div>
            )}
          </div>

          {/* Multi-Village Context Switcher Bar */}
          {villages.length > 1 && (
            <Card padded={false} className="border-brand-200 bg-white">
              <div className="flex items-center gap-2 overflow-x-auto p-2">
                <span className="px-2 text-xs font-bold uppercase tracking-wider text-gray-500 shrink-0">
                  {t('Assigned Villages')}:
                </span>
                {villages.map((v) => {
                  const isActive = String(v.id) === String(data.selected_village_id || data.village?.id)
                  return (
                    <button
                      key={v.id}
                      type="button"
                      onClick={() => setSelectedVillageId(v.id)}
                      className={`flex items-center gap-1.5 whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                        isActive
                          ? 'bg-brand-700 text-white shadow-sm'
                          : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      <MapPin className="h-3.5 w-3.5" />
                      {getVillageName(v)}
                    </button>
                  )
                })}
              </div>
            </Card>
          )}

          {/* Active Village Info Banner */}
          <Card className="border-brand-200 bg-brand-50/50">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="mb-1 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand-700">
                  <MapPin className="h-4 w-4" />
                  {t('Active Village Context')}
                  {villages.length > 1 && <span className="ml-1 rounded bg-brand-200 px-1.5 py-0.2 text-[10px] text-brand-900">{t('{n} villages assigned', { n: villages.length })}</span>}
                </div>
                <h2 className="text-xl font-bold text-gray-900">{getVillageName(data.village)}</h2>
                <p className="mt-1 text-sm text-gray-600">{data.village?.taluka_name || data.village?.district || ''}</p>
                <p className="mt-2 text-xs text-gray-500">
                  {t('{n} active groups', { n: data.groups?.length || 0 })} · {t('Month started {date}', { date: fmtDate(data.month_start) })}
                </p>
              </div>
            </div>
          </Card>

          {/* Stat Tiles (Mobile Responsive) */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
            <StatTile label={t('Assigned girls')} value={data.summary?.girls_total || 0} sub={t('{n} active', { n: data.summary?.girls_active || 0 })} />
            <StatTile label={t('Visits today')} value={data.summary?.home_visits_today || 0} />
            <StatTile label={t('Visits this week')} value={data.summary?.home_visits_this_week || 0} />
            <StatTile label={t('Visits this month')} value={data.summary?.home_visits_this_month || 0} />
            <StatTile label={t('Girls reached')} value={data.summary?.girls_covered || 0} />
            <StatTile label={t('Open follow-ups')} value={data.open_cases || 0} tone={data.open_cases ? 'alert' : undefined} />
          </div>

          <PlannedVsActual />

          {/* Quick Action Tiles (Mobile-First Touch Optimized) */}
          <section>
            <h2 className="mb-3 text-sm font-semibold text-gray-900">{t('Quick actions')}</h2>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
              {QUICK_LINKS.map(({ to, label, description, icon: Icon }) => (
                <Link
                  key={`${to}-${label}`}
                  to={to}
                  className="group flex flex-col justify-between rounded-xl border border-gray-200 bg-white p-3.5 shadow-sm transition hover:border-brand-300 hover:bg-brand-50/40 active:scale-98"
                >
                  <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
                    <Icon className="h-5 w-5" />
                  </div>
                  <div>
                    <div className="font-semibold text-gray-900 text-sm leading-tight">{t(label)}</div>
                    <div className="mt-1 text-xs text-gray-500 line-clamp-1">{t(description)}</div>
                  </div>
                </Link>
              ))}
            </div>
          </section>

          {/* Village Map and Groups */}
          <div className="grid gap-4 xl:grid-cols-2">
            <Card title={t('Assigned village map')}>
              {data.village?.location?.lat != null && data.village?.location?.lng != null ? (
                <div className="h-64 overflow-hidden rounded-lg border border-black/10">
                  <MapContainer center={[data.village.location.lat, data.village.location.lng]} zoom={12} scrollWheelZoom={false} className="h-full w-full">
                    <TileLayer attribution="&copy; OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                    <CircleMarker center={[data.village.location.lat, data.village.location.lng]} radius={10} pathOptions={{ color: '#ffffff', weight: 2, fillColor: '#0f766e', fillOpacity: 1 }}>
                      <MapTooltip>{getVillageName(data.village)}</MapTooltip>
                    </CircleMarker>
                    {(data.recent_visits || []).filter((visit) => visit.gps?.lat != null && visit.gps?.lng != null).map((visit) => (
                      <CircleMarker key={visit.id} center={[visit.gps.lat, visit.gps.lng]} radius={6} pathOptions={{ color: '#ffffff', weight: 1, fillColor: '#2563eb', fillOpacity: 0.9 }}>
                        <MapTooltip>{t('Home visit')} · {fmtDate(visit.visit_date)}</MapTooltip>
                      </CircleMarker>
                    ))}
                  </MapContainer>
                </div>
              ) : (
                <p className="rounded-lg bg-gray-50 p-4 text-sm text-gray-600">
                  {t('Village coordinates have not been added yet. GPS-tagged visits will appear on this map when available.')}
                </p>
              )}
            </Card>

            <Card title={t('Girls by Kishori Group')}>
              {data.groups?.length ? (
                <div className="space-y-3">
                  {data.groups.map((group) => (
                    <div key={group.id}>
                      <div className="mb-1 flex items-center justify-between gap-2 text-sm">
                        <Link className="font-medium text-gray-800 hover:text-brand-700" to={`/groups/${group.id}`}>
                          {group.name}
                        </Link>
                        <span className="text-xs text-gray-500">{group.girl_count || 0} {t('girls')}</span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-gray-100">
                        <div
                          className="h-full rounded-full bg-brand-600"
                          style={{ width: `${Math.min(100, (group.girl_count || 0) / Math.max(1, data.summary?.girls_total || 1) * 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty>{t('No active groups in this village yet.')}</Empty>
              )}
            </Card>
          </div>

          {/* Current Targets */}
          <div className="grid gap-4 xl:grid-cols-2">
            <Card title={t('My current targets')} actions={<Link className="text-xs text-brand-700 hover:underline" to="/targets">{t('View all')}</Link>}>
              {data.targets?.length ? (
                <div className="space-y-4">
                  {data.targets.map((target) => (
                    <div key={target.id}>
                      <div className="mb-1 flex flex-wrap items-center justify-between gap-2 text-sm">
                        <span className="font-medium text-gray-800">{target.title}</span>
                        <StatusBadge value={target.progress?.status} />
                      </div>
                      <ProgressBar pct={target.progress?.progress_pct} />
                      <div className="mt-1 flex justify-between gap-2 text-xs text-gray-500">
                        <span>{target.progress?.achieved || 0} / {target.target_value}</span>
                        <span>{t('{n} days left', { n: target.progress?.days_left || 0 })}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty>{t('No active targets assigned for this period.')}</Empty>
              )}
            </Card>

            <Card title={t('Upcoming events')} actions={<Link className="text-xs text-brand-700 hover:underline" to="/events">{t('All events')}</Link>}>
              {data.upcoming_events?.length ? (
                <div className="divide-y divide-gray-100">
                  {data.upcoming_events.map((event) => (
                    <Link key={event.id} to={`/events/${event.id}`} className="flex items-start justify-between gap-3 py-3 first:pt-0 last:pb-0 hover:text-brand-700">
                      <div>
                        <div className="font-medium text-gray-800">{event.title}</div>
                        <div className="mt-1 text-xs text-gray-500">
                          {fmtDateTime(event.start_at)}{event.location_name ? ` · ${event.location_name}` : ''}
                        </div>
                      </div>
                      <StatusBadge value={event.display_status || event.status} />
                    </Link>
                  ))}
                </div>
              ) : (
                <Empty>{t('No upcoming events are scheduled for your village.')}</Empty>
              )}
            </Card>
          </div>

          {/* Upcoming visits & Recent field activity */}
          <div className="grid gap-4 xl:grid-cols-2">
            <Card title={t('Upcoming home visits')} actions={<Link className="text-xs text-brand-700 hover:underline" to="/field">{t('Plan or record a visit')}</Link>}>
              {data.upcoming_visits?.length ? (
                <div className="divide-y divide-gray-100">
                  {data.upcoming_visits.map((visit) => (
                    <div key={visit.id} className="flex items-start justify-between gap-3 py-3 first:pt-0 last:pb-0">
                      <div>
                        <div className="font-medium text-gray-800">{humanize(visit.purpose || 'home visit')}</div>
                        <div className="mt-1 text-xs text-gray-500">{fmtDate(visit.visit_date)} · {visit.girl_ids?.length || 0} {t('girls')}</div>
                      </div>
                      <StatusBadge value={visit.status} />
                    </div>
                  ))}
                </div>
              ) : (
                <Empty>{t('No home visits are planned.')}</Empty>
              )}
            </Card>

            <Card title={t('Recent field activity')} actions={<Link className="text-xs text-brand-700 hover:underline" to="/field">{t('View records')}</Link>}>
              {[...(data.recent_visits || []).map((x) => ({ ...x, kind: 'visit', when: x.visit_date })), ...(data.recent_reports || []).map((x) => ({ ...x, kind: 'report', when: x.report_date }))]
                .sort((a, b) => new Date(b.when) - new Date(a.when)).slice(0, 6).map((item) => (
                  <div key={`${item.kind}-${item.id}`} className="flex items-start gap-3 border-b border-gray-100 py-2 last:border-0">
                    <div className="mt-0.5 rounded-lg bg-gray-100 p-2 text-gray-600">{item.kind === 'visit' ? <MapPin className="h-4 w-4" /> : <Activity className="h-4 w-4" />}</div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium text-gray-800">{item.kind === 'visit' ? t('Home visit') : t('Daily activity report')}</div>
                      <div className="text-xs text-gray-500">{fmtDate(item.when)} · {item.kind === 'visit' ? humanize(item.status) : (item.activities || []).map(humanize).join(', ')}</div>
                    </div>
                    {item.approval?.status && <StatusBadge value={item.approval.status} />}
                  </div>
                ))}
              {!data.recent_visits?.length && !data.recent_reports?.length && <Empty>{t('Your saved field activity will appear here.')}</Empty>}
            </Card>
          </div>
        </>
      )}

      {/* NoteCam Check-In / Check-Out Modal */}
      <NoteCamModal
        open={noteCamOpen}
        onClose={() => setNoteCamOpen(false)}
        action={noteCamAction}
        user={user}
        villages={villages}
        selectedVillageId={selectedVillageId || data?.selected_village_id || data?.village?.id}
        onSuccess={handleNoteCamSuccess}
      />
    </div>
  )
}
