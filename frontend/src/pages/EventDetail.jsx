import { ArrowLeft, Download, Send, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Badge, Button, Card, Checkbox, DefinitionList, ErrorBox, Field, Input, Modal, PageHeader, Select, Spinner, StatusBadge, Table, Tabs, Textarea } from '../components/ui'
import api, { download, errorMessage } from '../lib/api'
import { fmtDateTime, humanize } from '../lib/format'
import { lookupLabel, useAction, useFetch, useLookups } from '../lib/hooks'
import { locale, localName, t } from '../lib/i18n'
import { useAuth } from '../lib/auth'

function Checklist({ ev, which, onSaved }) {
  const [items, setItems] = useState(ev[`${which}_checklist`])
  const [newItem, setNewItem] = useState('')
  const { busy, error, run } = useAction()
  useEffect(() => setItems(ev[`${which}_checklist`]), [ev, which])
  const save = () => run(async () => onSaved((await api.put(`/events/${ev.id}/checklists/${which}`, { items })).data)).catch(() => {})
  return (
    <Card title={which === 'pre' ? t('Pre-event checklist') : t('Post-event checklist')} actions={<Button size="sm" busy={busy} onClick={save} disabled={ev.status === 'cancelled'}>{t('Save')}</Button>}>
      <ErrorBox message={error} />
      <div className="space-y-2">
        {items.map((it, i) => (
          <div key={i} className="flex items-center gap-2">
            <Checkbox checked={it.done} onChange={(e) => setItems(items.map((x, j) => (j === i ? { ...x, done: e.target.checked } : x)))} label={it.item} />
            {it.done_at && <span className="text-xs text-gray-400">{fmtDateTime(it.done_at)}</span>}
          </div>
        ))}
        <div className="flex gap-2 pt-1">
          <Input placeholder={t('Add item')} value={newItem} onChange={(e) => setNewItem(e.target.value)} />
          <Button size="sm" variant="secondary" disabled={!newItem.trim()} onClick={() => { setItems([...items, { item: newItem.trim(), done: false }]); setNewItem('') }}>{t('Add')}</Button>
        </div>
      </div>
    </Card>
  )
}

function Attendance({ ev, onSaved }) {
  const { data } = useFetch('/girls', { village_id: ev.village_id, page_size: 500, sort: 'name' })
  const [present, setPresent] = useState(() => Object.fromEntries((ev.attendance || []).map((a) => [a.girl_id, a.present])))
  const [others, setOthers] = useState({ boys: 0, parents: 0, community_members: 0, officials: 0, others: 0, ...(ev.other_participants || {}) })
  const [groupFilter, setGroupFilter] = useState('')
  const { busy, error, run } = useAction()
  const started = new Date(ev.start_at) <= new Date()
  const girls = (data?.items || []).filter((g) => !groupFilter || g.group_id === groupFilter)
  const save = () => run(async () => {
    const entries = Object.entries(present).map(([girl_id, p]) => ({ girl_id, present: p }))
    onSaved((await api.put(`/events/${ev.id}/attendance`, { entries, other_participants: Object.fromEntries(Object.entries(others).map(([k, v]) => [k, Number(v) || 0])) })).data)
  }).catch(() => {})
  const markGroups = () => run(async () => onSaved((await api.put(`/events/${ev.id}/attendance`, { mark_groups_present: ev.group_ids })).data)).catch(() => {})
  if (!started) return <Card title={t('Attendance')}><p className="text-sm text-gray-500">{t('Attendance opens once the event has started.')}</p></Card>
  return (
    <Card title={t('Attendance · {n} girls present', { n: Object.values(present).filter(Boolean).length })} actions={<>
      {ev.group_ids?.length > 0 && <Button size="sm" variant="secondary" busy={busy} onClick={markGroups}>{t('Mark invited groups present')}</Button>}
      <Button size="sm" busy={busy} onClick={save} disabled={ev.status === 'cancelled'}>{t('Save attendance')}</Button>
    </>}>
      <ErrorBox message={error} />
      <div className="mb-3 grid gap-2 sm:grid-cols-5">
        {Object.keys(others).map((k) => (
          <Field key={k} label={humanize(k)}><Input type="number" min={0} value={others[k]} onChange={(e) => setOthers({ ...others, [k]: e.target.value })} /></Field>
        ))}
      </div>
      {ev.groups?.length > 0 && (
        <div className="mb-2 max-w-xs"><Select options={ev.groups.map((g) => ({ value: g.id, label: localName(g) }))} placeholder={t('All girls in village')} value={groupFilter} onChange={(e) => setGroupFilter(e.target.value)} /></div>
      )}
      {!data ? <Spinner /> : (
        <div className="max-h-96 overflow-y-auto">
          <Table columns={[
            { key: 'present', label: t('Present'), render: (g) => <input type="checkbox" className="h-4 w-4" checked={Boolean(present[g.id])} onChange={(e) => setPresent({ ...present, [g.id]: e.target.checked })} /> },
            { key: 'girl_code', label: t('Girl ID') },
            { key: 'name', label: t('Name'), render: (g) => localName(g) || '—' },
            { key: 'current_age', label: t('Age') },
          ]} rows={girls} empty={t('No girls registered in this village.')} />
        </div>
      )}
    </Card>
  )
}

function ReportForm({ ev, onSaved }) {
  const [f, setF] = useState(ev.report || {})
  const { busy, error, run } = useAction()
  const started = new Date(ev.start_at) <= new Date()
  const submit = () => run(async () => onSaved((await api.post(`/events/${ev.id}/report`, {
    activities_conducted: f.activities_conducted, outcomes: f.outcomes || null, observations: f.observations || null,
    issues: f.issues || null, follow_up_actions: f.follow_up_actions || null,
  })).data)).catch(() => {})
  if (!started) return <Card title={t('Post-event report')}><p className="text-sm text-gray-500">{t('The report can be submitted once the event has started.')}</p></Card>
  return (
    <Card title={t('Post-event report')} actions={ev.approval?.status && ev.approval.status !== 'not_required' && <StatusBadge value={ev.approval.status} />}>
      <ErrorBox message={error} />
      <div className="space-y-3">
        {[['activities_conducted', 'Activities conducted *'], ['outcomes', 'Outcomes'], ['observations', 'Observations'], ['issues', 'Issues'], ['follow_up_actions', 'Follow-up actions']].map(([k, l]) => (
          <Field key={k} label={t(l)}><Textarea value={f[k] || ''} onChange={(e) => setF({ ...f, [k]: e.target.value })} /></Field>
        ))}
        <div className="flex justify-end"><Button busy={busy} disabled={!f.activities_conducted || ev.status === 'cancelled'} onClick={submit}>{ev.report ? t('Update report') : t('Submit report & complete event')}</Button></div>
      </div>
    </Card>
  )
}

function Expenditure({ ev, onSaved }) {
  const [items, setItems] = useState(ev.expenditure?.items?.length ? ev.expenditure.items : [])
  const { busy, error, run } = useAction()
  const set = (i, k, v) => setItems(items.map((x, j) => (j === i ? { ...x, [k]: v } : x)))
  const total = items.reduce((s, x) => s + (Number(x.quantity) || 0) * (Number(x.unit_cost) || 0), 0)
  const save = () => run(async () => onSaved((await api.put(`/events/${ev.id}/expenditure`, {
    items: items.map((x) => ({ item: x.item, category: x.category || 'other', quantity: Number(x.quantity) || 0, unit_cost: Number(x.unit_cost) || 0, notes: x.notes || null })),
  })).data)).catch(() => {})
  return (
    <Card title={`${t('Expenditure')} · ₹${total.toLocaleString(locale())}${ev.planned_budget ? ` ${t('of ₹{n} planned', { n: ev.planned_budget.toLocaleString(locale()) })}` : ''}`}
      actions={<Button size="sm" busy={busy} onClick={save}>{t('Save')}</Button>}>
      <ErrorBox message={error} />
      <div className="space-y-2">
        {items.map((x, i) => (
          <div key={i} className="grid grid-cols-12 gap-2">
            <div className="col-span-4"><Input placeholder={t('Item')} value={x.item} onChange={(e) => set(i, 'item', e.target.value)} /></div>
            <div className="col-span-3"><Select options={['material', 'refreshments', 'travel', 'venue', 'honorarium', 'printing', 'medical', 'other']} value={x.category || 'other'} onChange={(e) => set(i, 'category', e.target.value)} /></div>
            <div className="col-span-2"><Input type="number" placeholder={t('Qty')} value={x.quantity} onChange={(e) => set(i, 'quantity', e.target.value)} /></div>
            <div className="col-span-2"><Input type="number" placeholder={t('Unit ₹')} value={x.unit_cost} onChange={(e) => set(i, 'unit_cost', e.target.value)} /></div>
            <button type="button" className="col-span-1 text-xs text-red-600" onClick={() => setItems(items.filter((_, j) => j !== i))}>{t('Remove')}</button>
          </div>
        ))}
        <Button size="sm" variant="secondary" onClick={() => setItems([...items, { item: '', category: 'other', quantity: 1, unit_cost: 0 }])}>{t('Add line')}</Button>
      </div>
    </Card>
  )
}

function Media({ ev, onChange }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [urls, setUrls] = useState({})
  useEffect(() => {
    let alive = true
    const created = []
    ;(async () => {
      for (const m of ev.media || []) {
        if (!m.content_type?.startsWith('image/')) continue
        try {
          const r = await api.get(`/media/${m.id}/file`, { responseType: 'blob' })
          const u = URL.createObjectURL(r.data)
          created.push(u)
          if (alive) setUrls((p) => ({ ...p, [m.id]: u }))
        } catch { /* ignore broken file */ }
      }
    })()
    return () => { alive = false; created.forEach(URL.revokeObjectURL) }
  }, [ev.media])
  const upload = async (file) => {
    setBusy(true)
    setError(null)
    const fd = new FormData()
    fd.append('file', file)
    const send = async (coords) => {
      if (coords) { fd.append('lat', coords.latitude); fd.append('lng', coords.longitude); fd.append('accuracy_m', coords.accuracy) }
      try {
        const r = await api.post(`/events/${ev.id}/media`, fd)
        if (r.data.duplicate) setError(t('This photo was already uploaded to this event.'))
        onChange()
      } catch (e) {
        setError(errorMessage(e))
      } finally {
        setBusy(false)
      }
    }
    if (navigator.geolocation) navigator.geolocation.getCurrentPosition((p) => send(p.coords), () => send(null), { timeout: 5000 })
    else send(null)
  }
  return (
    <Card title={`${t('Photos & media')} (${ev.media?.length || 0})`} actions={
      <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg bg-brand-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-brand-700">
        <Upload className="h-4 w-4" /> {busy ? t('Uploading…') : t('Upload')}
        <input type="file" accept="image/*,video/mp4,application/pdf" className="sr-only" disabled={busy} onChange={(e) => e.target.files[0] && upload(e.target.files[0])} />
      </label>
    }>
      <ErrorBox message={error} />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {(ev.media || []).map((m) => (
          <figure key={m.id} className="overflow-hidden rounded-lg border border-black/10">
            {urls[m.id] ? <img src={urls[m.id]} alt={m.caption || m.original_name} className="h-32 w-full object-cover" /> : <div className="flex h-32 items-center justify-center bg-gray-50 text-xs text-gray-500">{m.content_type}</div>}
            <figcaption className="px-2 py-1 text-[11px] text-gray-500">
              {fmtDateTime(m.uploaded_at)} {m.location ? `· ${t('GPS')} ✓` : <Badge tone="yellow">{t('No GPS')}</Badge>}
            </figcaption>
          </figure>
        ))}
      </div>
      {!ev.media?.length && <p className="text-sm text-gray-500">{t('No photos yet. Location is attached automatically when the browser allows it.')}</p>}
    </Card>
  )
}

export default function EventDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const isVolunteer = user?.role === 'volunteer'
  const types = useLookups('event_type')
  const { data: ev, error, reload } = useFetch(`/events/${id}`)
  const [tab, setTab] = useState('overview')
  const [cancel, setCancel] = useState(false)
  const [reason, setReason] = useState('')
  const [approval, setApproval] = useState(null)
  const { busy, error: actErr, run } = useAction()
  const [smsResult, setSmsResult] = useState(null)
  if (error) return <ErrorBox message={error} />
  if (!ev) return <Spinner />
  const onSaved = () => reload()
  const att = ev.attendance_summary
  const doCancel = () => run(async () => { await api.post(`/events/${id}/cancel`, { reason }); setCancel(false); reload() }).catch(() => {})
  const notify = () => run(async () => setSmsResult((await api.post(`/events/${id}/notify-participants`)).data)).catch(() => {})
  const decide = (decision) => run(async () => { await api.post(`/events/${id}/approval`, { decision, remarks: approval || null }); setApproval(null); reload() }).catch(() => {})

  return (
    <div className="space-y-4">
      <Link to="/events" className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline"><ArrowLeft className="h-4 w-4" /> {t('Events')}</Link>
      <PageHeader
        title={ev.title}
        subtitle={`${lookupLabel(types, ev.event_type)} · ${localName(ev.village)} · ${fmtDateTime(ev.start_at)}`}
        actions={<>
          {!isVolunteer && <>
            <Button variant="secondary" size="sm" icon={Download} onClick={() => download(`/events/${id}/export`, { format: 'pdf' })}>PDF</Button>
            <Button variant="secondary" size="sm" icon={Download} onClick={() => download(`/events/${id}/export`, { format: 'xlsx' })}>{t('Excel')}</Button>
            {ev.display_status === 'upcoming' || ev.display_status === 'today' ? <Button variant="secondary" size="sm" icon={Send} busy={busy} onClick={notify}>{t('SMS participants')}</Button> : null}
            {ev.status === 'scheduled' && <Button variant="danger" size="sm" onClick={() => setCancel(true)}>{t('Cancel event')}</Button>}
            {ev.report && ev.approval?.status === 'pending' && <Button size="sm" onClick={() => setApproval('')}>{t('Review report')}</Button>}
          </>}
        </>}
      />
      <ErrorBox message={actErr} />
      {smsResult && <div className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-900">SMS: {Object.entries(smsResult).filter(([, n]) => n).map(([k, n]) => `${n} ${humanize(k).toLowerCase()}`).join(' · ') || t('no recipients')}</div>}
      <div className="flex flex-wrap gap-2"><StatusBadge value={ev.display_status} />{ev.is_historical && <Badge>{t('Back-dated')}</Badge>}{ev.notify_participants && <Badge tone="blue">{t('SMS reminders on')}</Badge>}</div>
      <Tabs tabs={['overview', 'checklists', 'attendance', 'report', ...(!isVolunteer ? ['expenditure'] : []), 'media']} value={tab} onChange={setTab} />
      {tab === 'overview' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title={t('Event')}>
            <DefinitionList items={[
              ['Location', ev.location_name], ['Responsible volunteer', ev.responsible_volunteer?.name], ['Invited groups', ev.groups?.map((g) => g.name).join(', ')],
              ['Expected participants', ev.expected_participants], ['Girls present', att.girls_present], ['Other participants', att.other_participants],
              ...(!isVolunteer ? [['Planned budget', ev.planned_budget ? `₹${ev.planned_budget}` : '—'], ['Spent', `₹${ev.expenditure?.total || 0}`]] : []),
            ]} />
            {ev.objective && <p className="mt-3 text-sm text-gray-700"><b>{t('Objective:')}</b> {ev.objective}</p>}
            {ev.cancel_reason && <p className="mt-3 text-sm text-red-700"><b>{t('Cancelled:')}</b> {ev.cancel_reason}</p>}
          </Card>
          <Card title={t('Reschedule history')}>
            <Table rowKey={(r) => r.at} columns={[
              { key: 'from', label: t('From'), render: (r) => fmtDateTime(r.from) }, { key: 'to', label: t('To'), render: (r) => fmtDateTime(r.to) }, { key: 'reason', label: t('Reason') },
            ]} rows={ev.reschedule_history} empty={t('Never rescheduled.')} />
          </Card>
        </div>
      )}
      {tab === 'checklists' && <div className="grid gap-4 lg:grid-cols-2"><Checklist ev={ev} which="pre" onSaved={onSaved} /><Checklist ev={ev} which="post" onSaved={onSaved} /></div>}
      {tab === 'attendance' && <Attendance key={ev.updated_at} ev={ev} onSaved={onSaved} />}
      {tab === 'report' && <ReportForm ev={ev} onSaved={onSaved} />}
      {!isVolunteer && tab === 'expenditure' && <Expenditure ev={ev} onSaved={onSaved} />}
      {tab === 'media' && <Media ev={ev} onChange={reload} />}
      {!isVolunteer && <Modal open={cancel} title={t('Cancel event')} onClose={() => setCancel(false)}
        footer={<><Button variant="secondary" onClick={() => setCancel(false)}>{t('Keep')}</Button><Button variant="danger" busy={busy} disabled={reason.length < 3} onClick={doCancel}>{t('Cancel event')}</Button></>}>
        <Field label={t('Reason *')}><Input value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
      </Modal>}
      {!isVolunteer && <Modal open={approval !== null} title={t('Review event report')} onClose={() => setApproval(null)}
        footer={<><Button variant="danger" busy={busy} onClick={() => decide('rejected')}>{t('Reject')}</Button><Button busy={busy} onClick={() => decide('approved')}>{t('Approve')}</Button></>}>
        <Field label={t('Remarks')}><Textarea value={approval || ''} onChange={(e) => setApproval(e.target.value)} /></Field>
      </Modal>}
    </div>
  )
}
