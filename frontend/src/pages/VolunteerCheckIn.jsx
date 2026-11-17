import { Camera, CheckCircle2, Clock, MapPin, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Button, Card, ErrorBox, PageHeader, Spinner } from '../components/ui'
import NoteCamModal from '../components/NoteCamModal'
import api from '../lib/api'
import { useAuth } from '../lib/auth'
import { fmtDate } from '../lib/format'
import { useFetch } from '../lib/hooks'
import { t } from '../lib/i18n'

function getVillageName(village) {
  if (!village) return ''
  const isMarathi = localStorage.getItem('kvp_lang') === 'mr'
  if (isMarathi) {
    return village.name_mr || village.marathi_name || village.name_marathi || village.nameMr || village.name || ''
  }
  return village.name_en || village.name || village.name_mr || village.marathi_name || ''
}

function PunchCard({ label, time, photo, gps }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-500">{t(label)}</span>
        <span className="flex items-center gap-1 text-sm font-semibold text-gray-900">
          <Clock className="h-4 w-4 text-gray-400" />
          {time || '—'}
        </span>
      </div>
      {photo ? (
        <img src={photo} alt={t(label)} className="aspect-[4/3] w-full rounded-lg object-cover" />
      ) : (
        <div className="flex aspect-[4/3] w-full items-center justify-center rounded-lg bg-gray-50 text-xs text-gray-400">
          {t('No photo yet')}
        </div>
      )}
      {gps?.lat != null && gps?.lng != null && (
        <div className="mt-2 flex items-center gap-1 text-[11px] text-gray-500">
          <MapPin className="h-3.5 w-3.5" />
          {Number(gps.lat).toFixed(5)}, {Number(gps.lng).toFixed(5)}
        </div>
      )}
    </div>
  )
}

export default function VolunteerCheckIn() {
  const { user } = useAuth()
  const [selectedVillageId, setSelectedVillageId] = useState('')
  const [noteCamOpen, setNoteCamOpen] = useState(false)
  const [noteCamAction, setNoteCamAction] = useState('CHECK-IN')
  const [today, setToday] = useState(null)
  const [todayLoading, setTodayLoading] = useState(true)

  // Only needed for the volunteer's assigned villages / assignment status.
  const { data, error, loading, reload } = useFetch('/volunteers/me/dashboard')

  const fetchToday = async () => {
    try {
      const res = await api.get('/attendance/today')
      setToday(res.data)
    } catch {
      // ignore
    } finally {
      setTodayLoading(false)
    }
  }

  useEffect(() => {
    fetchToday()
    const handleUpdate = () => fetchToday()
    window.addEventListener('kvp:attendance-updated', handleUpdate)
    return () => window.removeEventListener('kvp:attendance-updated', handleUpdate)
  }, [])

  // Restore a pending NoteCam session if the mobile browser was suspended/refreshed.
  useEffect(() => {
    if (todayLoading) return
    try {
      const saved = sessionStorage.getItem('kvp_notecam_pending')
      if (!saved) return
      const item = JSON.parse(saved)
      if (Date.now() - (item.timestamp || 0) >= 5 * 60 * 1000) return
      if (today?.checked_out) {
        sessionStorage.removeItem('kvp_notecam_pending')
        return
      }
      setNoteCamAction(item.action || 'CHECK-IN')
      if (item.villageId) setSelectedVillageId(item.villageId)
      setNoteCamOpen(true)
    } catch {}
  }, [todayLoading]) // eslint-disable-line react-hooks/exhaustive-deps

  const openNoteCam = (action) => {
    if (today?.checked_out) return
    setNoteCamAction(action)
    setNoteCamOpen(true)
  }

  if ((loading && !data) || todayLoading) return <Spinner />

  const villages = data?.villages || (data?.village ? [data.village] : [])
  const record = today?.record
  const checkedIn = Boolean(today?.checked_in)
  const checkedOut = Boolean(today?.checked_out)

  return (
    <div className="space-y-5 pb-16 lg:pb-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PageHeader
          title={t('Attendance')}
          subtitle={`${t('NoteCam daily check-in and check-out')} · ${fmtDate(today?.attendance_date)}`}
        />
        <Button size="sm" variant="secondary" icon={RefreshCw} onClick={() => { reload(); fetchToday() }}>
          {t('Refresh')}
        </Button>
      </div>

      <ErrorBox message={error} />

      {data && !data.assigned && (
        <Card title={t('Village assignment needed')}>
          <p className="text-sm text-gray-600">
            {t('Your account is active, but no village is assigned yet. Contact your Stakeholder / Admin to receive an assignment before recording field work.')}
          </p>
        </Card>
      )}

      {data?.assigned && (
        <>
          <div className="overflow-hidden rounded-2xl shadow-sm">
            {!checkedIn ? (
              <div className="flex flex-col items-center gap-4 bg-brand-gradient p-6 text-center text-white">
                <div className="flex h-16 w-16 items-center justify-center rounded-full bg-white/15">
                  <Camera className="h-8 w-8" />
                </div>
                <div>
                  <h3 className="text-lg font-bold">{t('You have not checked in today')}</h3>
                  <p className="mt-1 text-xs text-white/80">
                    {t('Capture your NoteCam photo with GPS & village stamp to mark attendance.')}
                  </p>
                </div>
                <Button
                  variant="light"
                  onClick={() => openNoteCam('CHECK-IN')}
                  className="w-full px-5 py-3 font-bold shadow transition active:scale-95 sm:w-auto"
                >
                  <Camera className="mr-2 h-5 w-5 text-brand-600" />
                  {t('NoteCam Check-In')}
                </Button>
              </div>
            ) : !checkedOut ? (
              <div className="flex flex-col items-center gap-4 bg-brand-gradient p-6 text-center text-white">
                <div className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-white/80">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400" /> {t('Currently Checked In')}
                </div>
                <div>
                  <h3 className="text-lg font-bold">{t('Checked In at')} {record?.check_in}</h3>
                  <p className="mt-1 text-xs text-white/80">📍 {record?.village_name || getVillageName(data.village)}</p>
                </div>
                <Button
                  variant="light"
                  onClick={() => openNoteCam('CHECK-OUT')}
                  className="w-full px-5 py-3 font-bold shadow transition active:scale-95 sm:w-auto"
                >
                  <Camera className="mr-2 h-5 w-5" />
                  {t('NoteCam Check-Out')}
                </Button>
              </div>
            ) : (
              <div className="flex flex-wrap items-center justify-between gap-3 border border-emerald-200 bg-emerald-50 p-5 text-emerald-900">
                <div className="flex items-center gap-3">
                  <CheckCircle2 className="h-7 w-7 shrink-0 text-emerald-600" />
                  <div>
                    <div className="text-xs font-bold uppercase text-emerald-700">{t('Day Attendance Completed')}</div>
                    <div className="mt-0.5 text-sm font-semibold">
                      {t('In')}: {record?.check_in} · {t('Out')}: {record?.check_out}
                    </div>
                    <div className="mt-0.5 text-xs text-emerald-600">
                      📍 {record?.village_name || getVillageName(data.village)}
                    </div>
                  </div>
                </div>
                <span className="rounded-full border border-emerald-300 bg-emerald-100 px-3 py-1 text-xs font-semibold text-emerald-800">
                  {t('Present')}
                </span>
              </div>
            )}
          </div>

          {villages.length > 1 && !checkedIn && (
            <Card title={t('Assigned Villages')}>
              <div className="flex flex-wrap gap-2">
                {villages.map((v) => {
                  const active = String(v.id) === String(selectedVillageId || data.selected_village_id || villages[0]?.id)
                  return (
                    <button
                      key={v.id}
                      type="button"
                      onClick={() => setSelectedVillageId(v.id)}
                      className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                        active ? 'bg-brand-700 text-white shadow-sm' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                      }`}
                    >
                      <MapPin className="h-3.5 w-3.5" />
                      {getVillageName(v)}
                    </button>
                  )
                })}
              </div>
            </Card>
          )}

          {checkedIn && (
            <Card title={t("Today's attendance")}>
              <div className="grid gap-3 sm:grid-cols-2">
                <PunchCard label="Check-in" time={record?.check_in} photo={record?.check_in_photo} gps={record?.check_in_gps} />
                <PunchCard label="Check-out" time={record?.check_out} photo={record?.check_out_photo} gps={record?.check_out_gps} />
              </div>
            </Card>
          )}
        </>
      )}

      <NoteCamModal
        open={noteCamOpen}
        onClose={() => setNoteCamOpen(false)}
        action={noteCamAction}
        user={user}
        villages={villages}
        selectedVillageId={selectedVillageId || data?.selected_village_id || data?.village?.id}
        onSuccess={() => {
          setNoteCamOpen(false)
          fetchToday()
          window.dispatchEvent(new CustomEvent('kvp:attendance-updated'))
        }}
      />
    </div>
  )
}
