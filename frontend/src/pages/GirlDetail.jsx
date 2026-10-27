import { ArrowLeft, ArrowRightLeft, FileText, Pencil, Plus, Trash2, Upload } from 'lucide-react'
import VoiceTextarea from '../components/VoiceTextarea'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { LookupSelect, VolunteerSelect } from '../components/pickers'
import { Badge, Button, Card, DefinitionList, ErrorBox, Field, Input, Modal, PageHeader, Select, Spinner, StatusBadge, Table, Tabs, Textarea } from '../components/ui'
import api, { errorMessage } from '../lib/api'
import { fmtDate, fmtDateTime, humanize, todayISO } from '../lib/format'
import { useAction, useFetch, useLookups } from '../lib/hooks'
import { GirlForm } from './Girls'
import { AADHAAR_SIDES, uploadAadhaar } from '../lib/aadhaar'
import { casteLabel, categoryLabel, getLang, localName, t } from '../lib/i18n'
import { useAuth } from '../lib/auth'

export function CaseCreateModal({ open, onClose, girl, onCreated }) {
  const [f, setF] = useState({ severity: 'medium', sensitive: true })
  const { busy, error, run } = useAction()
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }))
  const submit = () => run(async () => {
    const r = await api.post('/cases', { girl_id: girl.id, ...f, assigned_to: f.assigned_to || null, due_date: f.due_date || null })
    onCreated(r.data)
  }).catch(() => {})
  return (
    <Modal open={open} title={t('New case for {code}', { code: girl.girl_code })} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button><Button busy={busy} onClick={submit} disabled={!f.category || !f.title}>{t('Open case')}</Button></>}>
      <ErrorBox message={error} />
      <Field label={t('Title *')}><Input value={f.title || ''} onChange={(e) => set('title', e.target.value)} /></Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t('Category *')}><LookupSelect type="case_category" value={f.category} onChange={(v) => set('category', v)} /></Field>
        <Field label={t('Severity')}><Select options={['critical', 'high', 'medium', 'low']} value={f.severity} onChange={(e) => set('severity', e.target.value)} /></Field>
        <Field label={t('Assign to volunteer')}><VolunteerSelect villageId={girl.village_id} value={f.assigned_to} onChange={(v) => set('assigned_to', v)} placeholder={t('Unassigned')} /></Field>
        <Field label={t('Due date')} hint={t('Defaults from severity rules')}><Input type="date" value={f.due_date || ''} onChange={(e) => set('due_date', e.target.value)} /></Field>
      </div>
      <Field label={t('Description')}><Textarea value={f.description || ''} onChange={(e) => set('description', e.target.value)} /></Field>
      <Field label={t('Next action')}><Input value={f.next_action || ''} onChange={(e) => set('next_action', e.target.value)} /></Field>
    </Modal>
  )
}

function HealthTab({ girl, reload }) {
  const { user: me } = useAuth()
  const isSuperAdmin = me?.role === 'super_admin' || me?.role === 'stakeholder'
  const { data, reload: reloadHealth } = useFetch(`/girls/${girl.id}/health`)
  const fields = useLookups('health_field')
  const [adding, setAdding] = useState(false)
  const [f, setF] = useState({ recorded_on: todayISO(), source: 'health_camp', observations: {} })
  const { busy, error, run } = useAction()
  const setObs = (k, v) => setF((p) => ({ ...p, observations: { ...p.observations, [k]: v } }))
  const submit = () => run(async () => {
    const obs = Object.fromEntries(Object.entries(f.observations).filter(([, v]) => v !== '' && v !== undefined))
    await api.post(`/girls/${girl.id}/health`, {
      ...f, observations: obs, hb_level: f.hb_level ? Number(f.hb_level) : null,
      weight_kg: f.weight_kg ? Number(f.weight_kg) : null, height_cm: f.height_cm ? Number(f.height_cm) : null,
    })
    setAdding(false)
    reloadHealth()
    reload()
  }).catch(() => {})
  return (
    <Card title={t('Health records')} actions={<Button size="sm" icon={Plus} onClick={() => setAdding(true)}>{t('Add record')}</Button>}>
      {!data ? <Spinner /> : (
        <Table columns={[
          { key: 'recorded_on', label: t('Date'), render: (r) => fmtDate(r.recorded_on) },
          { key: 'hb_level', label: t('Hb (g/dL)') },
          { key: 'anaemia_status', label: t('Anaemia'), render: (r) => <StatusBadge value={r.anaemia_status} /> },
          { key: 'bmi', label: t('BMI') },
          { key: 'source', label: t('Source'), render: (r) => humanize(r.source) },
          { key: 'observations', label: t('Observations'), render: (r) => Object.entries(r.observations || {}).map(([k, v]) => `${humanize(k)}: ${v === true ? t('Yes') : v === false ? t('No') : v}`).join(' · ') || '—' },
          ...(isSuperAdmin ? [{
            key: 'del', label: '', render: (r) => (
              <button type="button" title={t('Delete record')} className="p-1 text-red-500 hover:text-red-700" onClick={async (e) => {
                e.stopPropagation()
                if (!window.confirm(t('Are you sure you want to delete this health record?'))) return
                await api.delete(`/girls/${girl.id}/health/${r.id}`)
                reloadHealth(); reload()
              }}><Trash2 className="h-4 w-4" /></button>
            )
          }] : []),
        ]} rows={data.records} empty={t('No health records yet.')} />
      )}
      <Modal open={adding} title={t('Add health record')} onClose={() => setAdding(false)}
        footer={<><Button variant="secondary" onClick={() => setAdding(false)}>{t('Cancel')}</Button><Button busy={busy} onClick={submit}>{t('Save')}</Button></>}>
        <ErrorBox message={error} />
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t('Date')}><Input type="date" max={todayISO()} value={f.recorded_on} onChange={(e) => setF({ ...f, recorded_on: e.target.value })} /></Field>
          <Field label={t('Source')}><Select options={['health_camp', 'home_visit', 'event', 'school', 'phc', 'other']} value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })} /></Field>
          <Field label={t('Haemoglobin (g/dL)')}><Input type="number" step="0.1" value={f.hb_level || ''} onChange={(e) => setF({ ...f, hb_level: e.target.value })} /></Field>
          <Field label={t('Weight (kg)')}><Input type="number" value={f.weight_kg || ''} onChange={(e) => setF({ ...f, weight_kg: e.target.value })} /></Field>
          <Field label={t('Height (cm)')}><Input type="number" value={f.height_cm || ''} onChange={(e) => setF({ ...f, height_cm: e.target.value })} /></Field>
        </div>
        {fields.map((fd) => {
          const dataType = fd.attributes?.data_type
          const v = f.observations[fd.code]
          return (
            <Field key={fd.code} label={`${fd.label}${fd.label_mr ? ` · ${fd.label_mr}` : ''}`}>
              {dataType === 'boolean' ? (
                <Select options={[{ value: 'true', label: t('Yes') }, { value: 'false', label: t('No') }]} placeholder={t('Not recorded')}
                  value={v === undefined ? '' : String(v)} onChange={(e) => setObs(fd.code, e.target.value === '' ? undefined : e.target.value === 'true')} />
              ) : dataType === 'select' ? (
                <Select options={fd.attributes.options || []} placeholder={t('Not recorded')} value={v || ''} onChange={(e) => setObs(fd.code, e.target.value)} />
              ) : dataType === 'number' ? (
                <Input type="number" value={v ?? ''} onChange={(e) => setObs(fd.code, e.target.value === '' ? undefined : Number(e.target.value))} />
              ) : (
                <Input value={v || ''} onChange={(e) => setObs(fd.code, e.target.value)} />
              )}
            </Field>
          )
        })}
      </Modal>
    </Card>
  )
}

function AadhaarCard({ girl }) {
  const { data: media, reload } = useFetch('/media', { entity_type: 'girl', entity_id: girl.id })
  const [urls, setUrls] = useState({})
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const byKind = Object.fromEntries((media || []).filter((m) => m.kind).map((m) => [m.kind, m]))

  useEffect(() => {
    let alive = true
    const created = []
    ;(async () => {
      for (const m of media || []) {
        if (!m.kind) continue
        try {
          const r = await api.get(`/media/${m.id}/file`, { responseType: 'blob' })
          const u = URL.createObjectURL(r.data)
          created.push(u)
          if (alive) setUrls((p) => ({ ...p, [m.id]: u }))
        } catch { /* ignore broken file */ }
      }
    })()
    return () => { alive = false; created.forEach(URL.revokeObjectURL) }
  }, [media])

  const replace = async (kind, file) => {
    setBusy(kind)
    setError(null)
    try {
      await uploadAadhaar(girl.id, kind, file)
      reload()
    } catch (e) {
      setError(errorMessage(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <Card title={t('Aadhaar card')}>
      <ErrorBox message={error} />
      {!media ? <Spinner /> : (
        <div className="grid gap-4 sm:grid-cols-2">
          {AADHAAR_SIDES.map(({ kind, label }) => {
            const m = byKind[kind]
            const url = m && urls[m.id]
            return (
              <div key={kind}>
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-gray-700">{t(label)}</span>
                  <label className="inline-flex cursor-pointer items-center gap-1 text-xs font-medium text-brand-700 hover:underline">
                    <Upload className="h-3.5 w-3.5" /> {busy === kind ? t('Uploading…') : m ? t('Replace') : t('Upload')}
                    <input type="file" accept="image/*,application/pdf" className="sr-only" disabled={Boolean(busy)}
                      onChange={(e) => { if (e.target.files[0]) replace(kind, e.target.files[0]); e.target.value = '' }} />
                  </label>
                </div>
                <div className="flex h-44 items-center justify-center overflow-hidden rounded-lg border border-gray-200 bg-gray-50 text-sm text-gray-500">
                  {!m ? t('Not uploaded') : !url ? <Spinner /> : m.content_type?.startsWith('image/') ? (
                    <a href={url} target="_blank" rel="noreferrer" className="h-full w-full"><img src={url} alt={t(label)} className="h-full w-full object-contain" /></a>
                  ) : (
                    <a href={url} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-brand-700 hover:underline"><FileText className="h-5 w-5" /> {m.original_name || 'PDF'}</a>
                  )}
                </div>
                {m && <div className="mt-1 text-xs text-gray-500">{t('Uploaded {date}', { date: fmtDateTime(m.uploaded_at) })}</div>}
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}

/** Rows of a definition list that have a value. */
const filled = (items) => items.filter(([, v]) => v !== undefined && v !== null && v !== '' && v !== '—')

/** Answers from the baseline survey (Master Data form), shown question by question. */
function BaselineSurvey({ survey }) {
  const [open, setOpen] = useState(false)
  const answers = Object.entries(survey).filter(([q]) => !q.startsWith('_'))
  return (
    <Card title={t('Baseline survey')} className="lg:col-span-2"
      actions={<Button variant="secondary" onClick={() => setOpen(!open)}>{open ? t('Hide') : t('Show {n} answers', { n: answers.length })}</Button>}>
      <p className="text-xs text-gray-500">{t('Survey date')}: {fmtDate(survey._survey_date)}</p>
      {open && <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
        {answers.map(([q, a]) => <div key={q} className="border-b border-gray-100 pb-2"><dt className="text-xs text-gray-500">{q}</dt><dd className="text-gray-900">{a}</dd></div>)}
      </dl>}
    </Card>
  )
}

function MergeModal({ open, onClose, girl, onMerged }) {
  const [dupId, setDupId] = useState('')
  const [reason, setReason] = useState('')
  const [candidates, setCandidates] = useState(null)
  const { busy, error, run } = useAction()
  const findCandidates = () => run(async () => {
    const r = await api.post('/girls/check-duplicates', { name: girl.name, village_id: girl.village_id, exclude_id: girl.id, household: girl.household })
    setCandidates(r.data.candidates)
  }).catch(() => {})
  const merge = () => run(async () => {
    const r = await api.post(`/girls/${girl.id}/merge`, { duplicate_id: dupId, reason })
    onMerged(r.data)
  }).catch(() => {})
  return (
    <Modal open={open} title={t('Merge a duplicate into {code}', { code: girl.girl_code })} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button><Button variant="danger" busy={busy} disabled={!dupId || reason.length < 3} onClick={merge}>{t('Merge')}</Button></>}>
      <ErrorBox message={error} />
      <p className="text-sm text-gray-600">{t("The duplicate's visits, events, health records and cases move to this girl, and the duplicate record is removed.")}</p>
      <Button size="sm" variant="secondary" onClick={findCandidates} disabled={!girl.name}>{t('Find likely duplicates')}</Button>
      {candidates && (candidates.length ? (
        <div className="space-y-1">
          {candidates.map((c) => (
            <label key={c.girl.id} className="flex items-center gap-2 text-sm">
              <input type="radio" name="dup" checked={dupId === c.girl.id} onChange={() => setDupId(c.girl.id)} />
              {c.girl.girl_code} · {localName(c.girl)} <span className="text-gray-500">({t('{n}% match', { n: Math.round(c.score * 100) })})</span>
            </label>
          ))}
        </div>
      ) : <p className="text-sm text-gray-500">{t('No likely duplicates found.')}</p>)}
      <Field label={t('Duplicate record id (or pick above)')}><Input value={dupId} onChange={(e) => setDupId(e.target.value)} /></Field>
      <Field label={t('Reason *')}><Input value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
    </Modal>
  )
}


export function TransferToExternalModal({ open, girl, onClose, onTransferred }) {
  const h = girl?.household || {}
  const [reason, setReason] = useState('')
  const [notes, setNotes] = useState('')
  const [status, setStatus] = useState('active')
  const [phone, setPhone] = useState(() => girl?.phone || h.phone || '')
  const [location, setLocation] = useState(() => {
    const vName = localName(girl?.village) || ''
    const addr = h.address || h.hamlet || ''
    return [vName, addr].filter(Boolean).join(', ')
  })
  const [guardianName, setGuardianName] = useState(
    () => h.guardian_name || h.father_name || h.mother_name || h.head_name || ''
  )
  const [guardianRelation, setGuardianRelation] = useState(
    () => (h.father_name ? 'father' : h.mother_name ? 'mother' : '')
  )
  const { busy, error, run } = useAction()

  useEffect(() => {
    if (open && girl) {
      const hh = girl.household || {}
      setReason('')
      setNotes('')
      setStatus('active')
      setPhone(girl.phone || hh.phone || '')
      const vName = localName(girl.village) || ''
      const addr = hh.address || hh.hamlet || ''
      setLocation([vName, addr].filter(Boolean).join(', '))
      setGuardianName(hh.guardian_name || hh.father_name || hh.mother_name || hh.head_name || '')
      setGuardianRelation(hh.father_name ? 'father' : hh.mother_name ? 'mother' : '')
    }
  }, [open, girl])

  const PRESETS = [
    { label: t('Married (विवाह झाला)'), text: 'विवाह झाल्यामुळे सासरी गेली (Married)' },
    { label: t('Migrated for education (शिक्षणासाठी स्थलांतर)'), text: 'शिक्षणासाठी शहरात स्थलांतर केले (Migrated for studies)' },
    { label: t('Family migrated (कुटुंब स्थलांतर)'), text: 'कुटुंब गावाबाहेर स्थलांतरित झाले (Family migrated)' },
    { label: t('Job / employment (नोकरी / काम)'), text: 'कामासाठी / नोकरीसाठी बाहेर (Working outside)' },
    { label: t('Aged out (वय पूर्ण झाले)'), text: 'वय पूर्ण झाल्याने गट सोडला (Age 20+ years)' },
  ]

  const appendPreset = (presetText) => {
    if (!reason.trim()) {
      setReason(presetText)
    } else if (!reason.includes(presetText)) {
      setReason(`${reason.trim()}, ${presetText}`)
    }
  }

  const submit = () =>
    run(async () => {
      const payload = {
        reason: reason.trim(),
        notes: notes.trim() || null,
        status,
        phone: phone.trim() || null,
        location: location.trim() || null,
        guardian_name: guardianName.trim() || null,
        guardian_relation: guardianRelation.trim() || null,
        education_status: girl.school_status || null,
        school_or_college: girl.school_name || null,
        standard: girl.standard || null,
      }
      const res = await api.post(`/girls/${girl.id}/transfer-to-external`, payload)
      onTransferred(res.data)
    })

  return (
    <Modal
      open={open}
      title={t('Transfer {code} to External Girls', { code: girl.girl_code })}
      onClose={onClose}
      wide
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            {t('Cancel')}
          </Button>
          <Button
            className="bg-amber-600 hover:bg-amber-700 text-white"
            busy={busy}
            disabled={!reason.trim() || reason.trim().length < 2}
            onClick={submit}
          >
            {t('Transfer to External')}
          </Button>
        </>
      }
    >
      <ErrorBox message={error} />

      <div className="rounded-lg border border-amber-200 bg-amber-50/80 p-3 text-sm text-amber-900">
        <p className="font-semibold">{t('Removal & Transfer Notice')}</p>
        <p className="mt-1 text-xs text-amber-800">
          {t(
            'This action removes {name} ({code}) from the village Kishori database so she no longer requires volunteer home visits or meeting tracking. She is safely moved to External Girls, where any Tai or Stakeholder can stay in touch via phone calls.',
            { name: localName(girl) || girl.girl_code, code: girl.girl_code }
          )}
        </p>
      </div>

      <div className="space-y-3 pt-2">
        <VoiceTextarea
          label={t('Reason for removal / transfer (कारण) *')}
          value={reason}
          onChange={setReason}
          placeholder={t('Click mic to speak in Marathi or English, or type reason (e.g. Married, Migrated)...')}
          rows={3}
          hint={t('Use the microphone button to record reason via speech-to-text in Marathi or English')}
        />

        <div>
          <div className="mb-1.5 text-xs font-medium text-gray-600">{t('Quick reason presets:')}</div>
          <div className="flex flex-wrap gap-1.5">
            {PRESETS.map((p) => (
              <button
                key={p.label}
                type="button"
                className="rounded-full border border-gray-300 bg-white px-2.5 py-1 text-xs text-gray-700 hover:border-brand-500 hover:bg-brand-50 hover:text-brand-800"
                onClick={() => appendPreset(p.text)}
              >
                + {p.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-3 pt-2 sm:grid-cols-2">
          <Field label={t('Contact mobile (मोबाईल नंबर)')} hint={t('For future phone calls and check-ins')}>
            <Input
              type="tel"
              value={phone}
              placeholder="9876543210"
              onChange={(e) => setPhone(e.target.value)}
            />
          </Field>
          <Field label={t('Location / New address (गाव / पत्ता)')}>
            <Input
              value={location}
              placeholder={t('Village or new location')}
              onChange={(e) => setLocation(e.target.value)}
            />
          </Field>
          <Field label={t('Parent / Guardian name')}>
            <Input
              value={guardianName}
              placeholder={t('Father, mother or guardian')}
              onChange={(e) => setGuardianName(e.target.value)}
            />
          </Field>
          <Field label={t('Status in External list')}>
            <Select
              options={[
                { value: 'active', label: t('Active (सक्रिय)') },
                { value: 'follow_up', label: t('Needs Follow-up (पाठपुरावा आवश्यक)') },
                { value: 'closed', label: t('Closed / Inactive (बंद)') },
              ]}
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            />
          </Field>
          <Field label={t('Additional notes / background')} className="sm:col-span-2">
            <Textarea
              rows={2}
              value={notes}
              placeholder={t('Optional notes on new town, college, husband name, etc.')}
              onChange={(e) => setNotes(e.target.value)}
            />
          </Field>
        </div>
      </div>
    </Modal>
  )
}

export default function GirlDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const isSuperAdmin = user?.role === 'super_admin' || user?.role === 'stakeholder'
  const isVolunteer = user?.role === 'volunteer'
  const nav = useNavigate()
  const { data: g, error, reload, setData } = useFetch(`/girls/${id}`)

  const deleteGirl = async () => {
    const reason = window.prompt(t('Are you sure you want to delete {name} ({code})? Enter reason:', { name: localName(g), code: g.girl_code }), t('Deleted by Super Admin'))
    if (reason === null) return
    try {
      await api.delete(`/girls/${g.id}?reason=${encodeURIComponent(reason || 'Deleted by Super Admin')}`)
      nav('/girls')
    } catch (e) {
      alert(errorMessage(e))
    }
  }
  const [tab, setTab] = useState('profile')
  const [editing, setEditing] = useState(false)
  const [aadhaarVersion, setAadhaarVersion] = useState(0)
  const [newCase, setNewCase] = useState(false)
  const [merging, setMerging] = useState(false)
  const { data: part } = useFetch(tab === 'participation' ? `/girls/${id}/participation` : null)
  const { data: cases, reload: reloadCases } = useFetch(tab === 'cases' ? `/girls/${id}/cases` : null)
  const [transferring, setTransferring] = useState(false)

  if (error) return <ErrorBox message={error} />
  if (!g) return <Spinner />
  const h = g.household || {}

  return (
    <div className="space-y-4">
      <Link to="/girls" className="inline-flex items-center gap-1 text-sm text-brand-700 hover:underline"><ArrowLeft className="h-4 w-4" /> {t('Girls')}</Link>
      <PageHeader
        title={<span>{g.girl_code} {g.name && <span className="text-gray-600">· {localName(g)}</span>}</span>}
        subtitle={<>{localName(g.village)}{g.group && ` · ${localName(g.group)}`}</>}
        actions={<>
          <Button variant="secondary" icon={Pencil} onClick={() => setEditing(true)}>{t('Edit')}</Button>
          <Button variant="secondary" icon={Plus} onClick={() => setNewCase(true)}>{t('New case')}</Button>
          {!isVolunteer && <Button variant="ghost" onClick={() => setMerging(true)}>{t('Merge duplicate')}</Button>}
          <Button
            variant="secondary"
            className="border-amber-300 text-amber-800 hover:bg-amber-50"
            icon={ArrowRightLeft}
            onClick={() => setTransferring(true)}
          >
            {t('Transfer to External')}
          </Button>
          {isSuperAdmin && (
            <Button
              variant="danger"
              icon={Trash2}
              onClick={deleteGirl}
            >
              {t('Delete')}
            </Button>
          )}
        </>}
      />
      <div className="flex flex-wrap gap-2">
        {g.flags?.profile_incomplete && <Badge>{t('Profile incomplete')}</Badge>}
        {g.flags?.needs_review && <Badge tone="red">{t('Village needs review')}: {g.source_village_raw}</Badge>}
        <StatusBadge value={g.enrollment?.status} />
        {g.case_summary?.open > 0 && <Badge tone="orange">{t('{n} open case(s)', { n: g.case_summary.open })}</Badge>}
        {g.health_summary?.anaemia_status && <Badge tone="yellow">{t('Anaemia')}: {humanize(g.health_summary.anaemia_status)}</Badge>}
      </div>
      <Tabs tabs={['profile', 'health', 'cases', 'participation']} value={tab} onChange={setTab} />

      {tab === 'profile' && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title={t('Profile')}>
            <DefinitionList items={filled([
              ['Age', g.current_age ?? '—'], ['Date of birth', fmtDate(g.dob)], ['Birth year', g.dob ? null : g.birth_year],
              ['Mobile', g.phone], ['Village', g.village && localName(g.village)], ['Group', g.group && localName(g.group)], ['Bal Panchayat', g.bal_panchayat && localName(g.bal_panchayat)],
              ['School status', g.school_status && t(humanize(g.school_status))],
              ['School', g.school_name], ['Standard', g.standard], ['Survey date', fmtDate(g.survey_date)],
              ['Enrolled on', fmtDate(g.enrollment?.enrolled_on)], ['Source', g.source && t(humanize(g.source))],
            ])} />
          </Card>
          <Card title={t('Household')}>
            <DefinitionList items={filled([
              ['Father', h.father_name], ['Mother', h.mother_name], ['Head', h.head_name], ['Mobile', h.phone],
              ['Members', h.members_count], ['Economic status', h.economic_status?.toUpperCase()], ['Address', h.address],
              ['Category', categoryLabel(h.social_category) || null], ['Caste', casteLabel(g) || null],
            ])} />
          </Card>
          {g.custom_fields?.baseline_survey && <BaselineSurvey survey={getLang() === 'mr' ? g.custom_fields.baseline_survey : g.baseline_survey_en || g.custom_fields.baseline_survey} />}
          <Card title={t('Participation summary')}>
            <DefinitionList items={[
              ['Events attended', g.participation?.events_attended], ['Attendance rate', g.participation?.attendance_rate != null ? `${Math.round(g.participation.attendance_rate * 100)}%` : '—'],
              ['Home visits', g.participation?.home_visits], ['Last participation', fmtDate(g.last_participation_at)],
            ]} />
          </Card>
          <Card title={t('Recent cases')}>
            <Table columns={[
              { key: 'case_code', label: t('Case'), render: (r) => <Link className="text-brand-700 hover:underline" to={`/cases/${r.id}`}>{r.case_code}</Link> },
              { key: 'category', label: t('Category'), render: (r) => humanize(r.category) },
              { key: 'severity', label: t('Severity'), render: (r) => <StatusBadge value={r.severity} /> },
              { key: 'status', label: t('Status'), render: (r) => <StatusBadge value={r.status} /> },
            ]} rows={g.recent_cases} empty={t('No cases.')} />
          </Card>
          <div className="lg:col-span-2"><AadhaarCard key={aadhaarVersion} girl={g} /></div>
        </div>
      )}
      {tab === 'health' && <HealthTab girl={g} reload={reload} />}
      {tab === 'cases' && (
        <Card title={t('Case history')} actions={<Button size="sm" icon={Plus} onClick={() => setNewCase(true)}>{t('New case')}</Button>}>
          {!cases ? <Spinner /> : (
            <Table columns={[
              { key: 'case_code', label: t('Case'), render: (r) => <Link className="text-brand-700 hover:underline" to={`/cases/${r.id}`}>{r.case_code}</Link> },
              { key: 'title', label: t('Title') },
              { key: 'category', label: t('Category'), render: (r) => humanize(r.category) },
              { key: 'severity', label: t('Severity'), render: (r) => <StatusBadge value={r.severity} /> },
              { key: 'status', label: t('Status'), render: (r) => <StatusBadge value={r.status} /> },
              { key: 'opened_at', label: t('Opened'), render: (r) => fmtDate(r.opened_at) },
            ]} rows={cases.cases} empty={t('No cases.')} />
          )}
        </Card>
      )}
      {tab === 'participation' && (
        <Card title={t('Participation history')}>
          {!part ? <Spinner /> : (
            <Table rowKey={(r) => `${r.type}-${r.id}`} columns={[
              { key: 'date', label: t('Date'), render: (r) => fmtDateTime(r.date) },
              { key: 'type', label: t('Type'), render: (r) => humanize(r.type) },
              { key: 'detail', label: t('Detail'), render: (r) => r.title || humanize(r.purpose || r.source) || '—' },
              { key: 'status', label: t('Status'), render: (r) => (r.present !== undefined ? (r.present ? t('Present') : t('Absent')) : humanize(r.visit_status || r.event_status)) },
            ]} rows={part.items} empty={t('No participation recorded yet.')} />
          )}
        </Card>
      )}

      <Modal open={editing} title={t('Edit {code}', { code: g.girl_code })} onClose={() => setEditing(false)} wide>
        <GirlForm initial={{ ...g, dob: g.dob?.slice(0, 10) }} onCancel={() => setEditing(false)} onSaved={(r) => { setData({ ...g, ...r }); setEditing(false); setAadhaarVersion((v) => v + 1); reload() }} />
      </Modal>
      <CaseCreateModal open={newCase} onClose={() => setNewCase(false)} girl={g} onCreated={() => { setNewCase(false); reload(); reloadCases() }} />
      {!isVolunteer && <MergeModal open={merging} onClose={() => setMerging(false)} girl={g} onMerged={() => { setMerging(false); reload() }} />}
      <TransferToExternalModal
        open={transferring}
        girl={g}
        onClose={() => setTransferring(false)}
        onTransferred={() => {
          setTransferring(false)
          nav('/external-girls')
        }}
      />

    </div>
  )
}
