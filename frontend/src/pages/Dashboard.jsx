import 'leaflet/dist/leaflet.css'
import { AlertTriangle, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { CircleMarker, MapContainer, TileLayer, Tooltip as MapTooltip } from 'react-leaflet'
import { Link } from 'react-router-dom'
import { BarList, GroupedBars, STATUS, TrendChart } from '../components/charts'
import { TalukaSelect } from '../components/pickers'
import { Card, ErrorBox, Field, PageHeader, ProgressBar, Select, Spinner, StatTile, StatusBadge, Table, Tabs } from '../components/ui'
import { fmtNum, humanize } from '../lib/format'
import { useAuth } from '../lib/auth'
import { useFetch } from '../lib/hooks'
import { localName, t } from '../lib/i18n'

const VILLAGE_STATUS_COLOR = { on_track: STATUS.good, delayed: STATUS.warning, no_recent_activity: STATUS.critical }
const SEVERITY_COLOR = { critical: STATUS.critical, high: STATUS.serious, medium: STATUS.warning, low: '#898781' }

function Kpis({ taluka, period }) {
  const { data: s, error } = useFetch('/dashboard/summary', { taluka_id: taluka, period })
  if (error) return <ErrorBox message={error} />
  if (!s) return <Spinner />
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
      <StatTile label={t('Girls enrolled')} value={fmtNum(s.girls_enrolled)} sub={t('{n} registered', { n: fmtNum(s.girls_total) })} />
      <StatTile label={t('Villages · Talukas')} value={`${s.villages} · ${s.talukas}`} sub={t('{n} district', { n: s.districts })} />
      <StatTile label={t('Kishori Groups')} value={s.kishori_groups} sub={t('{n} Bal Panchayat', { n: s.bal_panchayat_groups })} />
      <StatTile label={t('Active volunteers')} value={s.active_volunteers} />
      <StatTile label={t('Events conducted')} value={s.events_conducted} sub={t('{a} upcoming · {b} overdue', { a: s.events_upcoming, b: s.events_overdue })} />
      <StatTile label={t('Home visits')} value={fmtNum(s.home_visits)} sub={`${humanize(period)} · ${t('{n} girls reached', { n: fmtNum(s.girls_reached) })}`} />
      <StatTile label={t('Group meetings')} value={fmtNum(s.group_meetings)} sub={t('{n} event attendances', { n: fmtNum(s.event_attendance) })} />
      <StatTile label={t('Open cases')} value={s.open_cases} sub={t('{n} critical', { n: s.critical_open_cases })} tone={s.critical_open_cases ? 'alert' : undefined} />
    </div>
  )
}

function Trends({ taluka }) {
  const [granularity, setGranularity] = useState('monthly')
  const { data } = useFetch('/dashboard/trends', { taluka_id: taluka, granularity })
  return (
    <Card
      title={t('Field activity over time')}
      actions={<Select options={['daily', 'weekly', 'monthly']} value={granularity} onChange={(e) => setGranularity(e.target.value)} />}
    >
      {!data ? (
        <Spinner />
      ) : (
        <TrendChart
          data={data.series}
          series={[
            { key: 'home_visits', label: t('Home visits') },
            { key: 'group_meetings', label: t('Group meetings') },
            { key: 'events_completed', label: t('Events completed') },
          ]}
        />
      )}
    </Card>
  )
}

function CasesCard({ taluka }) {
  const { data } = useFetch('/dashboard/cases', { taluka_id: taluka })
  if (!data) return <Card title={t('Open cases')}><Spinner /></Card>
  const severities = ['critical', 'high', 'medium', 'low'].map((s) => ({
    label: humanize(s), value: data.by_severity[s] || 0, color: SEVERITY_COLOR[s],
  }))
  const categories = Object.entries(data.by_category).map(([k, v]) => ({ label: humanize(k), value: v }))
  return (
    <Card title={t('Open cases')} actions={<Link to="/cases" className="text-xs text-brand-700 hover:underline">{t('All cases')}</Link>}>
      <div className="mb-3 grid grid-cols-3 gap-2 text-center text-xs text-gray-600">
        <div><div className="text-lg font-semibold text-gray-900">{data.overdue}</div>{t('overdue')}</div>
        <div><div className="text-lg font-semibold text-gray-900">{data.opened_last_30_days}</div>{t('opened (30d)')}</div>
        <div><div className="text-lg font-semibold text-gray-900">{data.resolved_last_30_days}</div>{t('resolved (30d)')}</div>
      </div>
      {severities.some((x) => x.value) ? (
        <>
          <div className="text-xs font-medium text-gray-500">{t('By severity')}</div>
          <BarList items={severities} />
        </>
      ) : (
        <p className="py-6 text-center text-sm text-gray-500">{t('No open cases.')}</p>
      )}
      {categories.length > 0 && (
        <>
          <div className="mt-3 text-xs font-medium text-gray-500">{t('By category')}</div>
          <BarList items={categories} />
        </>
      )}
    </Card>
  )
}

function VillagesCard({ taluka }) {
  const { data } = useFetch('/dashboard/villages', { taluka_id: taluka })
  if (!data) return <Card title={t('Village activity status')}><Spinner /></Card>
  const mapped = data.villages.filter((v) => v.location)
  return (
    <Card title={t('Village activity status')}>
      <div className="mb-3 flex flex-wrap gap-3 text-xs">
        {Object.entries(data.counts).map(([k, n]) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: VILLAGE_STATUS_COLOR[k] }} />
            {humanize(k)}: <b>{n}</b>
          </span>
        ))}
      </div>
      {mapped.length > 0 ? (
        <div className="mb-3 h-64 overflow-hidden rounded-lg border border-black/10">
          <MapContainer bounds={mapped.map((v) => [v.location.lat, v.location.lng])} boundsOptions={{ padding: [30, 30] }} className="h-full w-full">
            <TileLayer attribution="&copy; OpenStreetMap" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            {mapped.map((v) => (
              <CircleMarker key={v.village_id} center={[v.location.lat, v.location.lng]} radius={9}
                pathOptions={{ color: '#fcfcfb', weight: 2, fillColor: VILLAGE_STATUS_COLOR[v.status], fillOpacity: 1 }}>
                <MapTooltip>{localName(v)} — {humanize(v.status)}</MapTooltip>
              </CircleMarker>
            ))}
          </MapContainer>
        </div>
      ) : (
        <p className="mb-3 rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-600">
          {t('Map appears once village coordinates are added (Villages → Set locations).')} {t('{n} villages unmapped.', { n: data.unmapped.length })}
        </p>
      )}
      <div className="max-h-72 overflow-y-auto">
        <Table
          rowKey={(r) => r.village_id}
          columns={[
            { key: 'name', label: t('Village'), render: (r) => <Link className="text-brand-700 hover:underline" to={`/villages/${r.village_id}`}>{localName(r)}</Link> },
            { key: 'status', label: t('Status'), render: (r) => <StatusBadge value={r.status} /> },
            { key: 'days_since', label: t('Last activity'), render: (r) => (r.days_since === null ? t('Never') : t('{n}d ago', { n: r.days_since })) },
            { key: 'home_visits_this_month', label: t('Visits (month)'), className: 'tabular text-right' },
            { key: 'open_cases', label: t('Open cases'), className: 'tabular text-right' },
          ]}
          rows={data.villages}
        />
      </div>
    </Card>
  )
}

function TargetsCard({ taluka }) {
  const { data } = useFetch('/dashboard/targets', { taluka_id: taluka || undefined })
  return (
    <Card title={t('Tai target achievement (current active targets)')} actions={<Link to="/targets" className="text-xs text-brand-700 hover:underline">{t('Manage targets →')}</Link>}>
      {!data ? <Spinner /> : (
        <Table
          empty={t('No active targets running. Set targets under Targets.')}
          rowKey={(r) => r.volunteer_id}
          columns={[
            { key: 'name', label: t('Tai'), render: (r) => <Link className="font-medium text-brand-700 hover:underline" to={`/volunteers/${r.volunteer_id}`}>{r.name}</Link> },
            { key: 'targets', label: t('Active targets'), render: (r) => (
              <div className="flex flex-wrap gap-1.5">
                {(r.targets || []).map((tg) => (
                  <span key={tg.id} className="inline-flex items-center gap-1 rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-800">
                    <span className="font-medium">{tg.title}</span>: {tg.achieved || 0}/{tg.target_value}
                  </span>
                ))}
                {!(r.targets?.length) && <span className="text-xs text-gray-400">{t('None')}</span>}
              </div>
            )},
            { key: 'avg', label: t('Average achievement'), render: (r) => <ProgressBar pct={r.avg_achievement_pct} /> },
            { key: 'at_risk_or_missed', label: t('At risk / missed'), className: 'tabular text-right' },
          ]}
          rows={data.volunteers}
        />
      )}
    </Card>
  )
}

function HealthCard({ taluka }) {
  const { data } = useFetch('/dashboard/health', { taluka_id: taluka })
  const { data: part } = useFetch('/dashboard/participation', { taluka_id: taluka })
  if (!data) return <Card title={t('Health & impact')}><Spinner /></Card>
  const anaemia = ['normal', 'mild', 'moderate', 'severe'].map((k) => ({
    label: humanize(k), value: data.anaemia_distribution[k] || 0,
    color: { normal: STATUS.good, mild: STATUS.warning, moderate: STATUS.serious, severe: STATUS.critical }[k],
  }))
  return (
    <Card title={t('Health & impact indicators')}>
      <div className="mb-3 grid grid-cols-3 gap-2 text-center text-xs text-gray-600">
        <div><div className="text-lg font-semibold text-gray-900">{data.hb_screening_coverage_pct ?? 0}%</div>{t('Hb screened')}</div>
        <div><div className="text-lg font-semibold text-gray-900">{data.anaemia_prevalence_pct ?? '—'}{data.anaemia_prevalence_pct != null && '%'}</div>{t('anaemic')}</div>
        <div><div className="text-lg font-semibold text-gray-900">{part?.active_participation_pct ?? 0}%</div>{t('active (90d)')}</div>
      </div>
      {data.hb_screened ? <BarList items={anaemia} valueLabel={t('Girls')} /> : <p className="text-xs text-gray-500">{t('No Hb screenings recorded yet.')}</p>}
      <div className="mt-3 text-xs text-gray-600">
        {t('Age')} 10–14: <b>{data.age_bands['10_14']}</b> · 15–19: <b>{data.age_bands['15_19']}</b> · {t('age unknown')}: <b>{data.age_bands.unknown}</b>
      </div>
    </Card>
  )
}

function AlertsCard({ taluka }) {
  const { data } = useFetch('/dashboard/alerts', { taluka_id: taluka })
  const [tab, setTab] = useState('unresolved_cases')
  if (!data) return <Card title={t('Alerts')}><Spinner /></Card>
  const tabs = [
    { value: 'unresolved_cases', label: `${t('Cases')} (${data.counts.unresolved_cases})` },
    { value: 'overdue_reports', label: `${t('Overdue reports')} (${data.counts.overdue_reports})` },
    { value: 'missed_targets', label: `${t('Targets')} (${data.counts.missed_targets})` },
    { value: 'inactive_villages', label: `${t('Inactive villages')} (${data.counts.inactive_villages})` },
    { value: 'missing_village_contacts', label: `${t('Contact gaps')} (${data.counts.missing_village_contacts})` },
  ]
  const cols = {
    unresolved_cases: [
      { key: 'case_code', label: t('Case'), render: (r) => <Link className="text-brand-700 hover:underline" to={`/cases/${r.case_id}`}>{r.case_code}</Link> },
      { key: 'severity', label: t('Severity'), render: (r) => <StatusBadge value={r.severity} /> },
      { key: 'category', label: t('Category'), render: (r) => humanize(r.category) },
      { key: 'village', label: t('Village') },
      { key: 'overdue_days', label: t('Overdue (days)'), className: 'tabular text-right' },
      { key: 'needs_escalation', label: '', render: (r) => r.needs_escalation && <span className="text-xs text-orange-700">{t('Escalate')}</span> },
    ],
    overdue_reports: [
      { key: 'type', label: t('Type'), render: (r) => humanize(r.type) },
      { key: 'who', label: t('Volunteer / event'), render: (r) => r.volunteer || r.title },
      { key: 'village', label: t('Village') },
      { key: 'detail', label: t('Detail'), render: (r) => (r.count ? t('{n} missing day(s)', { n: r.count }) : t('{n} day(s) overdue', { n: r.days_overdue })) },
    ],
    missed_targets: [
      { key: 'title', label: t('Target') },
      { key: 'volunteer', label: t('Volunteer') },
      { key: 'status', label: t('Status'), render: (r) => <StatusBadge value={r.status} /> },
      { key: 'progress', label: t('Progress'), render: (r) => `${r.achieved}/${r.target_value}` },
    ],
    inactive_villages: [
      { key: 'village', label: t('Village') },
      { key: 'status', label: t('Status'), render: (r) => <StatusBadge value={r.status} /> },
      { key: 'days_since', label: t('Last activity'), render: (r) => (r.days_since === null ? t('Never') : t('{n}d ago', { n: r.days_since })) },
    ],
    missing_village_contacts: [
      { key: 'village', label: t('Village') },
      { key: 'missing', label: t('Missing'), render: (r) => r.missing.map(humanize).join(', ') },
    ],
  }
  return (
    <Card title={<span className="inline-flex items-center gap-1.5"><AlertTriangle className="h-4 w-4 text-orange-600" /> {t('Alerts')}</span>}>
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      <div className="max-h-80 overflow-y-auto">
        <Table rowKey={(r) => r.case_id || r.event_id || r.target_id || r.volunteer_id || r.village_id} columns={cols[tab]} rows={data[tab]} empty={t('No alerts here.')} />
      </div>
    </Card>
  )
}

function PastUpcoming({ taluka }) {
  const { data } = useFetch('/dashboard/past-vs-upcoming', { taluka_id: taluka })
  if (!data) return <Card title={t('Past vs upcoming')}><Spinner /></Card>
  return (
    <Card title={t('Past activity vs upcoming plans')}>
      <div className="grid gap-4 lg:grid-cols-2">
        <div>
          <div className="mb-1 text-xs font-medium text-gray-500">{t('Past months (actual)')}</div>
          <GroupedBars data={data.past} xKey="period" series={[
            { key: 'events_planned', label: t('Events planned') },
            { key: 'events_completed', label: t('Events completed') },
            { key: 'home_visits', label: t('Home visits') },
          ]} />
        </div>
        <div>
          <div className="mb-1 text-xs font-medium text-gray-500">{t('Coming months (planned)')}</div>
          <GroupedBars data={data.upcoming} xKey="period" series={[
            { key: 'events_planned', label: t('Events planned') },
            { key: 'visits_planned', label: t('Visits planned') },
            { key: 'targets_starting', label: t('Targets starting') },
          ]} />
          <p className="mt-2 text-xs text-gray-600">{t('{n} case follow-ups due in this window.', { n: data.case_follow_ups_due })}</p>
        </div>
      </div>
    </Card>
  )
}

const LEVELS = ['district', 'taluka', 'village', 'group', 'girl']

function Drilldown() {
  const [trail, setTrail] = useState([{ level: 'district', parent: null, label: t('All districts') }])
  const current = trail[trail.length - 1]
  const { data } = useFetch('/dashboard/drilldown', { level: current.level, parent_id: current.parent })
  const next = (row) => {
    const idx = LEVELS.indexOf(current.level)
    if (idx < 0 || idx >= LEVELS.length - 1) return
    setTrail([...trail, { level: LEVELS[idx + 1], parent: row.id, label: localName(row) || row.girl_code }])
  }
  const metricCols = data?.rows?.[0]
    ? Object.keys(data.rows[0]).filter((k) => !['id', 'name', 'name_mr', 'name_en', 'next_level', 'village_id', 'responsible_volunteer_id', 'girl_code', 'last_participation_at'].includes(k))
    : []
  return (
    <Card title={t('Drill-down: district → taluka → village → group → girl')}>
      <div className="mb-3 flex flex-wrap items-center gap-1 text-sm">
        {trail.map((crumb, i) => (
          <span key={i} className="inline-flex items-center gap-1">
            {i > 0 && <ChevronRight className="h-3 w-3 text-gray-400" />}
            <button type="button" className={i === trail.length - 1 ? 'font-medium text-gray-900' : 'text-brand-700 hover:underline'}
              onClick={() => setTrail(trail.slice(0, i + 1))}>
              {crumb.label}
            </button>
          </span>
        ))}
      </div>
      {!data ? <Spinner /> : (
        <div className="max-h-96 overflow-y-auto">
          <Table
            onRowClick={current.level === 'girl' ? undefined : next}
            columns={[
              { key: 'name', label: humanize(current.level), render: (r) => current.level === 'girl'
                ? <Link to={`/girls/${r.id}`} className="text-brand-700 hover:underline">{r.girl_code} {r.name && `· ${localName(r)}`}</Link>
                : <span className="text-brand-700">{localName(r)}</span> },
              ...metricCols.map((k) => ({ key: k, label: humanize(k), render: (r) => (typeof r[k] === 'string' && r[k].includes('_') ? <StatusBadge value={r[k]} /> : fmtNum(r[k])) })),
            ]}
            rows={data.rows}
          />
        </div>
      )}
    </Card>
  )
}

export default function Dashboard() {
  const { user } = useAuth()
  const [taluka, setTaluka] = useState('')
  const [period, setPeriod] = useState('monthly')
  const isStakeholder = user?.role === 'stakeholder' || user?.role === 'super_admin'
  return (
    <div className="space-y-4">
      <PageHeader
        title={isStakeholder ? t('Stakeholder dashboard') : t('Admin dashboard')}
        subtitle={t('Programme-wide view of girls, villages, volunteers and field activity')}
        actions={
          <div className="flex flex-wrap items-end gap-2">
            <Field label={t('Taluka')}><TalukaSelect value={taluka} onChange={setTaluka} /></Field>
            <Field label={t('Period')}><Select options={['daily', 'weekly', 'monthly', 'quarterly', 'yearly']} value={period} onChange={(e) => setPeriod(e.target.value)} /></Field>
          </div>
        }
      />
      <Kpis taluka={taluka} period={period} />
      <AlertsCard taluka={taluka} />
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2"><Trends taluka={taluka} /></div>
        <CasesCard taluka={taluka} />
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2"><VillagesCard taluka={taluka} /></div>
        <HealthCard taluka={taluka} />
      </div>
      <TargetsCard taluka={taluka} />
      <PastUpcoming taluka={taluka} />
      <Drilldown />
    </div>
  )
}
