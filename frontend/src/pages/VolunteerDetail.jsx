import { ArrowLeft, ArrowRightLeft, MapPin, Shuffle } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { TrendChart } from '../components/charts'
import { GroupMultiSelect, VillageSelect, VolunteerSelect } from '../components/pickers'
import { Badge, Button, Card, DefinitionList, ErrorBox, Field, Input, Modal, PageHeader, ProgressBar, Select, Spinner, StatTile, StatusBadge, Table, Tabs } from '../components/ui'
import HandoverModal from '../components/HandoverModal'
import api from '../lib/api'
import { fmtDate, fmtDateTime, humanize } from '../lib/format'
import { invalidateRefData, useAction, useFetch } from '../lib/hooks'
import { localName, t } from '../lib/i18n'

function ReassignModal({ open, onClose, vol, onDone }) {
  const [f, setF] = useState({ village_id: '', group_ids: [], reason: '', effective_date: '', action: 'move', transfer_to: '' })
  const { busy, error, run } = useAction()
  const submit = () => run(async () => {
    const r = await api.post(`/volunteers/${vol.id}/reassign`, {
      village_id: f.village_id, group_ids: f.group_ids, reason: f.reason, effective_date: f.effective_date || null,
      targets: { action: f.action, transfer_to_volunteer_id: f.action === 'transfer' ? f.transfer_to : null },
    })
    invalidateRefData()
    onDone(r.data)
  }).catch(() => {})
  return (
    <Modal open={open} title={t('Reassign {name}', { name: vol.name })} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button><Button busy={busy} disabled={!f.village_id || f.reason.length < 3 || (f.action === 'transfer' && !f.transfer_to)} onClick={submit}>{t('Reassign')}</Button></>}>
      <ErrorBox message={error} />
      <p className="text-sm text-gray-600">{t('A volunteer has exactly one village. The current assignment is closed and kept in the history.')}</p>
      <Field label={t('New village *')}><VillageSelect value={f.village_id} onChange={(v) => setF({ ...f, village_id: v, group_ids: [] })} placeholder={t('Select village')} /></Field>
      <Field label={t('Groups in the new village')} group><GroupMultiSelect villageId={f.village_id} value={f.group_ids} onChange={(v) => setF({ ...f, group_ids: v })} /></Field>
      <Field label={t('Effective date')}><Input type="date" value={f.effective_date} onChange={(e) => setF({ ...f, effective_date: e.target.value })} /></Field>
      <Field label={t('Open targets')}>
        <Select value={f.action} onChange={(e) => setF({ ...f, action: e.target.value })} options={[
          { value: 'move', label: t('Move them to the new village') },
          { value: 'close', label: t('Close (cancel) them') },
          { value: 'transfer', label: t('Transfer to another volunteer of the old village') },
        ]} />
      </Field>
      {f.action === 'transfer' && <Field label={t('Transfer to')}><VolunteerSelect villageId={vol.village_id} value={f.transfer_to} onChange={(v) => setF({ ...f, transfer_to: v })} placeholder={t('Select…')} /></Field>}
      <Field label={t('Reason *')}><Input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} /></Field>
    </Modal>
  )
}

function AssignModal({ open, onClose, vol, onDone }) {
  const [f, setF] = useState({ village_id: '', group_ids: [], effective_date: '' })
  const { busy, error, run } = useAction()
  const submit = () => run(async () => {
    await api.post(`/volunteers/${vol.id}/assign`, { village_id: f.village_id, group_ids: f.group_ids, effective_date: f.effective_date || null })
    invalidateRefData()
    onDone()
  }).catch(() => {})
  return (
    <Modal open={open} title={t('Assign a village to {name}', { name: vol.name })} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button><Button busy={busy} disabled={!f.village_id} onClick={submit}>{t('Assign')}</Button></>}>
      <ErrorBox message={error} />
      <p className="text-sm text-gray-600">{t('Assign another village to this Tai. A Tai can be assigned to multiple villages concurrently.')}</p>
      <Field label={t('Village *')}><VillageSelect value={f.village_id} onChange={(v) => setF({ ...f, village_id: v, group_ids: [] })} placeholder={t('Select village')} /></Field>
      <Field label={t('Kishori Groups')} group><GroupMultiSelect villageId={f.village_id} value={f.group_ids} onChange={(v) => setF({ ...f, group_ids: v })} /></Field>
      <Field label={t('Start date')}><Input type="date" value={f.effective_date} onChange={(e) => setF({ ...f, effective_date: e.target.value })} /></Field>
    </Modal>
  )
}

function GroupsModal({ open, onClose, vol, onDone }) {
  const [ids, setIds] = useState(vol.group_ids || [])
  const { busy, error, run } = useAction()
  const save = () => run(async () => { await api.put(`/volunteers/${vol.id}/groups`, { group_ids: ids }); onDone() }).catch(() => {})
  return (
    <Modal open={open} title={t('Assign Kishori Groups')} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button><Button busy={busy} onClick={save}>{t('Save')}</Button></>}>
      <ErrorBox message={error} />
      <GroupMultiSelect villageId={vol.village_id} value={ids} onChange={setIds} />
    </Modal>
  )
}

function Overview({ id }) {
  const { data: d } = useFetch(`/volunteers/${id}/dashboard`)
  if (!d) return <Spinner />
  const pf = d.pending_forms
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <StatTile label={t('Visits today')} value={d.home_visits.today} />
        <StatTile label={t('Visits this week')} value={d.home_visits.this_week} />
        <StatTile label={t('Visits this month')} value={d.home_visits.this_month} />
        <StatTile label={t('Events (month)')} value={d.events.completed_this_month} sub={t('{n} upcoming', { n: d.events.upcoming.length })} />
        <StatTile label={t('Open cases')} value={d.open_cases} sub={t('{n} in village', { n: d.village_open_cases })} />
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={t('Current targets')}>
          <Table columns={[
            { key: 'title', label: t('Target') },
            { key: 'p', label: t('Progress'), render: (tg) => <ProgressBar pct={tg.progress.progress_pct} status={tg.progress.status} /> },
            { key: 's', label: t('Status'), render: (tg) => <StatusBadge value={tg.progress.status} /> },
            { key: 'd', label: t('Days left'), render: (tg) => tg.progress.days_left },
          ]} rows={d.targets} empty={t('No running targets.')} />
        </Card>
        <Card title={t('Pending forms & overdue actions')}>
          <DefinitionList items={[
            ['Missing daily reports (7 days)', pf.missing_daily_reports.length ? pf.missing_daily_reports.map(fmtDate).join(', ') : t('None')],
            ['Event reports due', pf.event_reports_due],
            ['Planned visits not completed', pf.planned_visits_not_completed],
            ['Overdue cases', d.overdue_actions.cases.length],
          ]} />
          {d.overdue_actions.cases.length > 0 && (
            <ul className="mt-2 space-y-1 text-sm">
              {d.overdue_actions.cases.map((c) => <li key={c.id}><Link className="text-brand-700 hover:underline" to={`/cases/${c.id}`}>{c.case_code}</Link> · {c.title}</li>)}
            </ul>
          )}
        </Card>
        <Card title={t('Upcoming events')}>
          <Table columns={[{ key: 'start_at', label: t('When'), render: (e) => fmtDateTime(e.start_at) }, { key: 'title', label: t('Event'), render: (e) => <Link className="text-brand-700 hover:underline" to={`/events/${e.id}`}>{e.title}</Link> }]} rows={d.events.upcoming} empty={t('None scheduled.')} />
        </Card>
        <Card title={t('Upcoming planned visits')}>
          <Table columns={[{ key: 'visit_date', label: t('Date'), render: (v) => fmtDate(v.visit_date) }, { key: 'purpose', label: t('Purpose'), render: (v) => humanize(v.purpose) }]} rows={d.upcoming_visits} empty={t('None planned.')} />
        </Card>
      </div>
    </div>
  )
}

function Activity({ id }) {
  const [granularity, setGranularity] = useState('daily')
  const { data } = useFetch(`/volunteers/${id}/activity`, { granularity })
  return (
    <Card title={t('Activity')} actions={<Select options={['daily', 'weekly', 'monthly']} value={granularity} onChange={(e) => setGranularity(e.target.value)} />}>
      {!data ? <Spinner /> : <TrendChart data={data.series} series={[{ key: 'home_visits', label: t('Home visits') }, { key: 'group_meetings', label: t('Group meetings') }, { key: 'activity_reports', label: t('Daily reports') }]} />}
    </Card>
  )
}

function Coverage({ id }) {
  const { data } = useFetch(`/volunteers/${id}/coverage`)
  if (!data) return <Spinner />
  return (
    <Card title={`${t('Field coverage')} · ${fmtDate(data.start)} – ${fmtDate(data.end)}`}>
      <DefinitionList items={[
        ['Girls reached', `${data.girls.reached} ${t('of')} ${data.girls.total} (${data.girls.coverage_pct ?? 0}%)`],
        ['Groups met', `${data.groups.met} ${t('of')} ${data.groups.total}`],
        ['Visits with GPS', data.visit_locations.length],
      ]} />
      {data.groups.not_met.length > 0 && <p className="mt-3 text-sm text-gray-700">Groups not met: {data.groups.not_met.map(localName).join(', ')}</p>}
    </Card>
  )
}

function History({ id }) {
  const { data } = useFetch(`/volunteers/${id}/history`)
  if (!data) return <Spinner />
  return <Card title={t('Activity history')}><Table rowKey={(r) => `${r.type}${r.id}${r.date}`} columns={[
    { key: 'date', label: t('Date'), render: (r) => fmtDateTime(r.date) }, { key: 'type', label: t('Type'), render: (r) => humanize(r.type) }, { key: 'summary', label: t('Summary') },
  ]} rows={data} empty={t('No activity yet.')} /></Card>
}

export default function VolunteerDetail() {
  const { id } = useParams()
  const { data: v, error, reload } = useFetch(`/volunteers/${id}`)
  const { data: hist, reload: reloadHist } = useFetch(`/volunteers/${id}/assignments`)
  const [tab, setTab] = useState('overview')
  const [modal, setModal] = useState(null)
  if (error) return <ErrorBox message={error} />
  if (!v) return <Spinner />
  const unassigned = !v.village_id
  return (
    <div className="space-y-4">
      <Link to="/volunteers" className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline"><ArrowLeft className="h-4 w-4" /> {t('Tais')}</Link>
      <PageHeader title={v.name}
        subtitle={<>{v.phone || t('No mobile yet')}{v.designation && ` · ${v.designation}`} · {unassigned ? t('No village yet') : <>{(v.villages?.length ? v.villages : [v.village]).map(localName).join(', ')}</>}</>}
        actions={unassigned
          ? <Button icon={MapPin} onClick={() => setModal('assign')}>{t('Assign village')}</Button>
          : <>
              <Button variant="secondary" icon={MapPin} onClick={() => setModal('assign')}>{t('Assign another village')}</Button>
              <Button variant="secondary" onClick={() => setModal('groups')}>{t('Groups')}</Button>
              <Button variant="secondary" icon={ArrowRightLeft} onClick={() => setModal('handover')}>{t('Handover village')}</Button>
              <Button icon={Shuffle} onClick={() => setModal('reassign')}>{t('Reassign village')}</Button>
            </>} />
      {unassigned && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {t('This volunteer is not assigned to a village yet. Assign one to give them targets, groups, events and village data.')}
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {!v.is_active && <Badge>{t('Inactive')}</Badge>}
        {(v.village_groups || []).filter((g) => g.assigned_to_this_volunteer).map((g) => <Badge key={g.id} tone="brand">{localName(g)}</Badge>)}
      </div>
      <Tabs tabs={unassigned ? ['overview', 'history', 'assignments'] : ['overview', 'activity', 'coverage', 'history', 'assignments']} value={tab} onChange={setTab} />
      {tab === 'overview' && <Overview id={id} />}
      {tab === 'activity' && <Activity id={id} />}
      {tab === 'coverage' && <Coverage id={id} />}
      {tab === 'history' && <History id={id} />}
      {tab === 'assignments' && (
        <Card title={t('Village assignment history')}>
          <Table columns={[
            { key: 'village_name', label: t('Village') }, { key: 'start_date', label: t('From'), render: (r) => fmtDate(r.start_date) },
            { key: 'end_date', label: t('To'), render: (r) => (r.is_current ? <Badge tone="green">{t('Current')}</Badge> : fmtDate(r.end_date)) },
            { key: 'reason', label: t('Reason') }, { key: 'assigned_by_name', label: t('By') },
          ]} rows={hist} />
        </Card>
      )}
      <ReassignModal key={`r${modal}`} open={modal === 'reassign'} vol={v} onClose={() => setModal(null)} onDone={() => { setModal(null); reload(); reloadHist() }} />
      <AssignModal key={`a${modal}`} open={modal === 'assign'} vol={v} onClose={() => setModal(null)} onDone={() => { setModal(null); reload(); reloadHist() }} />
      <GroupsModal key={`g${modal}`} open={modal === 'groups'} vol={v} onClose={() => setModal(null)} onDone={() => { setModal(null); reload() }} />
      <HandoverModal key={`h${modal}`} open={modal === 'handover'} sourceVolunteer={v} onClose={() => setModal(null)} onDone={() => { setModal(null); reload(); reloadHist() }} />
    </div>
  )
}
