import { useCallback, useEffect, useState } from 'react'
import { Camera, Download, Edit2, Eye, MapPin, Plus, RefreshCw, Save } from 'lucide-react'
import * as XLSX from 'xlsx'
import api, { errorMessage } from '../lib/api'
import { Button, Card, ErrorBox, Modal, PageHeader, Spinner } from '../components/ui'
import { t } from '../lib/i18n'
import { todayISO } from '../lib/format'

const STATUSES = [
  { value: 'present', label: 'Present', badge: 'bg-emerald-50 text-emerald-700 ring-emerald-200', chip: 'border-emerald-500 bg-emerald-50 text-emerald-800' },
  { value: 'late', label: 'Late', badge: 'bg-amber-50 text-amber-700 ring-amber-200', chip: 'border-amber-500 bg-amber-50 text-amber-800' },
  { value: 'absent', label: 'Absent', badge: 'bg-red-50 text-red-700 ring-red-200', chip: 'border-red-500 bg-red-50 text-red-800' },
  { value: 'leave', label: 'Leave', badge: 'bg-sky-50 text-sky-700 ring-sky-200', chip: 'border-sky-500 bg-sky-50 text-sky-800' },
]

const HOURS = Array.from({ length: 12 }, (_, i) => String(i + 1).padStart(2, '0'))
const MINUTES = Array.from({ length: 60 }, (_, i) => String(i).padStart(2, '0'))

const today = () => todayISO()

// Times are stored and shown as "hh:mm AM/PM" (the NoteCam format). Older manual entries may be "HH:MM".
function parseTime(value) {
  if (!value) return null
  const match = String(value).trim().match(/^(\d{1,2}):(\d{2})(?::\d{2})?\s*([AaPp][Mm])?$/)
  if (!match) return null
  let hours = Number(match[1])
  const minutes = Number(match[2])
  const meridiem = match[3]?.toUpperCase()
  if (meridiem === 'PM' && hours < 12) hours += 12
  if (meridiem === 'AM' && hours === 12) hours = 0
  if (hours > 23 || minutes > 59) return null
  return { hours, minutes }
}

function to12h(value) {
  const parsed = parseTime(value)
  if (!parsed) return value || ''
  const { hours, minutes } = parsed
  return `${String(hours % 12 || 12).padStart(2, '0')}:${String(minutes).padStart(2, '0')} ${hours < 12 ? 'AM' : 'PM'}`
}

function isNoteCam(record) {
  return Boolean(
    record && (record.check_in_photo || record.check_out_photo || record.check_in_gps || record.check_out_gps
      || record.has_check_in_photo || record.has_check_out_photo),
  )
}

function makeRow(volunteer, existing) {
  const villageNames = volunteer.village_names?.length
    ? volunteer.village_names.join(', ')
    : (volunteer.village?.name || volunteer.village_name || '')

  return {
    volunteer_id: volunteer.id,
    name: volunteer.name || 'Unnamed Volunteer',
    village_name: existing?.village_name || villageNames || 'Not assigned',
    village_id: existing?.village_id || volunteer.village_id || null,
    status: existing?.status || '',
    check_in: to12h(existing?.check_in),
    check_out: to12h(existing?.check_out),
    noteCam: isNoteCam(existing),
    check_in_photo: existing?.check_in_photo || null,
    check_out_photo: existing?.check_out_photo || null,
    check_in_gps: existing?.check_in_gps || null,
    check_out_gps: existing?.check_out_gps || null,
    remarks: existing?.remarks || '',
    hasRecord: Boolean(existing),
  }
}

function StatusPill({ value }) {
  const status = STATUSES.find((item) => item.value === value)
  if (!status) {
    return <span className="inline-flex rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-500">{t('Not marked')}</span>
  }
  return (
    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${status.badge}`}>
      {t(status.label)}
    </span>
  )
}

/** 12-hour time picker. `value` is "hh:mm AM/PM" or ''. */
function TimeField12({ label, value, onChange, disabled }) {
  const parsed = parseTime(value)
  const hour = parsed ? String(parsed.hours % 12 || 12).padStart(2, '0') : ''
  const minute = parsed ? String(parsed.minutes).padStart(2, '0') : ''
  const period = parsed ? (parsed.hours < 12 ? 'AM' : 'PM') : 'AM'

  function emit(next) {
    const h = next.hour ?? hour
    if (!h) {
      onChange('')
      return
    }
    onChange(`${h}:${next.minute ?? (minute || '00')} ${next.period ?? period}`)
  }

  const selectClass = 'rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm disabled:bg-gray-100'

  return (
    <fieldset disabled={disabled}>
      <legend className="mb-1 text-sm font-medium text-gray-700">{label}</legend>
      <div className="flex items-center gap-1.5">
        <select aria-label={`${label} hour`} value={hour} onChange={(e) => emit({ hour: e.target.value })} className={selectClass}>
          <option value="">--</option>
          {HOURS.map((h) => <option key={h} value={h}>{h}</option>)}
        </select>
        <span className="text-gray-500">:</span>
        <select aria-label={`${label} minute`} value={minute} onChange={(e) => emit({ minute: e.target.value })} disabled={!hour} className={selectClass}>
          {!hour && <option value="">--</option>}
          {MINUTES.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <select aria-label={`${label} AM or PM`} value={period} onChange={(e) => emit({ period: e.target.value })} disabled={!hour} className={selectClass}>
          <option value="AM">AM</option>
          <option value="PM">PM</option>
        </select>
        {hour && (
          <button type="button" onClick={() => onChange('')} className="ml-1 text-xs font-medium text-gray-500 hover:text-gray-800">
            {t('Clear')}
          </button>
        )}
      </div>
    </fieldset>
  )
}

export default function VolunteerAttendance() {
  const [date, setDate] = useState(today())
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  // Manual marking happens in a modal, on a draft copy of the row
  const [draft, setDraft] = useState(null)
  const [draftError, setDraftError] = useState('')

  // Attendance photo preview
  const [previewPhoto, setPreviewPhoto] = useState(null)
  const [previewTitle, setPreviewTitle] = useState('')

  // Recent NoteCam check-ins across dates (without photos), so admins can find them on any day
  const [recent, setRecent] = useState([])
  const [recentLoading, setRecentLoading] = useState(true)

  const loadRecent = useCallback(async () => {
    setRecentLoading(true)
    try {
      const end = today()
      const startDate = new Date(`${end}T00:00:00`)
      startDate.setDate(startDate.getDate() - 30)
      const start = `${startDate.getFullYear()}-${String(startDate.getMonth() + 1).padStart(2, '0')}-${String(startDate.getDate()).padStart(2, '0')}`
      const res = await api.get('/attendance', {
        params: { start_date: start, end_date: end, include_photos: false },
      })
      const items = Array.isArray(res.data) ? res.data : res.data.items || []
      setRecent(items.filter(isNoteCam))
    } catch {
      setRecent([])
    } finally {
      setRecentLoading(false)
    }
  }, [])

  useEffect(() => {
    loadRecent()
  }, [loadRecent])

  // The recent list is loaded without images; fetch the one record's photo on demand.
  const [photoLoadingKey, setPhotoLoadingKey] = useState('')

  async function openRecordPhoto(record, kind) {
    const recordDate = String(record.attendance_date || '').slice(0, 10)
    const key = `${record.id}-${kind}`
    setPhotoLoadingKey(key)
    setError('')
    try {
      const res = await api.get('/attendance', {
        params: { start_date: recordDate, end_date: recordDate, volunteer_id: record.volunteer_id },
      })
      const items = Array.isArray(res.data) ? res.data : res.data.items || []
      const full = items.find((item) => item.id === record.id) || items[0]
      const photo = full?.[kind === 'in' ? 'check_in_photo' : 'check_out_photo']
      if (!photo) {
        setError(t('Photo not found for this record.'))
        return
      }
      const time = to12h(kind === 'in' ? record.check_in : record.check_out)
      setPreviewPhoto(photo)
      setPreviewTitle(`${record.volunteer_name || ''} - ${kind === 'in' ? t('Check-in photo') : t('Check-out photo')} (${recordDate}${time ? `, ${time}` : ''})`)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setPhotoLoadingKey('')
    }
  }

  function renderPhotoButton(record, kind) {
    const has = kind === 'in' ? record.has_check_in_photo : record.has_check_out_photo
    if (!has) return null
    const loadingThis = photoLoadingKey === `${record.id}-${kind}`
    return (
      <button
        type="button"
        onClick={() => openRecordPhoto(record, kind)}
        disabled={Boolean(photoLoadingKey)}
        className={`ml-2 inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-semibold disabled:opacity-60 ${
          kind === 'in'
            ? 'border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100'
            : 'border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100'
        }`}
      >
        <Camera className="h-3 w-3" />
        {loadingThis ? t('Loading…') : t('View photo')}
      </button>
    )
  }

  function renderRowPhoto(row, kind) {
    const photo = kind === 'in' ? row.check_in_photo : row.check_out_photo
    if (!photo) return null
    const time = kind === 'in' ? row.check_in : row.check_out
    const label = kind === 'in' ? t('Check-in photo') : t('Check-out photo')
    return (
      <button
        type="button"
        onClick={() => {
          setPreviewPhoto(photo)
          setPreviewTitle(`${row.name} - ${label}${time ? ` (${time})` : ''}`)
        }}
        title={label}
        className={`mt-2 block overflow-hidden rounded-lg border hover:ring-2 ${
          kind === 'in' ? 'border-emerald-300 hover:ring-emerald-300' : 'border-amber-300 hover:ring-amber-300'
        }`}
      >
        <img src={photo} alt={label} className="h-14 w-20 object-cover" loading="lazy" />
      </button>
    )
  }

  function renderGps(gps) {
    if (!gps || typeof gps.lat !== 'number' || typeof gps.lng !== 'number') return null
    return (
      <div className="mt-1 text-[11px] text-gray-500">
        📍 {gps.lat.toFixed(4)}°, {gps.lng.toFixed(4)}°
      </div>
    )
  }

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    setMessage('')

    try {
      const [volunteerResponse, attendanceResponse] = await Promise.all([
        api.get('/users', {
          params: {
            role: 'volunteer',
            is_active: true,
            page: 1,
            page_size: 500,
          },
        }),
        api.get('/attendance', {
          params: { start_date: date, end_date: date },
        }),
      ])

      const volunteers = volunteerResponse.data.items || []
      const attendance = Array.isArray(attendanceResponse.data)
        ? attendanceResponse.data
        : attendanceResponse.data.items || []

      const existingByVolunteer = new Map(
        attendance.map((record) => [String(record.volunteer_id), record]),
      )

      const volunteerIds = new Set(volunteers.map((volunteer) => String(volunteer.id)))
      // Records from users not in the active-volunteer list (inactive volunteers, admins who
      // checked in with NoteCam) would otherwise be invisible on the register.
      const orphanRows = attendance
        .filter((record) => !volunteerIds.has(String(record.volunteer_id)))
        .map((record) =>
          makeRow(
            { id: String(record.volunteer_id), name: record.volunteer_name, village_id: record.village_id },
            record,
          ),
        )

      setRows([
        ...volunteers.map((volunteer) =>
          makeRow(volunteer, existingByVolunteer.get(String(volunteer.id))),
        ),
        ...orphanRows,
      ])
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [date])

  useEffect(() => {
    load()
  }, [load])

  function openEditor(row) {
    setDraft({ ...row })
    setDraftError('')
    setMessage('')
  }

  function closeEditor() {
    if (!saving) setDraft(null)
  }

  async function saveDraft() {
    if (!draft) return
    if (!draft.status) {
      setDraftError(t('Select an attendance status before saving.'))
      return
    }

    setSaving(true)
    setDraftError('')

    try {
      await api.post('/attendance/batch', {
        entries: [
          {
            volunteer_id: draft.volunteer_id,
            attendance_date: date,
            status: draft.status,
            check_in: draft.check_in || null,
            check_out: draft.check_out || null,
            village_id: draft.village_id || null,
            village_name: draft.village_name || null,
            check_in_photo: draft.check_in_photo || null,
            check_out_photo: draft.check_out_photo || null,
            check_in_gps: draft.check_in_gps || null,
            check_out_gps: draft.check_out_gps || null,
            remarks: draft.remarks.trim() || null,
          },
        ],
      })

      setRows((current) =>
        current.map((item) =>
          item.volunteer_id === draft.volunteer_id
            ? { ...draft, remarks: draft.remarks.trim(), hasRecord: true }
            : item,
        ),
      )
      setDraft(null)
      setMessage(t('Attendance saved successfully.'))
    } catch (err) {
      setDraftError(errorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  function exportExcel() {
    const workbook = XLSX.utils.book_new()
    const data = rows.map((row) => ({
      Date: date,
      'Volunteer Name': row.name,
      Village: row.village_name || 'Not assigned',
      Status: STATUSES.find((item) => item.value === row.status)?.label || 'Not recorded',
      'Check-in': row.check_in || '',
      'Check-out': row.check_out || '',
      'GPS Check-in': row.check_in_gps ? `${row.check_in_gps.lat}, ${row.check_in_gps.lng}` : '',
      'GPS Check-out': row.check_out_gps ? `${row.check_out_gps.lat}, ${row.check_out_gps.lng}` : '',
      'Photo': row.check_in_photo ? 'Yes' : 'No',
      Remarks: row.remarks || '',
      Saved: row.hasRecord ? 'Yes' : 'No',
    }))

    const worksheet = XLSX.utils.json_to_sheet(data)
    worksheet['!cols'] = [
      { wch: 14 },
      { wch: 28 },
      { wch: 24 },
      { wch: 18 },
      { wch: 14 },
      { wch: 14 },
      { wch: 24 },
      { wch: 24 },
      { wch: 20 },
      { wch: 40 },
      { wch: 12 },
    ]
    XLSX.utils.book_append_sheet(workbook, worksheet, 'Attendance')
    XLSX.writeFile(workbook, `KVP_Tai_Attendance_${date}.xlsx`)
  }

  const recordedCount = rows.filter((row) => row.hasRecord).length

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('Volunteer attendance register')}
        subtitle={t('Daily check-in and check-out tracking with GPS photos.')}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="secondary" onClick={exportExcel} disabled={loading || rows.length === 0}>
              <Download className="mr-2 h-4 w-4" />
              {t('Export to Excel')}
            </Button>
            <Button variant="secondary" onClick={() => { load(); loadRecent() }} disabled={loading}>
              <RefreshCw className="mr-2 h-4 w-4" />
              {t('Refresh')}
            </Button>
          </div>
        }
      />

      <ErrorBox message={error} />

      {message && (
        <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          {message}
        </p>
      )}

      <Card
        title={t('Daily register')}
        actions={
          <label className="flex items-center gap-2 text-sm font-medium">
            <span className="text-gray-600">{t('Attendance date')}</span>
            <input
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium shadow-sm focus:border-brand-500 focus:outline-none"
            />
          </label>
        }
      >
        <div className="mb-4 flex flex-wrap gap-4 text-sm text-gray-600">
          <span>{t('Total Volunteers')}: <strong>{rows.length}</strong></span>
          <span>{t('Recorded')}: <strong>{recordedCount}</strong></span>
          <span>{t('Pending')}: <strong>{rows.length - recordedCount}</strong></span>
        </div>

        {loading ? (
          <Spinner />
        ) : rows.length === 0 ? (
          <p className="py-8 text-center text-sm text-gray-500">
            {t('No active Volunteers found.')}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-sm">
              <thead>
                <tr className="border-b bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                  <th className="p-3">{t('Volunteer')}</th>
                  <th className="p-3">{t('Status')}</th>
                  <th className="p-3">{t('Check-in')}</th>
                  <th className="p-3">{t('Check-out')}</th>
                  <th className="p-3">{t('Remarks')}</th>
                  <th className="p-3 text-right">{t('Actions')}</th>
                </tr>
              </thead>

              <tbody>
                {rows.map((row) => (
                  <tr key={row.volunteer_id} className="border-b last:border-0 hover:bg-gray-50/70">
                    <td className="p-3 align-top">
                      <div className="font-semibold text-gray-900">{row.name}</div>
                      <div className="mt-1 flex items-center gap-1 text-xs text-gray-600">
                        <MapPin className="h-3.5 w-3.5 text-brand-700 shrink-0" />
                        <span>{row.village_name}</span>
                      </div>
                      {row.noteCam && (
                        <span className="mt-1.5 inline-flex items-center gap-1 rounded-full bg-sky-50 px-2 py-0.5 text-[11px] font-semibold text-sky-700">
                          <Camera className="h-3 w-3" />
                          NoteCam
                        </span>
                      )}
                    </td>

                    <td className="p-3 align-top">
                      <StatusPill value={row.status} />
                    </td>

                    <td className="p-3 align-top">
                      <div className="font-medium text-gray-900 whitespace-nowrap">{row.check_in || <span className="text-gray-400">—</span>}</div>
                      {renderRowPhoto(row, 'in')}
                      {renderGps(row.check_in_gps)}
                    </td>

                    <td className="p-3 align-top">
                      <div className="font-medium text-gray-900 whitespace-nowrap">{row.check_out || <span className="text-gray-400">—</span>}</div>
                      {renderRowPhoto(row, 'out')}
                      {renderGps(row.check_out_gps)}
                    </td>

                    <td className="p-3 align-top">
                      {row.remarks
                        ? <p className="max-w-[14rem] whitespace-pre-line text-xs text-gray-700">{row.remarks}</p>
                        : <span className="text-gray-400">—</span>}
                    </td>

                    <td className="p-3 align-top text-right">
                      {row.hasRecord ? (
                        <Button size="sm" variant="secondary" onClick={() => openEditor(row)}>
                          <Edit2 className="mr-1.5 h-3.5 w-3.5" />
                          {t('Edit')}
                        </Button>
                      ) : (
                        <Button size="sm" variant="secondary" onClick={() => openEditor(row)}>
                          <Plus className="mr-1.5 h-3.5 w-3.5" />
                          {t('Mark attendance')}
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title={t('Recent NoteCam check-ins (last 30 days)')}>
        {recentLoading ? (
          <Spinner />
        ) : recent.length === 0 ? (
          <p className="py-4 text-center text-sm text-gray-500">{t('No NoteCam check-ins in the last 30 days.')}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="border-b bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                  <th className="p-2">{t('Date')}</th>
                  <th className="p-2">{t('Volunteer')}</th>
                  <th className="p-2">{t('Village')}</th>
                  <th className="p-2">{t('Check-in')}</th>
                  <th className="p-2">{t('Check-out')}</th>
                  <th className="p-2" />
                </tr>
              </thead>
              <tbody>
                {recent.map((record) => {
                  const recordDate = String(record.attendance_date || '').slice(0, 10)
                  const active = recordDate === date
                  return (
                    <tr key={record.id} className={`border-b last:border-0 ${active ? 'bg-brand-50/60' : 'hover:bg-gray-50/70'}`}>
                      <td className="p-2 whitespace-nowrap">{recordDate}</td>
                      <td className="p-2 font-medium text-gray-900">{record.volunteer_name || '—'}</td>
                      <td className="p-2 text-gray-600">{record.village_name || '—'}</td>
                      <td className="p-2 whitespace-nowrap">
                        {to12h(record.check_in) || '—'}
                        {renderPhotoButton(record, 'in')}
                      </td>
                      <td className="p-2 whitespace-nowrap">
                        {to12h(record.check_out) || '—'}
                        {renderPhotoButton(record, 'out')}
                      </td>
                      <td className="p-2 text-right">
                        <Button size="sm" variant="secondary" onClick={() => setDate(recordDate)} disabled={active}>
                          <Eye className="mr-1 h-3.5 w-3.5" />
                          {active ? t('Showing') : t('Open day')}
                        </Button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Manual attendance marking */}
      {draft && (
        <Modal
          open={Boolean(draft)}
          onClose={closeEditor}
          title={`${draft.hasRecord ? t('Edit attendance') : t('Mark attendance')} – ${draft.name}`}
          footer={
            <>
              <Button variant="secondary" onClick={closeEditor} disabled={saving}>{t('Cancel')}</Button>
              <Button onClick={saveDraft} disabled={saving || !draft.status}>
                <Save className="mr-1.5 h-4 w-4" />
                {saving ? t('Saving…') : t('Save')}
              </Button>
            </>
          }
        >
          <div className="space-y-5">
            <p className="text-sm text-gray-600">
              {date} · {draft.village_name}
              {draft.noteCam && <span className="ml-2 text-xs font-semibold text-sky-700">({t('NoteCam photos and GPS are kept')})</span>}
            </p>

            <ErrorBox message={draftError} />

            <fieldset disabled={saving}>
              <legend className="mb-2 text-sm font-medium text-gray-700">{t('Attendance status')}</legend>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {STATUSES.map((item) => {
                  const selected = draft.status === item.value
                  return (
                    <label
                      key={item.value}
                      className={`cursor-pointer rounded-lg border-2 px-3 py-2 text-center text-sm font-medium transition ${
                        selected ? item.chip : 'border-gray-200 text-gray-600 hover:border-gray-300'
                      }`}
                    >
                      <input
                        type="radio"
                        name="attendance-status"
                        value={item.value}
                        checked={selected}
                        onChange={() => setDraft((d) => ({ ...d, status: item.value }))}
                        className="sr-only"
                      />
                      {t(item.label)}
                    </label>
                  )
                })}
              </div>
            </fieldset>

            <div className="grid gap-4 sm:grid-cols-2">
              <TimeField12
                label={t('Check-in time')}
                value={draft.check_in}
                onChange={(value) => setDraft((d) => ({ ...d, check_in: value }))}
                disabled={saving}
              />
              <TimeField12
                label={t('Check-out time')}
                value={draft.check_out}
                onChange={(value) => setDraft((d) => ({ ...d, check_out: value }))}
                disabled={saving}
              />
            </div>

            <label className="block">
              <span className="mb-1 block text-sm font-medium text-gray-700">{t('Remarks')}</span>
              <textarea
                value={draft.remarks}
                disabled={saving}
                onChange={(event) => setDraft((d) => ({ ...d, remarks: event.target.value }))}
                maxLength={1000}
                rows={3}
                placeholder={t('Optional')}
                className="w-full resize-y rounded-md border border-gray-300 p-2 text-sm disabled:bg-gray-100"
              />
            </label>
          </div>
        </Modal>
      )}

      {/* Attendance photo preview */}
      {previewPhoto && (
        <Modal
          open={Boolean(previewPhoto)}
          onClose={() => setPreviewPhoto(null)}
          title={previewTitle || t('Attendance photo')}
          footer={<Button onClick={() => setPreviewPhoto(null)}>{t('Close')}</Button>}
        >
          <div className="overflow-hidden rounded-xl bg-black">
            <img src={previewPhoto} alt="Attendance photo" className="w-full max-h-[75vh] object-contain mx-auto" />
          </div>
        </Modal>
      )}

    </div>
  )
}
