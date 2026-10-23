import { Camera, MapPin, Mic, Plus, Save } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../lib/auth'
import { Button, Card, Checkbox, Empty, ErrorBox, Field, Input, Modal, PageHeader, Select, Spinner, StatusBadge, Table, Tabs, Textarea } from '../components/ui'
import api, { errorMessage } from '../lib/api'
import { fmtDate, humanize, todayISO } from '../lib/format'
import { useAction, useFetch, useLookups } from '../lib/hooks'
import { localName, t } from '../lib/i18n'

function GirlMultiPicker({ villageId, value, onChange }) {
  const [search, setSearch] = useState('')
  const { data, loading, error } = useFetch(villageId ? '/girls' : null, { page: 1, page_size: 500, sort: 'name' })
  const girls = (data?.items || []).filter((girl) => !villageId || girl.village_id === villageId).filter((girl) => `${girl.name || ''} ${girl.name_en || ''} ${girl.girl_code || ''}`.toLowerCase().includes(search.toLowerCase()))
  const toggle = (id) => onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id])
  return <div className="space-y-2">
    <Input placeholder={t('Search girls')} value={search} onChange={(e) => setSearch(e.target.value)} />
    <ErrorBox message={error} />
    {loading ? <Spinner /> : girls.length ? <div className="max-h-44 space-y-1 overflow-y-auto rounded-lg border border-gray-200 p-2">{girls.map((girl) => <label key={girl.id} className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-gray-50"><input type="checkbox" checked={value.includes(girl.id)} onChange={() => toggle(girl.id)} /><span className="font-medium">{girl.girl_code}</span><span>{localName(girl) || t('Name not recorded')}</span></label>)}</div> : <Empty>{t('No girls registered in your village yet.')}</Empty>}
  </div>
}

function VoiceTextarea({ label, value, onChange }) {
  const [listening, setListening] = useState(false)
  const [voiceError, setVoiceError] = useState('')
  const startVoice = () => {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!Recognition) { setVoiceError(t('Voice input is not supported in this browser.')); return }
    setVoiceError('')
    const recognition = new Recognition()
    recognition.lang = 'mr-IN'
    recognition.interimResults = false
    recognition.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript || ''
      if (transcript) onChange([value, transcript].filter(Boolean).join(' '))
    }
    recognition.onerror = () => setVoiceError(t('Could not capture speech. Check microphone permission and try again.'))
    recognition.onend = () => setListening(false)
    setListening(true)
    recognition.start()
  }
  return <Field label={label}>
    <Textarea value={value || ''} onChange={(e) => onChange(e.target.value)} />
    <div className="mt-1 flex items-center gap-2"><Button size="sm" variant="secondary" icon={Mic} onClick={startVoice} disabled={listening}>{listening ? t('Listening…') : t('Speak in Marathi')}</Button>{voiceError && <span className="text-xs text-amber-700">{voiceError}</span>}</div>
  </Field>
}

function VisitEditor({ user, onClose, onSaved, submitRecord }) {
  const [form, setForm] = useState({ visit_date: todayISO(), status: 'completed', purpose: 'routine', girl_ids: [], met_with: ['girl'], observations: '', notes: '', is_historical: false })
  const [risks, setRisks] = useState({ child_marriage_risk: false, school_dropout_risk: false, health_concern: false, anaemia_concern: false, gender_discrimination: false, other: '' })
  const [gps, setGps] = useState(null)
  const selectedGirlId = form.girl_ids[0] || ''
  const { data: priorVisits } = useFetch(selectedGirlId ? '/home-visits' : null, { girl_id: selectedGirlId, page: 1, page_size: 3 })
  const { data: relatedCases } = useFetch(selectedGirlId ? '/cases' : null, { girl_id: selectedGirlId, open_only: true, page: 1, page_size: 5 })
  const [gpsBusy, setGpsBusy] = useState(false)
  const [gpsError, setGpsError] = useState('')
  const [photos, setPhotos] = useState([])
  const { busy, error, run } = useAction()
  const captureGps = () => {
    if (!navigator.geolocation) { setGpsError(t('Location is not supported on this device.')); return }
    setGpsBusy(true); setGpsError('')
    navigator.geolocation.getCurrentPosition((position) => {
      setGps({ lat: position.coords.latitude, lng: position.coords.longitude, accuracy_m: position.coords.accuracy, captured_at: new Date().toISOString() })
      setGpsBusy(false)
    }, (err) => { setGpsError(err.message || t('Location permission was not granted.')); setGpsBusy(false) }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 })
  }
  const save = () => run(async () => {
    const result = await submitRecord('/home-visits', { ...form, volunteer_id: user.id, risk_indicators: risks, gps, is_historical: form.visit_date < todayISO() })
    if (result.queued) {
      onSaved()
      if (photos.length) window.alert(t('The visit was saved offline, but photos were not queued. After reconnecting, use Attach photos on the saved visit.'))
      return
    }
    const response = result.response
    let failedPhotos = 0
    for (const file of photos) {
      try {
        const payload = new FormData()
        payload.append('entity_type', 'home_visit'); payload.append('entity_id', response.data.id); payload.append('file', file)
        if (gps) { payload.append('lat', String(gps.lat)); payload.append('lng', String(gps.lng)); payload.append('accuracy_m', String(gps.accuracy_m)); payload.append('captured_at', gps.captured_at) }
        await api.post('/media', payload)
      } catch { failedPhotos += 1 }
    }
    onSaved()
    if (failedPhotos) window.alert(t('{n} photo(s) could not be uploaded. Reopen the visit and try again when connected.', { n: failedPhotos }))
  }).catch(() => {})
  const toggleMet = (value) => setForm((prev) => ({ ...prev, met_with: prev.met_with.includes(value) ? prev.met_with.filter((x) => x !== value) : [...prev.met_with, value] }))
  return <Modal open title={t('Record a home visit')} onClose={onClose} wide footer={<><Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button><Button busy={busy} icon={Save} disabled={!form.visit_date} onClick={save}>{t('Save visit')}</Button></>}>
    <ErrorBox message={error} />
    <div className="grid gap-3 sm:grid-cols-2">
      <Field label={t('Visit date *')}><Input type="date" value={form.visit_date} onChange={(e) => setForm({ ...form, visit_date: e.target.value })} /></Field>
      <Field label={t('Visit status')}><Select options={['completed', 'planned', 'missed']} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} /></Field>
      <Field label={t('Purpose')}><Select options={['routine', 'follow_up', 'case_follow_up', 'enrolment', 'other']} value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })} /></Field>
      <Field label={t('People met')}><div className="flex flex-wrap gap-3">{['girl', 'mother', 'father', 'guardian', 'other_family'].map((person) => <Checkbox key={person} label={t(humanize(person))} checked={form.met_with.includes(person)} onChange={() => toggleMet(person)} />)}</div></Field>
    </div>
    <Field label={t('Girls involved')}><GirlMultiPicker villageId={user?.village_id} value={form.girl_ids} onChange={(ids) => setForm({ ...form, girl_ids: ids })} /></Field>
    {selectedGirlId && <Card title={t('Recent history for selected girl')}>
      <div className="space-y-2">{(priorVisits?.items || []).map((visit) => <div key={visit.id} className="rounded-lg bg-gray-50 p-2 text-xs"><div className="font-medium text-gray-800">{fmtDate(visit.visit_date)} · {humanize(visit.purpose)} · {humanize(visit.status)}</div><div className="mt-1 whitespace-pre-wrap text-gray-600">{visit.observations || visit.notes || t('No observations recorded.')}</div></div>)}{!priorVisits?.items?.length && <p className="text-xs text-gray-500">{t('No previous visits recorded in this village for this girl.')}</p>}</div>
      {relatedCases?.items?.length > 0 && <div className="mt-3 border-t border-gray-100 pt-3"><div className="mb-1 text-xs font-semibold text-gray-700">{t('Open concerns')}</div>{relatedCases.items.map((item) => <div key={item.id} className="mb-1 text-xs text-gray-600">{item.case_code} · {item.title} · {humanize(item.status)}{item.next_action ? ` · ${item.next_action}` : ''}</div>)}</div>}
    </Card>}
    <Field label={t('Risk indicators')}><div className="flex flex-wrap gap-3">{[['child_marriage_risk', 'Child marriage risk'], ['school_dropout_risk', 'School dropout risk'], ['health_concern', 'Health concern'], ['anaemia_concern', 'Anaemia concern'], ['gender_discrimination', 'Gender discrimination']].map(([key, label]) => <Checkbox key={key} label={t(label)} checked={risks[key]} onChange={(e) => setRisks({ ...risks, [key]: e.target.checked })} />)}</div></Field>
    <VoiceTextarea label={t('Observations')} value={form.observations} onChange={(value) => setForm({ ...form, observations: value })} />
    <Field label={t('Notes / next steps')}><Textarea value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
    <div className="rounded-lg border border-gray-200 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2"><div><div className="text-sm font-medium">{t('Visit location')}</div><div className="text-xs text-gray-500">{gps ? t('GPS captured with ±{n} m accuracy', { n: Math.round(gps.accuracy_m) }) : t('Capture location only for this field activity.')}</div></div><Button size="sm" variant="secondary" icon={MapPin} busy={gpsBusy} onClick={captureGps}>{gps ? t('Refresh location') : t('Capture GPS')}</Button></div>
      {gpsError && <p className="mt-2 text-xs text-amber-700">{gpsError}</p>}
    </div>
    <Field label={t('Visit photographs')}><label className="flex cursor-pointer items-center gap-3 rounded-lg border border-dashed border-gray-300 p-3 text-sm text-gray-700 hover:bg-gray-50"><Camera className="h-5 w-5 text-brand-700" /><span>{t('Take a photo or choose from gallery')}<span className="mt-0.5 block text-xs text-gray-500">{t('Photos are attached to this visit after it is saved.')}</span></span><input className="sr-only" type="file" accept="image/*" capture="environment" multiple onChange={(e) => setPhotos(Array.from(e.target.files || []))} /></label>{photos.length > 0 && <p className="mt-1 text-xs text-gray-500">{photos.map((file) => file.name).join(', ')}</p>}</Field>
    {form.visit_date < todayISO() && <p className="rounded-lg bg-amber-50 p-2 text-xs text-amber-800">{t('This is a back-dated entry. It will be marked historical and may require Stakeholder review.')}</p>}
  </Modal>
}

function DailyReportEditor({ user, onClose, onSaved, submitRecord }) {
  const activityTypes = useLookups('activity_type')
  const { data: groups } = useFetch('/groups', { page: 1, page_size: 200 })
  const [form, setForm] = useState({ report_date: todayISO(), activities: [], group_ids: [], girls_present: 0, home_visits_count: 0, home_visit_girl_ids: [], topics_discussed: '', other_meetings: '', is_historical: false })
  const { busy, error, run } = useAction()
  const toggle = (key, id) => setForm((prev) => ({ ...prev, [key]: prev[key].includes(id) ? prev[key].filter((x) => x !== id) : [...prev[key], id] }))
  const save = () => run(async () => {
    await submitRecord('/activity-reports', { ...form, volunteer_id: user.id, girls_present: Number(form.girls_present), home_visits_count: Number(form.home_visits_count), topics_discussed: form.topics_discussed || null, other_meetings: form.other_meetings || null })
    onSaved()
  }).catch(() => {})
  return <Modal open title={t('Daily activity report')} onClose={onClose} wide footer={<><Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button><Button busy={busy} icon={Save} disabled={!form.report_date || !form.activities.length} onClick={save}>{t('Submit daily report')}</Button></>}>
    <ErrorBox message={error} />
    <Field label={t('Report date *')}><Input type="date" max={todayISO()} value={form.report_date} onChange={(e) => setForm({ ...form, report_date: e.target.value })} /></Field>
    <Field label={t('Activities completed *')}><div className="flex flex-wrap gap-3">{activityTypes.map((item) => <Checkbox key={item.code} label={item.label_mr || item.label} checked={form.activities.includes(item.code)} onChange={() => toggle('activities', item.code)} />)}</div></Field>
    <Field label={t('Groups met')}><div className="flex flex-wrap gap-3">{(groups?.items || []).map((group) => <Checkbox key={group.id} label={localName(group)} checked={form.group_ids.includes(group.id)} onChange={() => toggle('group_ids', group.id)} />)}</div></Field>
    <div className="grid gap-3 sm:grid-cols-2"><Field label={t('Girls present')}><Input type="number" min={0} value={form.girls_present} onChange={(e) => setForm({ ...form, girls_present: e.target.value })} /></Field><Field label={t('Home visits completed')}><Input type="number" min={0} value={form.home_visits_count} onChange={(e) => setForm({ ...form, home_visits_count: e.target.value })} /></Field></div>
    <Field label={t('Girls visited at home')}><GirlMultiPicker villageId={user?.village_id} value={form.home_visit_girl_ids} onChange={(ids) => setForm({ ...form, home_visit_girl_ids: ids })} /></Field>
    <VoiceTextarea label={t('Topics discussed')} value={form.topics_discussed} onChange={(value) => setForm({ ...form, topics_discussed: value })} />
    <Field label={t('Other people met / information')}><Textarea value={form.other_meetings} onChange={(e) => setForm({ ...form, other_meetings: e.target.value })} /></Field>
    {form.report_date < todayISO() && <p className="rounded-lg bg-amber-50 p-2 text-xs text-amber-800">{t('This report is back-dated and will be marked historical for review.')}</p>}
  </Modal>
}

function PhotoUploadModal({ visit, onClose, onSaved }) {
  const [files, setFiles] = useState([])
  const { busy, error, run } = useAction()
  const upload = () => run(async () => {
    for (const file of files) {
      const payload = new FormData()
      payload.append('entity_type', 'home_visit')
      payload.append('entity_id', visit.id)
      payload.append('file', file)
      if (visit.gps) {
        payload.append('lat', String(visit.gps.lat)); payload.append('lng', String(visit.gps.lng))
        if (visit.gps.accuracy_m != null) payload.append('accuracy_m', String(visit.gps.accuracy_m))
        if (visit.gps.captured_at) payload.append('captured_at', visit.gps.captured_at)
      }
      await api.post('/media', payload)
    }
    onSaved()
  }).catch(() => {})
  return <Modal open title={t('Attach photos to home visit')} onClose={onClose} footer={<><Button variant="secondary" onClick={onClose}>{t('Cancel')}</Button><Button busy={busy} disabled={!files.length} icon={Camera} onClick={upload}>{t('Upload photos')}</Button></>}>
    <ErrorBox message={error} />
    <p className="mb-3 text-sm text-gray-600">{fmtDate(visit.visit_date)} · {humanize(visit.purpose)}</p>
    <Field label={t('Choose photos')}><Input type="file" accept="image/*" multiple onChange={(e) => setFiles(Array.from(e.target.files || []))} /></Field>
    {files.length > 0 && <p className="text-xs text-gray-500">{files.map((file) => file.name).join(', ')}</p>}
  </Modal>
}

function readQueue(key) {
  try { return JSON.parse(localStorage.getItem(key) || '[]') } catch { return [] }
}

function deviceId() {
  try {
    let id = localStorage.getItem('kvp_device_id')
    if (!id) { id = `web-${crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`}`; localStorage.setItem('kvp_device_id', id) }
    return id
  } catch { return `web-${Date.now()}` }
}

export default function VolunteerFieldRecords() {
  const { user } = useAuth()
  const queueKey = `kvp_field_queue_${user?.id || 'unknown'}`
  const [queue, setQueue] = useState(() => readQueue(queueKey))
  const queueRef = useRef(queue)
  const syncingRef = useRef(false)
  const syncQueueRef = useRef(null)
  const persistQueue = (items) => {
    queueRef.current = items
    setQueue(items)
    try { localStorage.setItem(queueKey, JSON.stringify(items)) } catch { /* storage unavailable */ }
    if (navigator.onLine) api.post('/sync/status', { device_id: deviceId(), pending: items.filter((item) => !item.error).length, failed: items.filter((item) => item.error).length, errors: items.filter((item) => item.error).map((item) => item.error).slice(0, 20) }).catch(() => {})
  }
  const submitRecord = async (endpoint, payload) => {
    const body = { ...payload, client_record_id: payload.client_record_id || crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}` }
    if (!navigator.onLine) {
      persistQueue([...queueRef.current, { id: body.client_record_id, endpoint, payload: body, label: endpoint === '/home-visits' ? 'Home visit' : 'Daily activity report', date: body.visit_date || body.report_date, created_at: new Date().toISOString(), error: null }])
      return { queued: true }
    }
    try { return { queued: false, response: await api.post(endpoint, body) } }
    catch (error) {
      if (error.response) throw error
      persistQueue([...queueRef.current, { id: body.client_record_id, endpoint, payload: body, label: endpoint === '/home-visits' ? 'Home visit' : 'Daily activity report', date: body.visit_date || body.report_date, created_at: new Date().toISOString(), error: null }])
      return { queued: true }
    }
  }
  const syncQueue = async (retryFailed = false) => {
    if (syncingRef.current || !navigator.onLine) return
    syncingRef.current = true
    let items = queueRef.current.map((item) => retryFailed ? { ...item, error: null } : item)
    let synced = 0
    for (const item of [...items]) {
      if (item.error) continue
      try {
        await api.post(item.endpoint, item.payload)
        items = items.filter((candidate) => candidate.id !== item.id)
        synced += 1
        persistQueue(items)
      } catch (error) {
        if (!error.response) break
        items = items.map((candidate) => candidate.id === item.id ? { ...candidate, error: errorMessage(error) } : candidate)
        persistQueue(items)
      }
    }
    persistQueue(items)
    if (navigator.onLine) api.post('/sync/status', { device_id: deviceId(), pending: items.filter((item) => !item.error).length, failed: items.filter((item) => item.error).length, synced_in_batch: synced, errors: items.filter((item) => item.error).map((item) => item.error).slice(0, 20) }).catch(() => {})
    syncingRef.current = false
  }
  syncQueueRef.current = syncQueue
  useEffect(() => {
    const saved = readQueue(queueKey)
    queueRef.current = saved; setQueue(saved)
  }, [queueKey])
  useEffect(() => {
    const onOnline = () => syncQueueRef.current?.(false)
    window.addEventListener('online', onOnline)
    if (navigator.onLine) syncQueueRef.current?.(false)
    return () => window.removeEventListener('online', onOnline)
  }, [])
  const [tab, setTab] = useState('visits')
  const [modal, setModal] = useState(null)
  const [photoVisit, setPhotoVisit] = useState(null)
  const [status, setStatus] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const visitQuery = useFetch('/home-visits', { page: 1, page_size: 100, volunteer_id: user?.id, status, start_date: start, end_date: end })
  const reportQuery = useFetch('/activity-reports', { page: 1, page_size: 100, volunteer_id: user?.id, start_date: start, end_date: end })
  const active = tab === 'visits' ? visitQuery : reportQuery
  const changeVisitStatus = async (visit, nextStatus) => {
    try { await api.patch(`/home-visits/${visit.id}`, { status: nextStatus }); await visitQuery.reload() } catch (e) { window.alert(e.response?.data?.detail || e.message) }
  }
  return <div className="space-y-4">
    <PageHeader title={t('My field records')} subtitle={t('Plan visits, record completed work and submit the daily activity report.')} actions={<><Button variant="secondary" icon={MapPin} onClick={() => setModal('visit')}>{t('Home visit')}</Button><Button icon={Plus} onClick={() => setModal('report')}>{t('Daily report')}</Button></>} />
    <Tabs tabs={[{ value: 'visits', label: t('Home visits') }, { value: 'reports', label: t('Daily reports') }]} value={tab} onChange={setTab} />
    {queue.length > 0 && <Card title={t('Offline submissions')} actions={<Button size="sm" variant="secondary" busy={syncingRef.current} onClick={() => syncQueue(true)}>{t('Retry sync')}</Button>}>
      <p className="mb-2 text-xs text-gray-500">{t('Field forms are stored on this device until they sync. Keep this account signed in and reconnect to upload them.')}</p>
      <div className="space-y-2">{queue.map((item) => <div key={item.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-gray-50 px-3 py-2 text-sm"><span>{t(item.label)} · {fmtDate(item.date)}</span><span className={item.error ? 'text-red-700' : 'text-amber-700'}>{item.error || t('Waiting to sync')}</span></div>)}</div>
    </Card>}
    <Card padded={false}>
      <div className="grid gap-2 border-b border-gray-100 p-3 sm:grid-cols-3"><Select options={['completed', 'planned', 'missed']} placeholder={t('Any visit status')} value={status} onChange={(e) => setStatus(e.target.value)} disabled={tab !== 'visits'} /><Field label={t('From')}><Input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></Field><Field label={t('To')}><Input type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></Field></div>
      <ErrorBox message={active.error} />
      {active.loading && !active.data ? <Spinner /> : tab === 'visits' ? <Table columns={[
        { key: 'visit_date', label: t('Date'), render: (r) => fmtDate(r.visit_date) },
        { key: 'purpose', label: t('Purpose'), render: (r) => humanize(r.purpose) },
        { key: 'girls', label: t('Girls'), render: (r) => r.girl_ids?.length || 0 },
        { key: 'status', label: t('Status'), render: (r) => <StatusBadge value={r.status} /> },
        { key: 'approval', label: t('Review'), render: (r) => <StatusBadge value={r.approval?.status} /> },
        { key: 'notes', label: t('Notes'), render: (r) => <span className="line-clamp-2">{r.observations || r.notes || '—'}</span> },
        { key: 'actions', label: '', render: (r) => <div className="flex flex-wrap gap-1">{r.status === 'planned' && <><Button size="sm" onClick={() => changeVisitStatus(r, 'completed')}>{t('Complete')}</Button><Button size="sm" variant="secondary" onClick={() => changeVisitStatus(r, 'missed')}>{t('Missed')}</Button></>}<Button size="sm" variant="ghost" icon={Camera} onClick={() => setPhotoVisit(r)}>{t('Attach photos')}</Button></div> },
      ]} rows={visitQuery.data?.items} empty={t('No home visits in this period.')} /> : <Table columns={[
        { key: 'report_date', label: t('Date'), render: (r) => fmtDate(r.report_date) },
        { key: 'activities', label: t('Activities'), render: (r) => (r.activities || []).map(humanize).join(', ') || '—' },
        { key: 'groups', label: t('Groups met'), render: (r) => r.group_ids?.length || 0 },
        { key: 'girls_present', label: t('Girls present') },
        { key: 'home_visits_count', label: t('Home visits') },
        { key: 'approval', label: t('Review'), render: (r) => <StatusBadge value={r.approval?.status} /> },
      ]} rows={reportQuery.data?.items} empty={t('No daily reports in this period.')} />}
    </Card>
    {modal === 'visit' && <VisitEditor user={user} submitRecord={submitRecord} onClose={() => setModal(null)} onSaved={() => { setModal(null); visitQuery.reload() }} />}
    {modal === 'report' && <DailyReportEditor user={user} submitRecord={submitRecord} onClose={() => setModal(null)} onSaved={() => { setModal(null); reportQuery.reload() }} />}
    {photoVisit && <PhotoUploadModal visit={photoVisit} onClose={() => setPhotoVisit(null)} onSaved={() => { setPhotoVisit(null); visitQuery.reload() }} />}
  </div>
}
