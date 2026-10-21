import { Camera, Check, MapPin, RefreshCw, X, AlertCircle } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Button, ErrorBox, Modal, Select, Spinner } from './ui'
import api, { errorMessage } from '../lib/api'
import { getPreciseGpsLocation, stampNoteCamPhoto } from '../lib/notecam'
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
  const [cameraError, setCameraError] = useState('')
  const [capturedPhoto, setCapturedPhoto] = useState(null)
  const [processingPhoto, setProcessingPhoto] = useState(false)
  const [submitting, setSubmitting] = useState(false)
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

  // 2. Start Live Camera
  const startCamera = async () => {
    setCameraError('')
    try {
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: 'environment' },
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
          audio: false,
        })
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          videoRef.current.play()
        }
        setCameraActive(true)
      } else {
        setCameraError(t('Live camera stream not supported. Please use the camera file upload below.'))
      }
    } catch (err) {
      setCameraError(t('Camera permission not granted or camera in use. Use file picker below.'))
      setCameraActive(false)
    }
  }

  const stopCamera = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
    setCameraActive(false)
  }

  useEffect(() => {
    if (open) {
      setCapturedPhoto(null)
      setApiError('')
      fetchGps()
      startCamera()
    } else {
      stopCamera()
    }
    return () => stopCamera()
  }, [open])

  // Handle snap from live video
  const snapLivePhoto = async () => {
    if (!videoRef.current) return
    setProcessingPhoto(true)
    try {
      const video = videoRef.current
      const canvas = document.createElement('canvas')
      canvas.width = video.videoWidth || 640
      canvas.height = video.videoHeight || 480
      const ctx = canvas.getContext('2d')
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height)

      const stamped = await stampNoteCamPhoto({
        source: canvas,
        userName: user?.name || 'Tai',
        role: user?.role || 'volunteer',
        action: action === 'CHECK-IN' ? 'CHECK-IN' : 'CHECK-OUT',
        villageName,
        gps,
        timestamp: new Date().toISOString(),
      })
      setCapturedPhoto(stamped.dataUrl)
      stopCamera()
    } catch (err) {
      setApiError(errorMessage(err) || t('Error stamping NoteCam photo.'))
    } finally {
      setProcessingPhoto(false)
    }
  }

  // Handle file capture (native device camera)
  const handleFileCapture = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setProcessingPhoto(true)
    setApiError('')
    try {
      const stamped = await stampNoteCamPhoto({
        source: file,
        userName: user?.name || 'Tai',
        role: user?.role || 'volunteer',
        action: action === 'CHECK-IN' ? 'CHECK-IN' : 'CHECK-OUT',
        villageName,
        gps,
        timestamp: new Date().toISOString(),
      })
      setCapturedPhoto(stamped.dataUrl)
      stopCamera()
    } catch (err) {
      setApiError(errorMessage(err) || t('Failed to process photo.'))
    } finally {
      setProcessingPhoto(false)
    }
  }

  // Retake
  const retake = () => {
    setCapturedPhoto(null)
    startCamera()
  }

  // Submit Check-In / Check-Out
  const handleSubmit = async () => {
    if (!capturedPhoto) {
      setApiError(t('Please take a NoteCam photo before submitting.'))
      return
    }

    setSubmitting(true)
    setApiError('')
    try {
      const endpoint = action === 'CHECK-IN' ? '/attendance/check-in' : '/attendance/check-out'
      const payload = {
        attendance_date: new Date().toISOString().slice(0, 10),
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
      if (onSuccess) onSuccess(res.data)
      onClose()
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
      onClose={onClose}
      title={
        <div className="flex items-center gap-2">
          <Camera className="h-5 w-5 text-brand-700" />
          <span>{action === 'CHECK-IN' ? t('NoteCam Check-In') : t('NoteCam Check-Out')}</span>
        </div>
      }
      footer={
        <div className="flex w-full flex-wrap items-center justify-between gap-2">
          {capturedPhoto ? (
            <Button variant="secondary" onClick={retake} disabled={submitting}>
              {t('Retake photo')}
            </Button>
          ) : (
            <Button
              variant="secondary"
              onClick={() => fileInputRef.current?.click()}
              disabled={processingPhoto}
            >
              <Camera className="mr-1.5 h-4 w-4" />
              {t('Use Phone Camera')}
            </Button>
          )}

          <div className="flex gap-2">
            <Button variant="secondary" onClick={onClose} disabled={submitting}>
              {t('Cancel')}
            </Button>
            {capturedPhoto && (
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

        {/* Village Context Selector (for multi-village Tais) */}
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

        {/* Camera / Stamped Photo Display */}
        <div className="relative overflow-hidden rounded-xl border border-gray-300 bg-black aspect-[4/3] flex items-center justify-center">
          {capturedPhoto ? (
            <img
              src={capturedPhoto}
              alt="NoteCam check-in photo"
              className="h-full w-full object-contain"
            />
          ) : cameraActive ? (
            <>
              <video
                ref={videoRef}
                playsInline
                autoPlay
                className="h-full w-full object-cover"
              />
              <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-3">
                <button
                  type="button"
                  onClick={snapLivePhoto}
                  disabled={processingPhoto}
                  className="flex h-16 w-16 items-center justify-center rounded-full border-4 border-white bg-red-600 shadow-xl transition active:scale-95"
                  aria-label={t('Take Photo')}
                >
                  <div className="h-6 w-6 rounded-full bg-white" />
                </button>
              </div>
            </>
          ) : (
            <div className="p-6 text-center text-white space-y-3">
              <Camera className="mx-auto h-12 w-12 text-gray-400" />
              <p className="text-sm text-gray-300">{cameraError || t('Camera feed ready.')}</p>
              <Button
                variant="secondary"
                onClick={() => fileInputRef.current?.click()}
                className="bg-white text-gray-900"
              >
                <Camera className="mr-2 h-4 w-4 text-brand-700" />
                {t('Open Device Camera')}
              </Button>
            </div>
          )}

          {processingPhoto && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/75 text-white">
              <Spinner size="lg" />
              <p className="mt-3 text-sm font-medium">{t('Stamping NoteCam GPS data onto photo…')}</p>
            </div>
          )}
        </div>

        {/* Hidden Native File Input */}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          capture="environment"
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
