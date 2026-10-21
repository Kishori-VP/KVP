import { useCallback, useEffect, useState } from 'react'
import { Camera, Download, Edit2, Eye, MapPin, RefreshCw, Save, X } from 'lucide-react'
import * as XLSX from 'xlsx'
import api, { errorMessage } from '../lib/api'
import { Button, Card, ErrorBox, Modal, PageHeader, Spinner, StatusBadge } from '../components/ui'
import { t } from '../lib/i18n'
import { todayISO } from '../lib/format'
import NoteCamModal from '../components/NoteCamModal'
import { useAuth } from '../lib/auth'

const STATUSES = [
  { value: 'present', label: 'Present' },
  { value: 'absent', label: 'Absent' },
  { value: 'late', label: 'Late' },
  { value: 'leave', label: 'Leave' },
]

const today = () => todayISO()

function makeRow(volunteer, existing) {
  const villageNames = volunteer.village_names?.length
    ? volunteer.village_names.join(', ')
    : (volunteer.village?.name || volunteer.village_name || '')

  return {
    volunteer_id: volunteer.id,
    name: volunteer.name || 'Unnamed Tai',
    village_name: existing?.village_name || villageNames || 'Not assigned',
    village_id: existing?.village_id || volunteer.village_id || null,
    status: existing?.status || '',
    check_in: existing?.check_in || '',
    check_out: existing?.check_out || '',
    check_in_photo: existing?.check_in_photo || null,
    check_out_photo: existing?.check_out_photo || null,
    check_in_gps: existing?.check_in_gps || null,
    check_out_gps: existing?.check_out_gps || null,
    remarks: existing?.remarks || '',
    hasRecord: Boolean(existing),
    editing: !existing,
  }
}

export default function VolunteerAttendance() {
  const { user } = useAuth()
  const [date, setDate] = useState(today())
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  // NoteCam photo preview modal
  const [previewPhoto, setPreviewPhoto] = useState(null)
  const [previewTitle, setPreviewTitle] = useState('')

  // Admin NoteCam capture modal
  const [noteCamOpen, setNoteCamOpen] = useState(false)
  const [noteCamAction, setNoteCamAction] = useState('CHECK-IN')

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

      setRows(
        volunteers.map((volunteer) =>
          makeRow(volunteer, existingByVolunteer.get(String(volunteer.id))),
        ),
      )
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setLoading(false)
    }
  }, [date])

  useEffect(() => {
    load()
  }, [load])

  function updateRow(volunteerId, field, value) {
    setRows((current) =>
      current.map((row) =>
        row.volunteer_id === volunteerId ? { ...row, [field]: value } : row,
      ),
    )
  }

  async function saveRow(row) {
    if (!row.status) {
      setError(`Select an attendance status for ${row.name} before saving.`)
      return
    }

    setSavingId(row.volunteer_id)
    setError('')
    setMessage('')

    try {
      await api.post('/attendance/batch', {
        entries: [
          {
            volunteer_id: row.volunteer_id,
            attendance_date: date,
            status: row.status,
            check_in: row.check_in || null,
            check_out: row.check_out || null,
            village_id: row.village_id || null,
            village_name: row.village_name || null,
            check_in_photo: row.check_in_photo || null,
            check_out_photo: row.check_out_photo || null,
            remarks: row.remarks.trim() || null,
          },
        ],
      })

      setRows((current) =>
        current.map((item) =>
          item.volunteer_id === row.volunteer_id
            ? { ...item, editing: false, hasRecord: true }
            : item,
        ),
      )

      setMessage(`Attendance saved for ${row.name}.`)
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSavingId(null)
    }
  }

  function cancelEdit(row) {
    if (!row.hasRecord) {
      setRows((current) =>
        current.map((item) =>
          item.volunteer_id === row.volunteer_id
            ? {
                ...item,
                status: '',
                check_in: '',
                check_out: '',
                remarks: '',
                editing: true,
              }
            : item,
        ),
      )
      setError('')
      return
    }
    load()
  }

  function exportExcel() {
    const workbook = XLSX.utils.book_new()
    const data = rows.map((row) => ({
      Date: date,
      'Tai Name': row.name,
      Village: row.village_name || 'Not assigned',
      Status: STATUSES.find((item) => item.value === row.status)?.label || 'Not recorded',
      'Check-in': row.check_in || '',
      'Check-out': row.check_out || '',
      'GPS Check-in': row.check_in_gps ? `${row.check_in_gps.lat}, ${row.check_in_gps.lng}` : '',
      'GPS Check-out': row.check_out_gps ? `${row.check_out_gps.lat}, ${row.check_out_gps.lng}` : '',
      'NoteCam Stamped Photo': row.check_in_photo ? 'Yes' : 'No',
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
        title={t('Tai attendance register')}
        subtitle={t('Daily check-in and check-out tracking with NoteCam GPS photos.')}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              onClick={() => {
                setNoteCamAction('CHECK-IN')
                setNoteCamOpen(true)
              }}
              className="bg-emerald-50 text-emerald-800 hover:bg-emerald-100 border-emerald-300"
            >
              <Camera className="mr-2 h-4 w-4 text-emerald-700" />
              {t('NoteCam Check-In')}
            </Button>
            <Button variant="secondary" onClick={exportExcel} disabled={loading || rows.length === 0}>
              <Download className="mr-2 h-4 w-4" />
              {t('Export to Excel')}
            </Button>
            <Button variant="secondary" onClick={load} disabled={loading}>
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
          <span>{t('Total Tais')}: <strong>{rows.length}</strong></span>
          <span>{t('Recorded')}: <strong>{recordedCount}</strong></span>
          <span>{t('Pending')}: <strong>{rows.length - recordedCount}</strong></span>
        </div>

        {loading ? (
          <Spinner />
        ) : rows.length === 0 ? (
          <p className="py-8 text-center text-sm text-gray-500">
            {t('No active Tais found.')}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px] text-left text-sm">
              <thead>
                <tr className="border-b bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                  <th className="p-3">{t('Tai')}</th>
                  <th className="p-3">{t('Attendance status')}</th>
                  <th className="p-3">{t('Check-in & Photo')}</th>
                  <th className="p-3">{t('Check-out & Photo')}</th>
                  <th className="p-3">{t('Remarks')}</th>
                  <th className="p-3">{t('Actions')}</th>
                </tr>
              </thead>

              <tbody>
                {rows.map((row) => {
                  const rowSaving = savingId === row.volunteer_id

                  return (
                    <tr key={row.volunteer_id} className="border-b last:border-0 hover:bg-gray-50/70">
                      <td className="p-3 align-top">
                        <div className="font-semibold text-gray-900">{row.name}</div>
                        <div className="mt-1 flex items-center gap-1 text-xs text-gray-600">
                          <MapPin className="h-3.5 w-3.5 text-brand-700 shrink-0" />
                          <span>{row.village_name}</span>
                        </div>
                        {row.hasRecord && (
                          <span className="mt-1.5 inline-block rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
                            {t('Saved')}
                          </span>
                        )}
                      </td>

                      <td className="p-3 align-top">
                        <fieldset disabled={!row.editing || rowSaving}>
                          <legend className="sr-only">Attendance status for {row.name}</legend>
                          <div className="space-y-1.5">
                            {STATUSES.map((item) => (
                              <label
                                key={item.value}
                                className={`flex items-center gap-2 rounded-md px-2 py-0.5 ${
                                  row.editing ? 'cursor-pointer hover:bg-gray-100' : 'cursor-default'
                                }`}
                              >
                                <input
                                  type="radio"
                                  name={`attendance-${row.volunteer_id}`}
                                  value={item.value}
                                  checked={row.status === item.value}
                                  onChange={() => updateRow(row.volunteer_id, 'status', item.value)}
                                  className="h-4 w-4 accent-brand-700"
                                />
                                <span className={row.status === item.value ? 'font-medium text-gray-900' : 'text-gray-600'}>
                                  {t(item.label)}
                                </span>
                              </label>
                            ))}
                          </div>
                        </fieldset>
                      </td>

                      <td className="p-3 align-top">
                        <input
                          type="time"
                          aria-label={`Check-in time for ${row.name}`}
                          value={row.check_in}
                          disabled={!row.editing || rowSaving}
                          onChange={(event) => updateRow(row.volunteer_id, 'check_in', event.target.value)}
                          className="w-28 rounded-md border border-gray-300 p-1.5 text-sm disabled:bg-gray-100 disabled:text-gray-500"
                        />
                        {row.check_in_photo && (
                          <button
                            type="button"
                            onClick={() => {
                              setPreviewPhoto(row.check_in_photo)
                              setPreviewTitle(`${row.name} - NoteCam Check-In Photo (${row.check_in})`)
                            }}
                            className="mt-2 flex items-center gap-1.5 rounded-lg border border-emerald-300 bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-800 hover:bg-emerald-100"
                          >
                            <Camera className="h-3.5 w-3.5" />
                            <span>{t('View NoteCam Photo')}</span>
                          </button>
                        )}
                        {row.check_in_gps && (
                          <div className="mt-1 text-[11px] text-gray-500">
                            📍 {row.check_in_gps.lat?.toFixed(4)}°, {row.check_in_gps.lng?.toFixed(4)}°
                          </div>
                        )}
                      </td>

                      <td className="p-3 align-top">
                        <input
                          type="time"
                          aria-label={`Check-out time for ${row.name}`}
                          value={row.check_out}
                          disabled={!row.editing || rowSaving}
                          onChange={(event) => updateRow(row.volunteer_id, 'check_out', event.target.value)}
                          className="w-28 rounded-md border border-gray-300 p-1.5 text-sm disabled:bg-gray-100 disabled:text-gray-500"
                        />
                        {row.check_out_photo && (
                          <button
                            type="button"
                            onClick={() => {
                              setPreviewPhoto(row.check_out_photo)
                              setPreviewTitle(`${row.name} - NoteCam Check-Out Photo (${row.check_out})`)
                            }}
                            className="mt-2 flex items-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-800 hover:bg-amber-100"
                          >
                            <Camera className="h-3.5 w-3.5" />
                            <span>{t('View NoteCam Photo')}</span>
                          </button>
                        )}
                        {row.check_out_gps && (
                          <div className="mt-1 text-[11px] text-gray-500">
                            📍 {row.check_out_gps.lat?.toFixed(4)}°, {row.check_out_gps.lng?.toFixed(4)}°
                          </div>
                        )}
                      </td>

                      <td className="p-3 align-top">
                        <textarea
                          aria-label={`Remarks for ${row.name}`}
                          value={row.remarks}
                          disabled={!row.editing || rowSaving}
                          onChange={(event) => updateRow(row.volunteer_id, 'remarks', event.target.value)}
                          maxLength={1000}
                          rows={2}
                          placeholder={t('Optional')}
                          className="w-40 resize-y rounded-md border border-gray-300 p-1.5 text-xs disabled:bg-gray-100 disabled:text-gray-500"
                        />
                      </td>

                      <td className="p-3 align-top">
                        {row.editing ? (
                          <div className="flex flex-col gap-1.5">
                            <Button size="sm" onClick={() => saveRow(row)} disabled={rowSaving || !row.status}>
                              <Save className="mr-1 h-3.5 w-3.5" />
                              {rowSaving ? t('Saving…') : t('Save')}
                            </Button>
                            {row.hasRecord && (
                              <Button size="sm" variant="secondary" onClick={() => cancelEdit(row)} disabled={rowSaving}>
                                <X className="mr-1 h-3.5 w-3.5" />
                                {t('Cancel')}
                              </Button>
                            )}
                          </div>
                        ) : (
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => updateRow(row.volunteer_id, 'editing', true)}
                            disabled={savingId !== null}
                          >
                            <Edit2 className="mr-1.5 h-3.5 w-3.5" />
                            {t('Edit')}
                          </Button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* NoteCam Photo Lightbox Preview Modal */}
      {previewPhoto && (
        <Modal
          open={Boolean(previewPhoto)}
          onClose={() => setPreviewPhoto(null)}
          title={previewTitle || t('NoteCam Attendance Photo')}
          footer={<Button onClick={() => setPreviewPhoto(null)}>{t('Close')}</Button>}
        >
          <div className="overflow-hidden rounded-xl bg-black">
            <img src={previewPhoto} alt="NoteCam GPS capture" className="w-full max-h-[75vh] object-contain mx-auto" />
          </div>
        </Modal>
      )}

      {/* Admin NoteCam Attendance Modal */}
      <NoteCamModal
        open={noteCamOpen}
        onClose={() => setNoteCamOpen(false)}
        action={noteCamAction}
        user={user}
        villages={[]}
        onSuccess={() => load()}
      />
    </div>
  )
}
