import { Camera, Check, MapPin, RefreshCw, X, AlertCircle, SwitchCamera, CheckCircle2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Button, ErrorBox, Modal, Spinner } from './ui'
import api, { errorMessage } from '../lib/api'
import { getPreciseGpsLocation, stampNoteCamPhoto } from '../lib/notecam'
import { todayISO } from '../lib/format'
import { t } from '../lib/i18n'

export default function NoteCamModal({
  open,
  onClose,
  action = 'CHECK-IN', // 'CHECK-IN' or 'CHECK-OUT'
  user,
  villages = [],
  selectedVillageId = null,
  onSuccess,
}) {
  const [gps, setGps] = useState(null)
  const [gpsLoading, setGpsLoading] = useState(true)
  const [gpsError, setGpsError] = useState('')
  const [activeVillageId, setActiveVillageId] = useState(selectedVillageId || villages[0]?.id || user?.village_id || '')
  const [remarks, setRemarks] = useState('')

  const [cameraActive, setCameraActive] = useState(false)
  const [cameraLoading, setCameraLoading] = useState(false)
  const [cameraError, setCameraError] = useState('')
  const [facingMode, setFacingMode] = useState('environment') // 'environment' (back) or 'user' (front)
  const [capturedPhoto, setCapturedPhoto] = useState(null)
  const [processingPhoto, setProcessingPhoto] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [alreadyCompleted, setAlreadyCompleted] = useState(false)
  const [apiError, setApiError] = useState('')

  const videoRef = useRef(null)
  const streamRef = useRef(null)
  const fileInputRef = useRef(null)

  const activeVillage = villages.find((v) => String(v.id) === String(activeVillageId))
  const villageName = activeVillage?.name || user?.village?.name || ''

  // 1. Fetch GPS on open
  const fetchGps = async () => {
    setGpsLoading(true)
    setGpsError('')
    const res = await getPreciseGpsLocation()
    if (res.coords) {
      setGps(res.coords)
    } else {
      setGpsError(res.error || t('Could not obtain GPS location.'))
    }
    setGpsLoading(false)
  }

  // Helper to attach video stream cleanly
  const attachStreamToVideo = (el, stream) => {
    if (!el || !stream) return
    try {
      el.srcObject = stream
      el.muted = true
      el.setAttribute('playsinline', 'true')
      el.setAttribute('webkit-playsinline', 'true')
      el.onloadedmetadata = () => {
        el.play().catch(() => {})
      }
      el.play().catch(() => {})
    } catch (e) {
      console.warn('Video attach stream warning:', e)
    }
  }

  // Ref callback for the <video> element
  const handleVideoRef = (el) => {
    videoRef.current = el
    if (el && streamRef.current && el.srcObject !== streamRef.current) {
      attachStreamToVideo(el, streamRef.current)
    }
  }

  // 2. Stop camera tracks
  const stopCamera = () => {
    if (streamRef.current) {
      try {
        streamRef.current.getTracks().forEach((track) => track.stop())
      } catch {}
      streamRef.current = null
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
    setCameraActive(false)
  }

  // 3. Start Live Camera with progressive fallbacks
  const startCamera = async (facing = facingMode) => {
    setCameraError('')
    setCameraLoading(true)
    stopCamera()

    if (!navigator?.mediaDevices?.getUserMedia) {
      setCameraError(t('Live camera stream not supported by this browser. Use photo upload below.'))
      setCameraLoading(false)
      return
    }

    const constraintSets = [
      { video: { facingMode: { ideal: facing }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false },
      { video: { facingMode: { ideal: facing } }, audio: false },
      { video: { facingMode: facing }, audio: false },
      { video: true, audio: false },
    ]

    let stream = null
    for (const constraints of constraintSets) {
      try {
        stream = await navigator.mediaDevices.getUserMedia(constraints)
        if (stream) break
      } catch (e) {
        // try next fallback
      }
    }

    if (stream) {
      streamRef.current = stream
      if (videoRef.current) {
        attachStreamToVideo(videoRef.current, stream)
      }
      setCameraActive(true)
    } else {
      setCameraError(t('Camera permission not granted or camera in use. Please enable camera access or choose a photo below.'))
      setCameraActive(false)
    }
    setCameraLoading(false)
  }

  // Switch between Rear and Front camera
  const toggleFacingMode = () => {
    const next = facingMode === 'environment' ? 'user' : 'environment'
    setFacingMode(next)
    startCamera(next)
  }

  // Lifecycle
  useEffect(() => {
    if (open) {
      setCapturedPhoto(null)
      setApiError('')
      setAlreadyCompleted(false)

      // Guard: if already checked out today, check-in is not permitted
      if (user?.role === 'volunteer') {
        api.get('/attendance/today')
          .then((res) => {
            if (res.data?.checked_out && action === 'CHECK-IN') {
              setAlreadyCompleted(true)
              setApiError(t('You have already checked out today. Daily attendance is taken only once.'))
              stopCamera()
            }
          })
          .catch(() => {})
      }

      fetchGps()
      startCamera(facingMode)

      // Persist session state so if tab is recycled by mobile OS, it can be resumed
      try {
        sessionStorage.setItem(
          'kvp_notecam_pending',
          JSON.stringify({ action, villageId: activeVillageId, timestamp: Date.now() })
        )
      } catch {}
    } else {
      stopCamera()
      setAlreadyCompleted(false)
      try {
        sessionStorage.removeItem('kvp_notecam_pending')
      } catch {}
    }
    return () => {
      stopCamera()
    }
  }, [open, action])

  // Handle snap from live video
  const snapLivePhoto = async () => {
    if (!videoRef.current) return
    setProcessingPhoto(true)
    setApiError('')
    try {
      const video = videoRef.current
      const w = video.videoWidth || 640
      const h = video.videoHeight || 480
      const canvas = document.createElement('canvas')
      canvas.width = w
      canvas.height = h
      const ctx = canvas.getContext('2d')

      if (facingMode === 'user') {
        // Mirror selfie camera horizontally
        ctx.translate(w, 0)
        ctx.scale(-1, 1)
      }
      ctx.drawImage(video, 0, 0, w, h)

      const stamped = await stampNoteCamPhoto({
        source: canvas,
        userName: user?.name || 'Volunteer',
        role: user?.role || 'volunteer',
        action: action === 'CHECK-IN' ? 'CHECK-IN' : 'CHECK-OUT',
        villageName,
        gps,
        timestamp: new Date().toISOString(),
      })
      setCapturedPhoto(stamped.dataUrl)
      stopCamera()
    } catch (err) {
      console.error('Snap error:', err)
      setApiError(errorMessage(err) || t('Error stamping NoteCam photo.'))
    } finally {
      setProcessingPhoto(false)
    }
  }

  // Handle file capture (device gallery / camera upload)
  const handleFileCapture = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setProcessingPhoto(true)
    setApiError('')
    try {
      const stamped = await stampNoteCamPhoto({
        source: file,
        userName: user?.name || 'Volunteer',
        role: user?.role || 'volunteer',
        action: action === 'CHECK-IN' ? 'CHECK-IN' : 'CHECK-OUT',
        villageName,
        gps,
        timestamp: new Date().toISOString(),
      })
      setCapturedPhoto(stamped.dataUrl)
      stopCamera()
    } catch (err) {
      console.error('File process error:', err)
      setApiError(errorMessage(err) || t('Failed to process photo.'))
    } finally {
      setProcessingPhoto(false)
      if (e.target) e.target.value = ''
    }
  }

  // Retake
  const retake = () => {
    setCapturedPhoto(null)
    startCamera(facingMode)
  }

  // Close modal safely
  const handleClose = () => {
    stopCamera()
    try {
      sessionStorage.removeItem('kvp_notecam_pending')
    } catch {}
    onClose()
  }

  // Submit Check-In / Check-Out
  const handleSubmit = async () => {
    if (alreadyCompleted && action === 'CHECK-IN') {
      setApiError(t('Attendance already completed for today. Daily attendance is taken only once.'))
      return
    }
    if (!capturedPhoto) {
      setApiError(t('Please take a NoteCam photo before submitting.'))
      return
    }

    setSubmitting(true)
    setApiError('')
    try {
      const endpoint = action === 'CHECK-IN' ? '/attendance/check-in' : '/attendance/check-out'
      const payload = {
        attendance_date: todayISO(),
        village_id: activeVillageId || null,
        village_name: villageName || null,
        gps: gps
          ? {
              lat: gps.lat,
              lng: gps.lng,
              accuracy_m: gps.accuracy_m,
              captured_at: gps.captured_at,
              village_name: villageName,
            }
          : null,
        photo: capturedPhoto,
        remarks: remarks.trim() || null,
      }

      const res = await api.post(endpoint, payload)
      try {
        sessionStorage.removeItem('kvp_notecam_pending')
      } catch {}

      if (onSuccess) onSuccess(res.data)
      handleClose()
    } catch (err) {
      setApiError(errorMessage(err) || t('Failed to record attendance.'))
    } finally {
      setSubmitting(false)
    }
  }

  if (!open) return null

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={
        <div className="flex items-center gap-2">
          <Camera className="h-5 w-5 text-brand-700" />
          <span>{action === 'CHECK-IN' ? t('NoteCam Check-In') : t('NoteCam Check-Out')}</span>
        </div>
      }
      footer={
        <div className="flex w-full flex-wrap items-center justify-between gap-2">
          {alreadyCompleted ? (
            <div className="text-xs font-semibold text-emerald-800">{t('Attendance taken for today.')}</div>
          ) : capturedPhoto ? (
            <Button variant="secondary" onClick={retake} disabled={submitting}>
              {t('Retake photo')}
            </Button>
          ) : (
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
                disabled={processingPhoto}
              >
                <Camera className="mr-1.5 h-4 w-4 text-brand-700" />
                {t('Upload / Gallery')}
              </Button>
            </div>
          )}

          <div className="flex gap-2">
            <Button variant="secondary" onClick={handleClose} disabled={submitting}>
              {alreadyCompleted ? t('Close') : t('Cancel')}
            </Button>
            {!alreadyCompleted && capturedPhoto && (
              <Button
                busy={submitting}
                onClick={handleSubmit}
                className={action === 'CHECK-IN' ? 'bg-emerald-600 hover:bg-emerald-700' : 'bg-amber-600 hover:bg-amber-700'}
              >
                <Check className="mr-1.5 h-4 w-4" />
                {action === 'CHECK-IN' ? t('Confirm Check-In') : t('Confirm Check-Out')}
              </Button>
            )}
          </div>
        </div>
      }
    >
      <div className="space-y-4">
        {apiError && <ErrorBox message={apiError} />}

        {/* GPS Status Indicator */}
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-gray-200 bg-gray-50 p-3">
          <div className="flex items-center gap-2 text-xs sm:text-sm">
            <MapPin className="h-4 w-4 shrink-0 text-brand-700" />
            {gpsLoading ? (
              <span className="flex items-center gap-1.5 text-gray-600">
                <Spinner size="sm" /> {t('Acquiring high accuracy GPS…')}
              </span>
            ) : gps ? (
              <div className="leading-tight">
                <span className="font-semibold text-emerald-800">
                  {t('GPS Locked')}: {gps.lat.toFixed(5)}°, {gps.lng.toFixed(5)}°
                </span>
                <span className="ml-1 text-gray-500 text-xs">
                  (±{gps.accuracy_m}m)
                </span>
              </div>
            ) : (
              <span className="text-amber-800 flex items-center gap-1">
                <AlertCircle className="h-4 w-4 text-amber-600" />
                {gpsError || t('GPS unavailable')}
              </span>
            )}
          </div>

          <Button
            size="sm"
            variant="ghost"
            icon={RefreshCw}
            busy={gpsLoading}
            onClick={fetchGps}
            title={t('Refresh GPS location')}
          >
            {t('Retry GPS')}
          </Button>
        </div>

        {/* Village Context Selector (for multi-village Volunteers) */}
        {villages.length > 1 && (
          <div>
            <label className="mb-1 block text-xs font-semibold text-gray-700">
              {t('Select Village for Attendance *')}
            </label>
            <select
              value={activeVillageId}
              onChange={(e) => setActiveVillageId(e.target.value)}
              className="w-full rounded-lg border border-gray-300 bg-white p-2.5 text-sm font-medium focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              {villages.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Live NoteCam Viewfinder & Stamped Photo Display */}
        <div className="relative overflow-hidden rounded-xl border border-gray-300 bg-black aspect-[4/3] flex items-center justify-center">
          {alreadyCompleted ? (
            <div className="p-6 text-center text-white space-y-3">
              <CheckCircle2 className="mx-auto h-14 w-14 text-emerald-400" />
              <h4 className="text-base font-bold text-white">{t('Day Attendance Completed')}</h4>
              <p className="text-xs text-gray-300 max-w-xs mx-auto">
                {t('You have already checked out today. Daily attendance is taken only once.')}
              </p>
            </div>
          ) : capturedPhoto ? (
            <img
              src={capturedPhoto}
              alt="NoteCam check-in photo"
              className="h-full w-full object-contain"
            />
          ) : (
            <>
              {/* Always keep video element in DOM so MediaStream attaches immediately */}
              <video
                ref={handleVideoRef}
                playsInline
                autoPlay
                muted
                className={`h-full w-full object-cover ${facingMode === 'user' ? '-scale-x-100' : ''}`}
              />

              {/* Camera Loading Overlay */}
              {cameraLoading && (
                <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/70 text-white z-10">
                  <Spinner size="lg" />
                  <p className="mt-2 text-xs text-gray-300">{t('Starting camera…')}</p>
                </div>
              )}

              {/* Camera Permission / Error Overlay */}
              {cameraError && !cameraActive && (
                <div className="absolute inset-0 flex flex-col items-center justify-center bg-gray-900 p-6 text-center text-white z-10 space-y-3">
                  <Camera className="mx-auto h-12 w-12 text-gray-400" />
                  <p className="text-xs sm:text-sm text-amber-300 max-w-xs">{cameraError}</p>
                  <div className="flex flex-wrap justify-center gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => startCamera(facingMode)}
                      className="bg-white text-gray-900"
                    >
                      <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                      {t('Retry Camera')}
                    </Button>
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <Camera className="mr-1.5 h-3.5 w-3.5" />
                      {t('Choose Photo')}
                    </Button>
                  </div>
                </div>
              )}

              {/* Viewfinder Overlays when Camera is Active */}
              {cameraActive && !cameraLoading && (
                <>
                  {/* Top Bar: Front/Back Camera Flip button */}
                  <div className="absolute top-3 right-3 z-10 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={toggleFacingMode}
                      className="flex items-center gap-1.5 rounded-full bg-black/60 px-3 py-1.5 text-xs font-semibold text-white backdrop-blur hover:bg-black/80 transition active:scale-95 shadow-md"
                      title={t('Switch front/back camera')}
                    >
                      <RefreshCw className="h-3.5 w-3.5" />
                      <span>{facingMode === 'environment' ? t('Front (Selfie)') : t('Back (Village)')}</span>
                    </button>
                  </div>

                  {/* Top Bar: GPS badge on viewfinder */}
                  <div className="absolute top-3 left-3 z-10 flex items-center gap-1.5 rounded-full bg-black/60 px-2.5 py-1 text-[11px] font-medium text-white backdrop-blur shadow-md">
                    <MapPin className="h-3 w-3 text-emerald-400" />
                    <span>{gps ? `${gps.lat.toFixed(4)}°, ${gps.lng.toFixed(4)}°` : t('GPS locating…')}</span>
                  </div>

                  {/* Center Shutter Button at bottom */}
                  <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 flex items-center gap-3">
                    <button
                      type="button"
                      onClick={snapLivePhoto}
                      disabled={processingPhoto}
                      className="flex h-16 w-16 items-center justify-center rounded-full border-4 border-white bg-red-600 shadow-2xl transition active:scale-90 hover:bg-red-700"
                      aria-label={t('Take Photo')}
                    >
                      <div className="h-6 w-6 rounded-full bg-white shadow-inner" />
                    </button>
                  </div>
                </>
              )}
            </>
          )}

          {/* Stamping Processing Overlay */}
          {processingPhoto && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80 text-white z-20">
              <Spinner size="lg" />
              <p className="mt-3 text-sm font-medium">{t('Stamping NoteCam GPS data onto photo…')}</p>
            </div>
          )}
        </div>

        {/* Hidden File Input for Gallery / Upload (without aggressive capture mode) */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleFileCapture}
        />

        {/* Optional Remarks */}
        <div>
          <label className="mb-1 block text-xs font-semibold text-gray-700">
            {t('Remarks (optional)')}
          </label>
          <input
            type="text"
            value={remarks}
            onChange={(e) => setRemarks(e.target.value)}
            placeholder={t('e.g. Starting field visits in Ward 2')}
            className="w-full rounded-lg border border-gray-300 p-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>
      </div>
    </Modal>
  )
}
