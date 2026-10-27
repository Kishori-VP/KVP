import { Plus } from 'lucide-react'
import { useState, useEffect } from 'react'
import { LookupSelect, VolunteerSelect } from '../components/pickers'
import { Button, Card, Checkbox, ErrorBox, Field, Input, Modal, PageHeader, Pagination, ProgressBar, Select, Spinner, StatusBadge, Table } from '../components/ui'
import api from '../lib/api'
import { fmtDate, fmtDateTime, humanize, todayISO } from '../lib/format'
import { useAction, useFetch, useVolunteers } from '../lib/hooks'
import { t } from '../lib/i18n'
import { useAuth } from '../lib/auth'

function CreateModal({ open, onClose, onSaved }) {
  const vols = useVolunteers()
  const [f, setF] = useState({ volunteer_ids: [], all_active_volunteers: true, target_type: 'home_visits', period_type: 'weekly', reference_date: todayISO(), periods: 1, target_value: 20 })
  const [result, setResult] = useState(null)
  const { busy, error, run } = useAction()
  const toggle = (id) => setF({ ...f, volunteer_ids: f.volunteer_ids.includes(id) ? f.volunteer_ids.filter((x) => x !== id) : [...f.volunteer_ids, id] })
  const submit = () => run(async () => {
    const custom = f.period_type === 'custom'
    const r = await api.post('/targets', {
      volunteer_ids: f.all_active_volunteers ? [] : f.volunteer_ids, all_active_volunteers: f.all_active_volunteers,
      target_type: f.target_type, period_type: f.period_type, target_value: Number(f.target_value), title: f.title || null, notes: f.notes || null,
      ...(custom ? { period_start: f.period_start, period_end: f.period_end } : { reference_date: f.reference_date, periods: Number(f.periods) }),
    })
    setResult(r.data)
    onSaved()
    setTimeout(() => onClose(), 800)
  }).catch(() => {})
  return (
    <Modal open={open} title={t('Assign targets')} onClose={onClose} wide
      footer={<><Button variant="secondary" onClick={onClose}>{t('Close')}</Button><Button busy={busy} disabled={!f.target_type || (!f.all_active_volunteers && !f.volunteer_ids.length)} onClick={submit}>{t('Assign / Update')}</Button></>}>
      <ErrorBox message={error} />
      {result && <div className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-900">{t('Successfully assigned/updated {n} target(s).', { n: result.created?.length || 0 })}</div>}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t('Target type *')}><LookupSelect type="target_type" value={f.target_type} onChange={(v) => setF({ ...f, target_type: v })} /></Field>
        <Field label={t('Target value *')}><Input type="number" min={1} value={f.target_value} onChange={(e) => setF({ ...f, target_value: e.target.value })} /></Field>
        <Field label={t('Period')}><Select options={['daily', 'weekly', 'monthly', 'quarterly', 'custom']} value={f.period_type} onChange={(e) => setF({ ...f, period_type: e.target.value })} /></Field>
        {f.period_type === 'custom' ? (
          <div className="grid grid-cols-2 gap-2">
            <Field label={t('From')}><Input type="date" value={f.period_start || ''} onChange={(e) => setF({ ...f, period_start: e.target.value })} /></Field>
            <Field label={t('To')}><Input type="date" value={f.period_end || ''} onChange={(e) => setF({ ...f, period_end: e.target.value })} /></Field>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            <Field label={t('First period contains')}><Input type="date" value={f.reference_date} onChange={(e) => setF({ ...f, reference_date: e.target.value })} /></Field>
            <Field label={t('Repeat for periods')}><Input type="number" min={1} max={24} value={f.periods} onChange={(e) => setF({ ...f, periods: e.target.value })} /></Field>
          </div>
        )}
        <Field label={t('Title (optional)')}><Input value={f.title || ''} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <Field label={t('Notes')}><Input value={f.notes || ''} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
      </div>
      <Field label={t('Volunteers')} group>
        <Checkbox label={t('All active Volunteers')} checked={f.all_active_volunteers} onChange={(e) => setF({ ...f, all_active_volunteers: e.target.checked })} />
        {!f.all_active_volunteers && (
          <div className="mt-2 flex flex-wrap gap-3">{(Array.isArray(vols) ? vols : []).map((v) => <Checkbox key={v.id} label={`${v.name} (${v.village_name || '—'})`} checked={f.volunteer_ids.includes(v.id)} onChange={() => toggle(v.id)} />)}</div>
        )}
      </Field>
      <p className="text-xs text-gray-500">{t('Targets apply to the Volunteer’s assigned villages.')}</p>
    </Modal>
  )
}

function DetailModal({ target, onClose, onChanged }) {
  const { user } = useAuth()
  const isSuperAdmin = user?.role === 'super_admin' || user?.role === 'stakeholder'
  const [rev, setRev] = useState({ target_value: target.target_value, period_end: (target.period_end || '').slice(0, 10), reason: '' })
  const [cancelReason, setCancelReason] = useState('')
  const { busy, error, run } = useAction()
  const revise = () => run(async () => {
    await api.patch(`/targets/${target.id}`, { target_value: Number(rev.target_value), period_end: rev.period_end, reason: rev.reason })
    onChanged()
  }).catch(() => {})
  const cancel = () => run(async () => { await api.post(`/targets/${target.id}/cancel`, { reason: cancelReason }); onChanged() }).catch(() => {})
  const p = target.progress || {}
  return (
    <Modal open title={target.title} onClose={onClose} wide>
      <ErrorBox message={error} />
      <div className="text-sm text-gray-700">{target.volunteer_name} · {fmtDate(target.period_start)} – {fmtDate(target.period_end)} · {humanize(target.period_type)}</div>
      <ProgressBar pct={p.progress_pct} status={p.status} />
      <div className="text-sm text-gray-700"><StatusBadge value={p.status} /> {t('{a} of {b} · expected by now {c} · {d} day(s) left', { a: p.achieved, b: target.target_value, c: p.expected_by_now, d: p.days_left })}</div>
      {target.status === 'active' && (
        <div className="grid gap-3 rounded-lg bg-gray-50 p-3 sm:grid-cols-4">
          <Field label={t('New value')}><Input type="number" min={1} value={rev.target_value} onChange={(e) => setRev({ ...rev, target_value: e.target.value })} /></Field>
          <Field label={t('Period end')}><Input type="date" value={rev.period_end} onChange={(e) => setRev({ ...rev, period_end: e.target.value })} /></Field>
          <Field label={t('Reason *')} className="sm:col-span-2"><Input value={rev.reason} onChange={(e) => setRev({ ...rev, reason: e.target.value })} /></Field>
          <div className="sm:col-span-4 flex justify-end"><Button size="sm" busy={busy} disabled={rev.reason.length < 3} onClick={revise}>{t('Revise target')}</Button></div>
        </div>
      )}
      <div>
        <div className="mb-1 text-xs font-semibold uppercase text-gray-500">{t('Revision history')}</div>
        <Table rowKey={(r) => r.at} columns={[
          { key: 'at', label: t('When'), render: (r) => fmtDateTime(r.at) }, { key: 'by_name', label: t('By') }, { key: 'reason', label: t('Reason') },
          { key: 'changes', label: t('Changes'), render: (r) => Object.entries(r.changes || {}).map(([k, c]) => `${humanize(k)}: ${c.from} → ${c.to}`).join('; ') },
        ]} rows={target.revisions} empty={t('Never revised.')} />
      </div>
      {isSuperAdmin && target.status === 'active' && (
        <div className="flex items-end gap-2 border-t border-gray-100 pt-3">
          <Field label={t('Cancel target — reason')} className="flex-1"><Input value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} /></Field>
          <Button variant="danger" size="sm" busy={busy} disabled={cancelReason.length < 3} onClick={cancel}>{t('Cancel target')}</Button>
        </div>
      )}
    </Modal>
  )
}

function ModalReadOnlyTarget({ target, onClose }) {
  return <Modal open title={target.title} onClose={onClose}>
    <div className="mb-2 text-sm text-gray-600">{fmtDate(target.period_start)} – {fmtDate(target.period_end)} · {humanize(target.period_type)}</div>
    <ProgressBar pct={target.progress?.progress_pct} />
    <div className="mt-2 text-sm">{target.progress?.achieved || 0} / {target.target_value} · <StatusBadge value={target.progress?.status} /></div>
    {target.notes && <p className="mt-3 text-sm text-gray-600">{target.notes}</p>}
    <p className="mt-3 text-xs text-gray-500">{t('Targets can only be created or revised by an Admin or Stakeholder.')}</p>
  </Modal>
}


function DefaultTargetsCard({ onApplied }) {
  const [defaults, setDefaults] = useState({ weekly_visits: 20, monthly_visits: 400 })
  const [saving, setSaving] = useState(false)
  const [applying, setApplying] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    api.get('/targets/defaults')
      .then((r) => {
        if (r?.data) setDefaults(r.data)
      })
      .catch(() => {})
  }, [])

  const saveDefaults = async () => {
    setSaving(true)
    setErr('')
    setMsg('')
    try {
      const res = await api.put('/targets/defaults', defaults)
      if (res?.data) setDefaults(res.data)
      setMsg(t('Default targets updated successfully.'))
    } catch (e) {
      setErr(t('Failed to save default targets.'))
    } finally {
      setSaving(false)
    }
  }

  const applyToAll = async () => {
    if (!window.confirm(t('Apply default weekly ({w}) and monthly ({m}) visit targets to all active Volunteers?', { w: defaults.weekly_visits, m: defaults.monthly_visits }))) return
    setApplying(true)
    setErr('')
    setMsg('')
    try {
      const res = await api.post('/targets/apply-defaults', {
        all_active: true,
        weekly_visits: Number(defaults.weekly_visits),
        monthly_visits: Number(defaults.monthly_visits),
      })
      setMsg(t('Applied targets: {c} updated for all active Volunteers.', { c: res?.data?.created_count ?? 0 }))
      if (onApplied) onApplied()
    } catch (e) {
      setErr(t('Failed to apply default targets.'))
    } finally {
      setApplying(false)
    }
  }

  return (
    <Card title={t('Default Volunteer Targets (Admin Configurable)')} className="mb-4 border-brand-200 bg-brand-50/30">
      {err && <p className="mb-2 text-xs text-red-600">{err}</p>}
      {msg && <p className="mb-2 text-xs font-semibold text-emerald-700">{msg}</p>}
      <div className="grid gap-3 sm:grid-cols-4 items-end">
        <div>
          <label className="block text-xs font-semibold text-gray-700 mb-1">{t('Weekly Visits Target (per Volunteer)')}</label>
          <Input
            type="number"
            min={1}
            max={500}
            value={defaults.weekly_visits}
            onChange={(e) => setDefaults({ ...defaults, weekly_visits: Number(e.target.value) })}
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-gray-700 mb-1">{t('Monthly Visits Target (per Volunteer)')}</label>
          <Input
            type="number"
            min={1}
            max={2000}
            value={defaults.monthly_visits}
            onChange={(e) => setDefaults({ ...defaults, monthly_visits: Number(e.target.value) })}
          />
        </div>
        <div className="flex gap-2 sm:col-span-2">
          <Button size="sm" variant="secondary" busy={saving} onClick={saveDefaults}>
            {t('Save Defaults')}
          </Button>
          <Button size="sm" busy={applying} onClick={applyToAll} className="bg-emerald-700 hover:bg-emerald-800 text-white">
            {t('Apply Defaults to All Volunteers')}
          </Button>
        </div>
      </div>
    </Card>
  )
}

export default function Targets() {
  const { user } = useAuth()
  const isVolunteer = user?.role === 'volunteer'
  const isReadOnly = user?.role === 'admin_2'
  const canAssign = !isVolunteer && !isReadOnly
  const [f, setF] = useState({ when: 'current', volunteer_id: '', target_type: '', status: '' })
  const [page, setPage] = useState(1)
  const [creating, setCreating] = useState(false)
  const [selected, setSelected] = useState(null)
  const { data, error, loading, reload } = useFetch('/targets', { ...f, page, page_size: 25 })
  const set = (k, v) => { setF({ ...f, [k]: v }); setPage(1) }
  return (
    <div>
      <PageHeader title={t(isVolunteer ? 'My targets' : 'Targets')} subtitle={t('Live progress against assigned jobs and targets')} actions={canAssign && <Button icon={Plus} onClick={() => setCreating(true)}>{t('Assign targets')}</Button>} />
      {canAssign && <DefaultTargetsCard onApplied={reload} />}
      <Card padded={false}>
        <div className="grid gap-2 border-b border-gray-100 p-3 sm:grid-cols-4">
          <Select options={['current', 'upcoming', 'past', 'all']} value={f.when} onChange={(e) => set('when', e.target.value)} />
          {!isVolunteer && <VolunteerSelect value={f.volunteer_id} onChange={(v) => set('volunteer_id', v)} />}
          <LookupSelect type="target_type" value={f.target_type} onChange={(v) => set('target_type', v)} placeholder={t('Any type')} />
          <Select options={['on_track', 'at_risk', 'achieved', 'missed', 'upcoming', 'cancelled']} placeholder={t('Any status')} value={f.status} onChange={(e) => set('status', e.target.value)} />
        </div>
        {data?.by_status && <div className="flex flex-wrap gap-3 px-3 pt-3 text-xs">{Object.entries(data.by_status).map(([k, n]) => <span key={k}><StatusBadge value={k} /> {n}</span>)}</div>}
        <ErrorBox message={error} />
        {loading && !data ? <Spinner /> : (
          <>
            <Table onRowClick={setSelected} columns={[
              ...(!isVolunteer ? [{ key: 'volunteer_name', label: t('Volunteer'), className: 'font-medium' }] : []),
              { key: 'title', label: t('Target') },
              { key: 'period', label: t('Period'), render: (tg) => `${fmtDate(tg.period_start)} – ${fmtDate(tg.period_end)}` },
              { key: 'value', label: t('Done / target'), render: (tg) => `${tg.progress?.achieved ?? 0} / ${tg.target_value}` },
              { key: 'progress', label: t('Progress'), render: (tg) => <ProgressBar pct={tg.progress?.progress_pct ?? 0} status={tg.progress?.status} /> },
              { key: 'status', label: t('Status'), render: (tg) => <StatusBadge value={tg.status === 'cancelled' ? 'cancelled' : (tg.progress?.status || 'active')} /> },
              { key: 'rev', label: t('Revisions'), render: (tg) => tg.revisions?.length || '—' },
            ]} rows={data?.items || []} empty={t('No targets in this view.')} />
            <Pagination page={page} pageSize={25} total={data?.total || 0} onPage={setPage} />
          </>
        )}
      </Card>
      {canAssign && creating && <CreateModal key={String(creating)} open={creating} onClose={() => setCreating(false)} onSaved={reload} />}
      {selected && ((isVolunteer || isReadOnly) ? <ModalReadOnlyTarget target={selected} onClose={() => setSelected(null)} /> : <DetailModal target={selected} onClose={() => setSelected(null)} onChanged={() => { setSelected(null); reload() }} />)}
    </div>
  )
}
