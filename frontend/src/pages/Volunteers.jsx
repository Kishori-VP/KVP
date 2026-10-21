import { Plus } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { GroupMultiSelect, VillageSelect } from '../components/pickers'
import { Badge, Button, Card, ErrorBox, Field, Input, Modal, PageHeader, ProgressBar, Select, Spinner, Table, Tabs } from '../components/ui'
import api from '../lib/api'
import { fmtDate } from '../lib/format'
import { invalidateRefData, useAction, useFetch } from '../lib/hooks'
import { t } from '../lib/i18n'

function AddTai({ onClose, onSaved }) {
  const [f, setF] = useState({ group_ids: [] })
  const { busy, error, run } = useAction()
  const save = () => run(async () => {
    const r = await api.post('/users', {
      role: 'volunteer', name: f.name, phone: f.phone, email: f.email || null, password: f.password,
      designation: f.designation || null, village_id: f.village_id || null, group_ids: f.village_id ? f.group_ids : [],
    })
    invalidateRefData()
    onSaved(r.data)
  }).catch(() => {})
  return (
    <Modal open title={t('Add Tai')} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button><Button busy={busy} disabled={!f.name || !f.phone || !f.password} onClick={save}>{t('Add Tai')}</Button></>}>
      <ErrorBox message={error} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t('Name *')}><Input value={f.name || ''} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label={t('Mobile * (used to log in)')}><Input value={f.phone || ''} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
        <Field label={t('Email')}><Input type="email" value={f.email || ''} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label={t('Designation')}><Input placeholder={t('e.g. Field worker')} value={f.designation || ''} onChange={(e) => setF({ ...f, designation: e.target.value })} /></Field>
        <Field label={t('Initial password * (min 8)')} className="sm:col-span-2"><Input type="password" value={f.password || ''} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
      </div>
      <Field label={t('Village (optional)')} hint={t('Assign a village to this Tai. Multiple villages can also be assigned from Tai details.')}>
        <VillageSelect value={f.village_id} onChange={(v) => setF({ ...f, village_id: v, group_ids: [] })} placeholder={t('Assign later')} />
      </Field>
      {f.village_id && <Field label={t('Kishori Groups')} group><GroupMultiSelect villageId={f.village_id} value={f.group_ids} onChange={(v) => setF({ ...f, group_ids: v })} /></Field>}
    </Modal>
  )
}

function Roster() {
  const nav = useNavigate()
  const [assigned, setAssigned] = useState('')
  const [adding, setAdding] = useState(false)
  const { data, error, reload } = useFetch('/volunteers', { assigned })
  if (error) return <ErrorBox message={error} />
  if (!data) return <Spinner />
  return (
    <Card padded={false} title={t('{n} Tai(s)', { n: data.length })} actions={<>
      <Select options={[{ value: 'true', label: t('Assigned to a village') }, { value: 'false', label: t('Not yet assigned') }]} placeholder={t('All Tais')}
        value={assigned} onChange={(e) => setAssigned(e.target.value)} />
      <Button size="sm" icon={Plus} onClick={() => setAdding(true)}>{t('Add Tai')}</Button>
    </>}>
      <Table onRowClick={(r) => nav(`/volunteers/${r.id}`)} columns={[
        { key: 'name', label: t('Tai'), className: 'font-medium' },
        { key: 'phone', label: t('Mobile') },
        { key: 'phone', label: t('Mobile') },
        { key: 'village_name', label: t('Village'), render: (r) => r.village_name || <Badge tone="yellow">{t('Not assigned')}</Badge> },
        { key: 'groups', label: t('Groups'), render: (r) => r.groups.map((g) => g.name).join(', ') || '—' },
        { key: 'home_visits_this_month', label: t('Visits (month)'), className: 'tabular text-right' },
        { key: 'open_cases', label: t('Open cases'), className: 'tabular text-right' },
        { key: 'last_report_date', label: t('Last daily report'), render: (r) => fmtDate(r.last_report_date) },
        { key: 'is_active', label: '', render: (r) => (!r.is_active ? <Badge>{t('Inactive')}</Badge> : null) },
      ]} rows={data} empty={t('No volunteers yet. Use “Add volunteer” — the village can be assigned later.')} />
      {adding && <AddTai onClose={() => setAdding(false)} onSaved={(v) => { setAdding(false); reload(); nav(`/volunteers/${v.id}`) }} />}
    </Card>
  )
}

function Performance() {
  const [period, setPeriod] = useState('monthly')
  const { data } = useFetch('/volunteers/performance', { period })
  return (
    <Card title={t('Performance against targets')} actions={<Select options={['daily', 'weekly', 'monthly', 'quarterly', 'yearly']} value={period} onChange={(e) => setPeriod(e.target.value)} />}>
      {!data ? <Spinner /> : (
        <Table rowKey={(r) => r.volunteer_id} columns={[
          { key: 'name', label: t('Tai'), render: (r) => <Link className="text-brand-700 hover:underline" to={`/volunteers/${r.volunteer_id}`}>{r.name}</Link> },
          { key: 'village_name', label: t('Village') },
          { key: 'hv', label: t('Home visits'), render: (r) => r.activity.home_visits, className: 'tabular text-right' },
          { key: 'gm', label: t('Meetings'), render: (r) => r.activity.group_meetings, className: 'tabular text-right' },
          { key: 'ev', label: t('Events'), render: (r) => r.activity.events, className: 'tabular text-right' },
          { key: 'gc', label: t('Girls reached'), render: (r) => r.activity.girls_covered, className: 'tabular text-right' },
          { key: 'avg', label: t('Target achievement'), render: (r) => (r.target_count ? <ProgressBar pct={r.avg_achievement_pct} /> : <span className="text-xs text-gray-400">{t('No targets')}</span>) },
          { key: 'st', label: t('At risk / missed'), render: (r) => r.targets_by_status.at_risk + r.targets_by_status.missed, className: 'tabular text-right' },
        ]} rows={data.volunteers} empty={t('No active volunteers.')} />
      )}
    </Card>
  )
}

function Submissions() {
  const [range, setRange] = useState({ start_date: '', end_date: '' })
  const { data } = useFetch('/volunteers/submission-status', range)
  return (
    <Card title={t('Submission status — who has not submitted expected reports')} actions={<>
      <Field><Input type="date" value={range.start_date} onChange={(e) => setRange({ ...range, start_date: e.target.value })} /></Field>
      <Field><Input type="date" value={range.end_date} onChange={(e) => setRange({ ...range, end_date: e.target.value })} /></Field>
    </>}>
      {!data ? <Spinner /> : (
        <>
          <p className="mb-2 text-sm text-gray-600">{fmtDate(data.start)} – {fmtDate(data.end)} · {t('{n} working days', { n: data.expected_days })} · <b>{data.defaulters}</b> {t('volunteer(s) behind')}</p>
          <Table rowKey={(r) => r.volunteer_id} columns={[
            { key: 'name', label: t('Tai'), render: (r) => <Link className="text-brand-700 hover:underline" to={`/volunteers/${r.volunteer_id}`}>{r.name}</Link> },
            { key: 'village_name', label: t('Village') },
            { key: 'sub', label: t('Daily reports'), render: (r) => `${r.submitted} / ${r.expected}` },
            { key: 'missing_dates', label: t('Missing dates'), render: (r) => r.missing_dates.map(fmtDate).join(', ') || '—' },
            { key: 'pending_event_reports', label: t('Event reports due'), className: 'tabular text-right' },
          ]} rows={data.volunteers} empty={t('No active volunteers.')} />
        </>
      )}
    </Card>
  )
}

export default function Volunteers() {
  const [tab, setTab] = useState('roster')
  return (
    <div>
      <PageHeader title={t('Tais')} subtitle={t('Field team · multiple village assignment · performance · report submission')} />
      <Tabs tabs={[{ value: 'roster', label: t('Roster') }, { value: 'performance', label: t('Performance') }, { value: 'submissions', label: t('Submission status') }]} value={tab} onChange={setTab} />
      {tab === 'roster' && <Roster />}
      {tab === 'performance' && <Performance />}
      {tab === 'submissions' && <Submissions />}
    </div>
  )
}
