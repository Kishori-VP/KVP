import { ArrowLeft, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { VolunteerSelect } from '../components/pickers'
import { Badge, Button, Card, DefinitionList, ErrorBox, Field, Input, Modal, PageHeader, Select, Spinner, StatusBadge, Textarea } from '../components/ui'
import api from '../lib/api'
import { fmtDate, fmtDateTime, humanize } from '../lib/format'
import { useAction, useFetch } from '../lib/hooks'
import { localName, t } from '../lib/i18n'
import { useAuth } from '../lib/auth'

const NEXT = {
  open: ['in_progress', 'escalated', 'resolved', 'closed'],
  in_progress: ['escalated', 'resolved', 'closed', 'open'],
  escalated: ['in_progress', 'resolved', 'closed'],
  resolved: ['closed', 'in_progress'],
  closed: ['in_progress'],
}

export default function CaseDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const { user } = useAuth()
  const isSuperAdmin = user?.role === 'super_admin' || user?.role === 'stakeholder'
  const isVolunteer = user?.role === 'volunteer'
  const { data: c, error, setData } = useFetch(`/cases/${id}`)
  const [note, setNote] = useState({ type: 'note', text: '', next_action: '' })
  const [statusModal, setStatusModal] = useState(null)
  const [statusNote, setStatusNote] = useState('')
  const [assign, setAssign] = useState(null)
  const { busy, error: actErr, run } = useAction()

  if (error) return <ErrorBox message={error} />
  if (!c) return <Spinner />

  const deleteCase = async () => {
    const reason = window.prompt(t('Enter reason for deleting this case:'), t('Deleted by Super Admin'))
    if (!reason) return
    try {
      await api.delete(`/cases/${id}?reason=${encodeURIComponent(reason)}`)
      nav('/cases')
    } catch (err) {
      alert(err?.response?.data?.detail || err?.message || 'Failed to delete case')
    }
  }

  const refresh = async () => setData((await api.get(`/cases/${id}`)).data)
  const addNote = () => run(async () => {
    await api.post(`/cases/${id}/notes`, { ...note, next_action: note.next_action || null })
    setNote({ type: 'note', text: '', next_action: '' })
    await refresh()
  }).catch(() => {})
  const changeStatus = () => run(async () => {
    await api.post(`/cases/${id}/status`, { status: statusModal, note: statusNote })
    setStatusModal(null)
    setStatusNote('')
    await refresh()
  }).catch(() => {})
  const doAssign = () => run(async () => {
    await api.post(`/cases/${id}/assign`, { assigned_to: assign.assigned_to, due_date: assign.due_date || null, next_action: assign.next_action || null })
    setAssign(null)
    await refresh()
  }).catch(() => {})

  return (
    <div className="space-y-4">
      <Link to="/cases" className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline"><ArrowLeft className="h-4 w-4" /> {t('Cases')}</Link>
      <PageHeader
        title={<span>{c.case_code} · {c.title}</span>}
        subtitle={<>{t('Girl')} <Link className="text-brand-700 hover:underline" to={`/girls/${c.girl_id}`}>{c.girl?.girl_code}{c.girl?.name && ` · ${localName(c.girl)}`}</Link></>}
        actions={<>
          {NEXT[c.status].filter((s) => !isVolunteer || s !== 'closed').map((s) => <Button key={s} size="sm" variant={s === 'escalated' ? 'danger' : 'secondary'} onClick={() => setStatusModal(s)}>Mark {humanize(s).toLowerCase()}</Button>)}
          {!isVolunteer && <Button size="sm" onClick={() => setAssign({ assigned_to: c.assigned_to || '' })}>{t('Assign')}</Button>}
          {isSuperAdmin && <Button size="sm" variant="danger" icon={Trash2} onClick={deleteCase}>{t('Delete case')}</Button>}
        </>}
      />
      <ErrorBox message={actErr} />
      <div className="flex flex-wrap gap-2">
        <StatusBadge value={c.status} /> <StatusBadge value={c.severity} /> <Badge>{humanize(c.category)}</Badge>
        {c.sensitive && <Badge tone="red">{t('Sensitive')}</Badge>}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title={t('Details')} className="lg:col-span-1">
          <DefinitionList items={[
            ['Assigned to', c.assignee?.name || t('Unassigned')], ['Due date', fmtDate(c.due_date)], ['Next action', c.next_action],
            ['Opened', fmtDateTime(c.opened_at)], ['Source', humanize(c.source?.type)], ['Resolved', fmtDateTime(c.resolved_at)],
          ]} />
          {c.description && <p className="mt-3 whitespace-pre-wrap text-sm text-gray-700">{c.description}</p>}
        </Card>
        <Card title={t('Timeline')} className="lg:col-span-2">
          <div className="mb-4 space-y-2 rounded-lg bg-gray-50 p-3">
            <div className="grid gap-2 sm:grid-cols-3">
              <Select options={['note', 'follow_up', 'visit', 'call', 'referral']} value={note.type} onChange={(e) => setNote({ ...note, type: e.target.value })} />
              <div className="sm:col-span-2"><Input placeholder={t('Next action (optional)')} value={note.next_action} onChange={(e) => setNote({ ...note, next_action: e.target.value })} /></div>
            </div>
            <Textarea placeholder={t('What happened?')} value={note.text} onChange={(e) => setNote({ ...note, text: e.target.value })} />
            <div className="flex justify-end"><Button size="sm" busy={busy} disabled={!note.text.trim()} onClick={addNote}>{t('Add to timeline')}</Button></div>
          </div>
          <ol className="space-y-3">
            {[...c.timeline].reverse().map((ev, i) => (
              <li key={i} className="border-l-2 border-brand-200 pl-3">
                <div className="text-xs text-gray-500">{fmtDateTime(ev.at)} · {ev.by_name || t('system')} · {humanize(ev.type)}{ev.to && ` → ${humanize(ev.to)}`}</div>
                <div className="whitespace-pre-wrap text-sm text-gray-800">{ev.text}</div>
              </li>
            ))}
          </ol>
        </Card>
      </div>
      <Modal open={Boolean(statusModal)} title={t('Mark case as {status}', { status: humanize(statusModal) })} onClose={() => setStatusModal(null)}
        footer={<><Button variant="secondary" onClick={() => setStatusModal(null)}>{t('Cancel')}</Button><Button busy={busy} disabled={statusNote.trim().length < 3} onClick={changeStatus}>{t('Confirm')}</Button></>}>
        <ErrorBox message={actErr} />
        <Field label={statusModal === 'resolved' || statusModal === 'closed' ? t('Resolution summary *') : t('Reason *')}>
          <Textarea value={statusNote} onChange={(e) => setStatusNote(e.target.value)} />
        </Field>
        <p className="text-xs text-gray-500">{t('Sensitive cases are only closed by a person — the system never closes cases automatically.')}</p>
      </Modal>
      {!isVolunteer && <Modal open={Boolean(assign)} title={t('Assign case')} onClose={() => setAssign(null)}
        footer={<><Button variant="secondary" onClick={() => setAssign(null)}>{t('Cancel')}</Button><Button busy={busy} disabled={!assign?.assigned_to} onClick={doAssign}>{t('Assign')}</Button></>}>
        <ErrorBox message={actErr} />
        <Field label={t('Volunteer')}><VolunteerSelect villageId={c.village_id} value={assign?.assigned_to} onChange={(v) => setAssign({ ...assign, assigned_to: v })} placeholder={t('Select…')} /></Field>
        <Field label={t('Due date')}><Input type="date" value={assign?.due_date || ''} onChange={(e) => setAssign({ ...assign, due_date: e.target.value })} /></Field>
        <Field label={t('Next action')}><Input value={assign?.next_action || ''} onChange={(e) => setAssign({ ...assign, next_action: e.target.value })} /></Field>
      </Modal>}
    </div>
  )
}
