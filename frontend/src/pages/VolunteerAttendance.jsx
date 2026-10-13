
import { useCallback, useEffect, useState } from 'react'
import { Download, Edit2, Save, X, RefreshCw } from 'lucide-react'
import * as XLSX from 'xlsx'
import api, { errorMessage } from '../lib/api'
import { Button, Card, ErrorBox, PageHeader, Spinner } from '../components/ui'

const STATUSES = [
  { value: 'present', label: 'Present' },
  { value: 'absent', label: 'Absent' },
  { value: 'late', label: 'Late' },
  { value: 'leave', label: 'Leave' },
]

function today() {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000)
  return local.toISOString().slice(0, 10)
}

function makeRow(volunteer, existing) {
  return {
    volunteer_id: volunteer.id,
    name: volunteer.name || 'Unnamed volunteer',
    village_name:
      volunteer.village?.name ||
      volunteer.village_name ||
      '',
    status: existing?.status || '',
    check_in: existing?.check_in || '',
    check_out: existing?.check_out || '',
    remarks: existing?.remarks || '',
    hasRecord: Boolean(existing),
    editing: !existing,
  }
}

export default function VolunteerAttendance() {
  const [date, setDate] = useState(today())
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState(null)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

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
        attendance.map((record) => [
          String(record.volunteer_id),
          record,
        ]),
      )

      setRows(
        volunteers.map((volunteer) =>
          makeRow(
            volunteer,
            existingByVolunteer.get(String(volunteer.id)),
          ),
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
        row.volunteer_id === volunteerId
          ? { ...row, [field]: value }
          : row,
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
      const response = await api.post('/attendance/batch', {
        entries: [
          {
            volunteer_id: row.volunteer_id,
            attendance_date: date,
            status: row.status,
            check_in: row.check_in || null,
            check_out: row.check_out || null,
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

    // Reload saved data so unsaved edits are discarded.
    load()
  }

  function exportExcel() {
    const workbook = XLSX.utils.book_new()

    const data = rows.map((row) => ({
      Date: date,
      Volunteer: row.name,
      Village: row.village_name || 'Not assigned',
      Status:
        STATUSES.find((item) => item.value === row.status)?.label ||
        'Not recorded',
      'Check-in': row.check_in || '',
      'Check-out': row.check_out || '',
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
      { wch: 40 },
      { wch: 12 },
    ]

    XLSX.utils.book_append_sheet(workbook, worksheet, 'Attendance')
    XLSX.writeFile(workbook, `KVP-Attendance-${date}.xlsx`)
  }

  const recordedCount = rows.filter((row) => row.hasRecord).length

  return (
    <div className="space-y-5">
      <PageHeader
        title="Volunteer attendance"
        subtitle="Record and manage daily attendance for active volunteers."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={exportExcel} disabled={!rows.length}>
              <Download className="mr-2 h-4 w-4" />
              Export Excel
            </Button>

            <Button variant="secondary" onClick={load} disabled={loading}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Refresh
            </Button>
          </div>
        }
      />

      <ErrorBox message={error} />

      {message && (
        <p
          role="status"
          className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800"
        >
          {message}
        </p>
      )}

      <Card
        title="Daily register"
        actions={
          <label className="flex items-center gap-2 text-sm">
            <span className="text-gray-600">Attendance date</span>
            <input
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
              className="rounded-lg border border-gray-300 px-2 py-1.5"
            />
          </label>
        }
      >
        <div className="mb-4 flex flex-wrap gap-3 text-sm text-gray-600">
          <span>
            Volunteers: <strong>{rows.length}</strong>
          </span>
          <span>
            Saved records: <strong>{recordedCount}</strong>
          </span>
          <span>
            Pending records: <strong>{rows.length - recordedCount}</strong>
          </span>
        </div>

        {loading ? (
          <Spinner />
        ) : rows.length === 0 ? (
          <p className="py-8 text-center text-sm text-gray-500">
            No active volunteers found.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[950px] text-left text-sm">
              <thead>
                <tr className="border-b bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
                  <th className="p-3">Volunteer</th>
                  <th className="p-3">Attendance status</th>
                  <th className="p-3">Check-in</th>
                  <th className="p-3">Check-out</th>
                  <th className="p-3">Remarks</th>
                  <th className="p-3">Actions</th>
                </tr>
              </thead>

              <tbody>
                {rows.map((row) => {
                  const rowSaving = savingId === row.volunteer_id

                  return (
                    <tr
                      key={row.volunteer_id}
                      className="border-b last:border-0 hover:bg-gray-50/70"
                    >
                      <td className="p-3 align-top">
                        <div className="font-medium text-gray-900">
                          {row.name}
                        </div>
                        <div className="mt-1 text-xs text-gray-500">
                          {row.village_name || 'No village assigned'}
                        </div>
                        {row.hasRecord && (
                          <span className="mt-2 inline-block rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700">
                            Saved
                          </span>
                        )}
                      </td>

                      <td className="p-3 align-top">
                        <fieldset disabled={!row.editing || rowSaving}>
                          <legend className="sr-only">
                            Attendance status for {row.name}
                          </legend>

                          <div className="space-y-2">
                            {STATUSES.map((item) => (
                              <label
                                key={item.value}
                                className={`flex items-center gap-2 rounded-md px-2 py-1 ${
                                  row.editing
                                    ? 'cursor-pointer hover:bg-gray-100'
                                    : 'cursor-default'
                                }`}
                              >
                                <input
                                  type="radio"
                                  name={`attendance-${row.volunteer_id}`}
                                  value={item.value}
                                  checked={row.status === item.value}
                                  onChange={() =>
                                    updateRow(
                                      row.volunteer_id,
                                      'status',
                                      item.value,
                                    )
                                  }
                                  className="h-4 w-4 accent-blue-700"
                                />
                                <span
                                  className={
                                    row.status === item.value
                                      ? 'font-medium text-gray-900'
                                      : 'text-gray-600'
                                  }
                                >
                                  {item.label}
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
                          onChange={(event) =>
                            updateRow(
                              row.volunteer_id,
                              'check_in',
                              event.target.value,
                            )
                          }
                          className="w-28 rounded-md border border-gray-300 p-2 text-sm disabled:bg-gray-100 disabled:text-gray-500"
                        />
                      </td>

                      <td className="p-3 align-top">
                        <input
                          type="time"
                          aria-label={`Check-out time for ${row.name}`}
                          value={row.check_out}
                          disabled={!row.editing || rowSaving}
                          onChange={(event) =>
                            updateRow(
                              row.volunteer_id,
                              'check_out',
                              event.target.value,
                            )
                          }
                          className="w-28 rounded-md border border-gray-300 p-2 text-sm disabled:bg-gray-100 disabled:text-gray-500"
                        />
                      </td>

                      <td className="p-3 align-top">
                        <textarea
                          aria-label={`Remarks for ${row.name}`}
                          value={row.remarks}
                          disabled={!row.editing || rowSaving}
                          onChange={(event) =>
                            updateRow(
                              row.volunteer_id,
                              'remarks',
                              event.target.value,
                            )
                          }
                          maxLength={1000}
                          rows={2}
                          placeholder="Optional"
                          className="w-40 resize-y rounded-md border border-gray-300 p-2 text-sm disabled:bg-gray-100 disabled:text-gray-500"
                        />
                      </td>

                      <td className="p-3 align-top">
                        {row.editing ? (
                          <div className="flex flex-col gap-2">
                            <Button
                              onClick={() => saveRow(row)}
                              disabled={rowSaving || !row.status}
                            >
                              <Save className="mr-2 h-4 w-4" />
                              {rowSaving ? 'Saving…' : 'Save'}
                            </Button>

                            {row.hasRecord && (
                              <Button
                                variant="secondary"
                                onClick={() => cancelEdit(row)}
                                disabled={rowSaving}
                              >
                                <X className="mr-2 h-4 w-4" />
                                Cancel
                              </Button>
                            )}
                          </div>
                        ) : (
                          <Button
                            variant="secondary"
                            onClick={() =>
                              updateRow(row.volunteer_id, 'editing', true)
                            }
                            disabled={savingId !== null}
                          >
                            <Edit2 className="mr-2 h-4 w-4" />
                            Edit
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
    </div>
  )
}
