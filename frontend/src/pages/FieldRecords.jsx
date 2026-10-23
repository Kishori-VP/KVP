import { Check, Eye, Plus, Trash2, X } from 'lucide-react'
import { useState } from 'react'
import { VillageSelect, VolunteerSelect } from '../components/pickers'
import { Badge, Button, Card, Checkbox, ErrorBox, Field, Input, Modal, PageHeader, Pagination, Select, Spinner, StatusBadge, Table, Tabs, Textarea } from '../components/ui'
import api from '../lib/api'
import { fmtDate, humanize, todayISO } from '../lib/format'
import { useAction, useFetch, useLookups, useVillages, useVolunteers } from '../lib/hooks'
import { localName, t } from '../lib/i18n'

const RISKS = ['child_marriage_risk', 'school_dropout_risk', 'health_concern', 'anaemia_concern', 'gender_discrimination']

function GirlPicker({ villageId, value, onChange }) {
  const { data } = useFetch(villageId ? '/girls' : null, { village_id: villageId, page_size: 500, sort: 'name' })
  const [q, setQ] = useState('')
  if (!villageId) return <p className="text-xs text-gray-500">{t('Pick a volunteer and village first.')}</p>
  const girls = (data?.items || []).filter((g) => !q || `${g.girl_code} ${g.name || ''} ${g.name_en || ''}`.toLowerCase().includes(q.toLowerCase()))
  return (
    <div>
      <Input placeholder={t('Filter by name or Girl ID')} value={q} onChange={(e) => setQ(e.target.value)} />
      <div className="mt-2 max-h-40 space-y-1 overflow-y-auto rounded-lg border border-gray-200 p-2">
        {girls.slice(0, 200).map((g) => (
          <Checkbox key={g.id} label={`${g.girl_code} · ${localName(g) || t('no name')}`} checked={value.includes(g.id)}
            onChange={(e) => onChange(e.target.checked ? [...value, g.id] : value.filter((x) => x !== g.id))} />
        ))}
      </div>
      <p className="mt-1 text-xs text-gray-500">{t('{n} selected', { n: value.length })}</p>
    </div>
  )
}

function HomeVisitModal({ open, onClose, onSaved }) {
  const vols = useVolunteers()
  const villages = useVillages()
  const [f, setF] = useState({ visit_date: todayISO(), status: 'completed', purpose: 'routine', girl_ids: [], risks: {}, volunteer_id: '', village_id: '' })
  const { busy, error, run } = useAction()
  const vol = vols.find((v) => v.id === f.volunteer_id)
  const assignedVillages = (vol?.village_ids?.length ? vol.village_ids : (vol?.village_id ? [vol.village_id] : []))
  const volVillageId = f.village_id || (assignedVillages.length > 0 ? assignedVillages[0] : (vol?.village_id || ''))

  const submit = () => run(async () => {
    await api.post('/home-visits', {
      volunteer_id: f.volunteer_id,
      village_id: volVillageId || null,
      visit_date: f.visit_date,
      status: f.status,
      purpose: f.purpose,
      girl_ids: f.girl_ids,
      observations: f.observations || null,
      risk_indicators: { ...Object.fromEntries(RISKS.map((r) => [r, Boolean(f.risks[r])])) },
    })
    onSaved()
  }).catch(() => {})

  return (
    <Modal open={open} title={t('Record or plan a home visit')} onClose={onClose} wide
      footer={<><Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button><Button busy={busy} disabled={!f.volunteer_id} onClick={submit}>{t('Save')}</Button></>}>
      <ErrorBox message={error} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t('Volunteer *')}><VolunteerSelect value={f.volunteer_id} onChange={(v) => setF({ ...f, volunteer_id: v, village_id: '', girl_ids: [] })} placeholder={t('Select…')} /></Field>
        {assignedVillages.length > 1 && (
          <Field label={t('Village *')}>
            <select className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm" value={volVillageId} onChange={(e) => setF({ ...f, village_id: e.target.value, girl_ids: [] })}>
              {assignedVillages.map((vid) => {
                const vObj = villages.find((v) => (v.id || v._id) === vid)
                return <option key={vid} value={vid}>{vObj?.name || vid}</option>
              })}
            </select>
          </Field>
        )}
        <Field label={t('Status')}><Select options={['completed', 'planned', 'missed']} value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })} /></Field>
        <Field label={t('Date')} hint={t('Planned visits must be today or later; completed visits cannot be in the future')}><Input type="date" value={f.visit_date} onChange={(e) => setF({ ...f, visit_date: e.target.value })} /></Field>
        <Field label={t('Purpose')}><Select options={['routine', 'follow_up', 'case_follow_up', 'enrolment', 'other']} value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })} /></Field>
      </div>
      <Field label={t('Girls visited')} group><GirlPicker villageId={volVillageId} value={f.girl_ids} onChange={(v) => setF({ ...f, girl_ids: v })} /></Field>
      <Field label={t('Risk indicators')} group>
        <div className="flex flex-wrap gap-3">{RISKS.map((r) => <Checkbox key={r} label={humanize(r)} checked={Boolean(f.risks[r])} onChange={(e) => setF({ ...f, risks: { ...f.risks, [r]: e.target.checked } })} />)}</div>
      </Field>
      <Field label={t('Observations')}><Textarea value={f.observations || ''} onChange={(e) => setF({ ...f, observations: e.target.value })} /></Field>
    </Modal>
  )
}

function ActivityReportModal({ open, onClose, onSaved }) {
  const vols = useVolunteers()
  const acts = useLookups('activity_type')
  const villages = useVillages()
  const [f, setF] = useState({ report_date: todayISO(), activities: [], group_ids: [], girls_present: 0, home_visits_count: 0, home_visit_girl_ids: [], volunteer_id: '', village_id: '', topics_discussed: '', other_meetings: '' })
  const { busy, error, run } = useAction()
  const vol = vols.find((v) => v.id === f.volunteer_id)
  const assignedVillages = (vol?.village_ids?.length ? vol.village_ids : (vol?.village_id ? [vol.village_id] : []))
  const volVillageId = f.village_id || (assignedVillages.length > 0 ? assignedVillages[0] : (vol?.village_id || ''))
  const { data: groups } = useFetch(volVillageId ? '/groups' : null, { village_id: volVillageId, page_size: 200 })

  const submit = () => run(async () => {
    await api.post('/activity-reports', {
      volunteer_id: f.volunteer_id,
      village_id: volVillageId || null,
      report_date: f.report_date,
      activities: f.activities,
      group_ids: f.group_ids,
      girls_present: Number(f.girls_present),
      home_visits_count: Number(f.home_visits_count),
      home_visit_girl_ids: f.home_visit_girl_ids,
      topics_discussed: f.topics_discussed || null,
      other_meetings: f.other_meetings || null,
    })
    onSaved()
  }).catch(() => {})

  const toggle = (k, id) => setF({ ...f, [k]: f[k].includes(id) ? f[k].filter((x) => x !== id) : [...f[k], id] })

  return (
    <Modal open={open} title={t('Daily activity report (दैनिक अहवाल)')} onClose={onClose} wide
      footer={<><Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button><Button busy={busy} disabled={!f.volunteer_id || !f.activities.length} onClick={submit}>{t('Save report')}</Button></>}>
      <ErrorBox message={error} />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t('Tai *')}><VolunteerSelect value={f.volunteer_id} onChange={(v) => setF({ ...f, volunteer_id: v, village_id: '', group_ids: [], home_visit_girl_ids: [] })} placeholder={t('Select…')} /></Field>
        {assignedVillages.length > 1 && (
          <Field label={t('Village *')}>
            <select className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm" value={volVillageId} onChange={(e) => setF({ ...f, village_id: e.target.value, group_ids: [], home_visit_girl_ids: [] })}>
              {assignedVillages.map((vid) => {
                const vObj = villages.find((v) => (v.id || v._id) === vid)
                return <option key={vid} value={vid}>{vObj?.name || vid}</option>
              })}
            </select>
          </Field>
        )}
        <Field label={t('Date')}><Input type="date" max={todayISO()} value={f.report_date} onChange={(e) => setF({ ...f, report_date: e.target.value })} /></Field>
      </div>
      <Field label={t('Activities done (आज काय ऍक्टिव्हिटी पूर्ण केली?)')} group>
        <div className="flex flex-wrap gap-3">{acts.map((a) => <Checkbox key={a.code} label={a.label_mr || a.label} checked={f.activities.includes(a.code)} onChange={() => toggle('activities', a.code)} />)}</div>
      </Field>
      <Field label={t('Groups met')} group>
        <div className="flex flex-wrap gap-3">{(groups?.items || []).map((g) => <Checkbox key={g.id} label={localName(g)} checked={f.group_ids.includes(g.id)} onChange={() => toggle('group_ids', g.id)} />)}</div>
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t('Girls present (किती मुली हजर होत्या?)')}><Input type="number" min={0} value={f.girls_present} onChange={(e) => setF({ ...f, girls_present: e.target.value })} /></Field>
        <Field label={t('Home visits (आज किती गृहभेटी झाल्या?)')}><Input type="number" min={0} value={f.home_visits_count} onChange={(e) => setF({ ...f, home_visits_count: e.target.value })} /></Field>
      </div>
      <Field label={t('Girls visited at home')} group><GirlPicker villageId={volVillageId} value={f.home_visit_girl_ids} onChange={(v) => setF({ ...f, home_visit_girl_ids: v })} /></Field>
      <Field label={t('Topics discussed (कुठल्या विषयावर चर्चा झाली?)')}><Textarea value={f.topics_discussed || ''} onChange={(e) => setF({ ...f, topics_discussed: e.target.value })} /></Field>
      <Field label={t('Others met / information (इतर कोणाला भेटला का?)')}><Textarea value={f.other_meetings || ''} onChange={(e) => setF({ ...f, other_meetings: e.target.value })} /></Field>
    </Modal>
  )
}

function ReportDetailModal({ report, onClose, onUpdated }) {
  const vols = useVolunteers()
  const villages = useVillages()
  const acts = useLookups('activity_type')
  const { busy, run } = useAction()
  if (!report) return null

  const vol = vols.find((v) => v.id === report.volunteer_id)
  const vil = villages.find((v) => (v.id || v._id) === report.village_id)
  const actMap = Object.fromEntries(acts.map((a) => [a.code, a.label_mr || a.label]))

  const decide = (decision) => run(async () => {
    await api.post(`/activity-reports/${report.id}/approval`, { decision })
    onUpdated()
  }).catch(() => {})

  const deleteReport = () => {
    if (!window.confirm(t('Are you sure you want to delete this daily report?'))) return
    run(async () => {
      await api.delete(`/activity-reports/${report.id}`)
      onUpdated()
    }).catch(() => {})
  }

  return (
    <Modal open title={t('Daily Activity Report Details')} onClose={onClose} wide
      footer={
        <div className="flex w-full items-center justify-between">
          <Button variant="danger" size="sm" icon={Trash2} busy={busy} onClick={deleteReport}>
            {t('Delete Report')}
          </Button>
          <div className="flex gap-2">
            {report.approval?.status === 'pending' && (
              <>
                <Button size="sm" variant="secondary" icon={Check} busy={busy} onClick={() => decide('approved')}>{t('Approve')}</Button>
                <Button size="sm" variant="ghost" icon={X} onClick={() => decide('rejected')}>{t('Reject')}</Button>
              </>
            )}
            <Button variant="secondary" onClick={onClose}>{t('Close')}</Button>
          </div>
        </div>
      }>
      <div className="space-y-4 text-sm">
        <div className="grid gap-3 sm:grid-cols-3 rounded-lg bg-gray-50 p-3">
          <div><span className="text-xs text-gray-500">{t('Date')}</span><div className="font-medium">{fmtDate(report.report_date)}</div></div>
          <div><span className="text-xs text-gray-500">{t('Tai')}</span><div className="font-medium">{vol?.name || '—'}</div></div>
          <div><span className="text-xs text-gray-500">{t('Village')}</span><div className="font-medium">{vil?.name || vol?.village_name || '—'}</div></div>
          <div><span className="text-xs text-gray-500">{t('Approval Status')}</span><div><StatusBadge value={report.approval?.status} /></div></div>
          <div><span className="text-xs text-gray-500">{t('Girls Present')}</span><div className="font-medium tabular">{report.girls_present ?? 0}</div></div>
          <div><span className="text-xs text-gray-500">{t('Home Visits')}</span><div className="font-medium tabular">{report.home_visits_count ?? 0}</div></div>
        </div>

        <div>
          <span className="text-xs font-semibold uppercase text-gray-500">{t('Activities Done')}</span>
          <div className="mt-1 flex flex-wrap gap-2">
            {(report.activities || []).map((code) => (
              <Badge key={code} variant="brand">{actMap[code] || humanize(code)}</Badge>
            ))}
            {!report.activities?.length && <span className="text-gray-400">—</span>}
          </div>
        </div>

        {report.topics_discussed && (
          <div>
            <span className="text-xs font-semibold uppercase text-gray-500">{t('Topics Discussed')}</span>
            <p className="mt-1 whitespace-pre-wrap rounded-lg bg-gray-50 p-2 text-gray-800">{report.topics_discussed}</p>
          </div>
        )}

        {report.other_meetings && (
          <div>
            <span className="text-xs font-semibold uppercase text-gray-500">{t('Other Meetings & Info')}</span>
            <p className="mt-1 whitespace-pre-wrap rounded-lg bg-gray-50 p-2 text-gray-800">{report.other_meetings}</p>
          </div>
        )}
      </div>
    </Modal>
  )
}

function ApprovalButtons({ path, onDone }) {
  const { busy, run } = useAction()
  const decide = (decision) => run(async () => { await api.post(path, { decision }); onDone() }).catch(() => {})
  return (
    <span className="inline-flex gap-1" onClick={(e) => e.stopPropagation()}>
      <Button size="sm" variant="secondary" icon={Check} busy={busy} onClick={(e) => { e.stopPropagation(); decide('approved') }}>{t('Approve')}</Button>
      <Button size="sm" variant="ghost" icon={X} onClick={(e) => { e.stopPropagation(); decide('rejected') }}>{t('Reject')}</Button>
    </span>
  )
}

export default function FieldRecords() {
  const [tab, setTab] = useState('visits')
  const [f, setF] = useState({ volunteer_id: '', village_id: '', status: '', approval: '', start_date: '', end_date: '' })
  const [page, setPage] = useState(1)
  const [modal, setModal] = useState(null)
  const [selectedReport, setSelectedReport] = useState(null)
  const vols = useVolunteers()
  const volName = (id) => vols.find((v) => v.id === id)?.name || '—'
  const url = tab === 'visits' ? '/home-visits' : '/activity-reports'

  const { data, error, loading, reload } = useFetch(url, {
    volunteer_id: f.volunteer_id || undefined,
    village_id: f.village_id || undefined,
    status: tab === 'visits' ? (f.status || undefined) : undefined,
    approval: f.approval || undefined,
    start_date: f.start_date || undefined,
    end_date: f.end_date || undefined,
    page,
    page_size: 25,
  })

  const set = (k, v) => { setF({ ...f, [k]: v }); setPage(1) }

  return (
    <div>
      <PageHeader title={t('Field records')} subtitle={t('Home visits and daily activity reports (the digital version of the Google Form)')}
        actions={<>
          <Button variant="secondary" icon={Plus} onClick={() => setModal('visit')}>{t('Home visit')}</Button>
          <Button icon={Plus} onClick={() => setModal('report')}>{t('Daily report')}</Button>
        </>} />
      <Tabs tabs={[{ value: 'visits', label: t('Home visits') }, { value: 'reports', label: t('Daily activity reports') }]} value={tab} onChange={(v) => { setTab(v); setPage(1) }} />
      <Card padded={false}>
        <div className="grid gap-2 border-b border-gray-100 p-3 sm:grid-cols-3 lg:grid-cols-6">
          <VolunteerSelect value={f.volunteer_id} onChange={(v) => set('volunteer_id', v)} />
          <VillageSelect value={f.village_id} onChange={(v) => set('village_id', v)} />
          {tab === 'visits' && <Select options={['completed', 'planned', 'missed']} placeholder={t('Any status')} value={f.status} onChange={(e) => set('status', e.target.value)} />}
          <Select options={['pending', 'approved', 'rejected']} placeholder={t('Any approval')} value={f.approval} onChange={(e) => set('approval', e.target.value)} />
          <Input type="date" value={f.start_date} onChange={(e) => set('start_date', e.target.value)} />
          <Input type="date" value={f.end_date} onChange={(e) => set('end_date', e.target.value)} />
        </div>
        <ErrorBox message={error} />
        {loading && !data ? <Spinner /> : (
          <>
            {tab === 'visits' ? (
              <Table columns={[
                { key: 'visit_date', label: t('Date'), render: (r) => fmtDate(r.visit_date) },
                { key: 'volunteer', label: t('Volunteer'), render: (r) => volName(r.volunteer_id) },
                { key: 'status', label: t('Status'), render: (r) => <StatusBadge value={r.status} /> },
                { key: 'purpose', label: t('Purpose'), render: (r) => humanize(r.purpose) },
                { key: 'girls', label: t('Girls'), render: (r) => r.girl_ids?.length || 0 },
                { key: 'risks', label: t('Risks'), render: (r) => Object.entries(r.risk_indicators || {}).filter(([, v]) => v === true).map(([k]) => humanize(k)).join(', ') || '—' },
                { key: 'approval', label: t('Approval'), render: (r) => (r.approval?.status === 'pending' ? <ApprovalButtons path={`/home-visits/${r.id}/approval`} onDone={reload} /> : <StatusBadge value={r.approval?.status} />) },
              ]} rows={data?.items} empty={t('No home visits recorded.')} />
            ) : (
              <Table onRowClick={(r) => setSelectedReport(r)} columns={[
                { key: 'report_date', label: t('Date'), render: (r) => fmtDate(r.report_date) },
                { key: 'volunteer', label: t('Volunteer'), render: (r) => volName(r.volunteer_id) },
                { key: 'activities', label: t('Activities'), render: (r) => (r.activities || []).map(humanize).join(', ') || '—' },
                { key: 'girls_present', label: t('Girls present'), className: 'tabular text-right', render: (r) => r.girls_present ?? 0 },
                { key: 'home_visits_count', label: t('Home visits'), className: 'tabular text-right', render: (r) => r.home_visits_count ?? 0 },
                { key: 'topics_discussed', label: t('Topics'), render: (r) => <span className="line-clamp-2">{r.topics_discussed || '—'}</span> },
                { key: 'approval', label: t('Approval'), render: (r) => (r.approval?.status === 'pending' ? <ApprovalButtons path={`/activity-reports/${r.id}/approval`} onDone={reload} /> : <StatusBadge value={r.approval?.status} />) },
                { key: 'view', label: '', render: (r) => <Button size="sm" variant="ghost" icon={Eye} onClick={() => setSelectedReport(r)}>{t('View')}</Button> },
              ]} rows={data?.items} empty={t('No daily reports yet.')} />
            )}
            <Pagination page={page} pageSize={25} total={data?.total} onPage={setPage} />
          </>
        )}
      </Card>
      <HomeVisitModal key={`v${modal}`} open={modal === 'visit'} onClose={() => setModal(null)} onSaved={() => { setModal(null); setTab('visits'); reload() }} />
      <ActivityReportModal key={`r${modal}`} open={modal === 'report'} onClose={() => setModal(null)} onSaved={() => { setModal(null); setTab('reports'); reload() }} />
      {selectedReport && <ReportDetailModal report={selectedReport} onClose={() => setSelectedReport(null)} onUpdated={() => { setSelectedReport(null); reload() }} />}
    </div>
  )
}
