/**
 * NoteCam GPS Geotagging & Camera Utilities for KVP Field Operations.
 * Emulates the NoteCam application by burning GPS coordinates, village,
 * timestamp, action (Check-In/Out), and user details directly onto the photo canvas.
 */

export function getPreciseGpsLocation() {
  return new Promise((resolve) => {
    if (!navigator.geolocation) {
      resolve({
        coords: null,
        error: 'Geolocation is not supported by your browser or device.',
      })
      return
    }

    // High accuracy attempt
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        resolve({
          coords: {
            lat: pos.coords.latitude,
            lng: pos.coords.longitude,
            accuracy_m: Math.round(pos.coords.accuracy || 0),
            captured_at: new Date().toISOString(),
          },
          error: null,
        })
      },
      (err) => {
        // Fallback to standard accuracy if high accuracy timed out or was unavailable
        if (err.code === 3 || err.code === 2) {
          navigator.geolocation.getCurrentPosition(
            (fallbackPos) => {
              resolve({
                coords: {
                  lat: fallbackPos.coords.latitude,
                  lng: fallbackPos.coords.longitude,
                  accuracy_m: Math.round(fallbackPos.coords.accuracy || 0),
                  captured_at: new Date().toISOString(),
                },
                error: null,
              })
            },
            (fallbackErr) => {
              let msg = 'Could not acquire GPS location.'
              if (fallbackErr.code === 1) msg = 'Location permission denied. Please allow location access in your browser settings.'
              else if (fallbackErr.code === 2) msg = 'GPS signal unavailable. Please ensure device location / GPS is turned ON.'
              else if (fallbackErr.code === 3) msg = 'GPS request timed out. Please retry in an open area.'
              resolve({ coords: null, error: msg })
            },
            { enableHighAccuracy: false, timeout: 10000, maximumAge: 30000 }
          )
        } else {
          let msg = 'Location access error.'
          if (err.code === 1) msg = 'Location permission denied. Please allow location access in your browser settings.'
          resolve({ coords: null, error: msg })
        }
      },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 0 }
    )
  })
}

/**
 * Loads an image file into an Image object
 */
function loadImage(source) {
  return new Promise((resolve, reject) => {
    if (source instanceof HTMLImageElement) {
      if (source.complete) resolve(source)
      else {
        source.onload = () => resolve(source)
        source.onerror = reject
      }
      return
    }

    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = reject

    if (typeof source === 'string') {
      img.src = source
    } else if (source instanceof Blob || source instanceof File) {
      img.src = URL.createObjectURL(source)
    } else {
      reject(new Error('Invalid image source'))
    }
  })
}

/**
 * Burn NoteCam style GPS banner onto the photo
 */
export async function stampNoteCamPhoto({
  source,
  userName = 'User',
  role = 'volunteer',
  action = 'CHECK-IN', // 'CHECK-IN' or 'CHECK-OUT'
  villageName = '',
  gps = null,
  timestamp = null,
}) {
  const img = await loadImage(source)

  // Target maximum resolution for efficient upload and crisp text
  const maxDimension = 1440
  let width = img.naturalWidth || img.width
  let height = img.naturalHeight || img.height

  if (width > maxDimension || height > maxDimension) {
    if (width > height) {
      height = Math.round((height * maxDimension) / width)
      width = maxDimension
    } else {
      width = Math.round((width * maxDimension) / height)
      height = maxDimension
    }
  }

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')

  // 1. Draw base image
  ctx.drawImage(img, 0, 0, width, height)

  // 2. Compute overlay banner dimensions
  const isPortrait = height > width
  const bannerHeight = Math.max(140, Math.round(height * (isPortrait ? 0.20 : 0.24)))
  const bannerY = height - bannerHeight

  // Dark translucent background with smooth gradient
  const gradient = ctx.createLinearGradient(0, bannerY, 0, height)
  gradient.addColorStop(0, 'rgba(15, 23, 42, 0.88)')
  gradient.addColorStop(1, 'rgba(15, 23, 42, 0.96)')

  ctx.fillStyle = gradient
  ctx.fillRect(0, bannerY, width, bannerHeight)

  // Top highlight border on banner
  const isCheckIn = action.toUpperCase().includes('IN')
  ctx.fillStyle = isCheckIn ? '#10b981' : '#f59e0b' // emerald for check-in, amber for check-out
  ctx.fillRect(0, bannerY, width, Math.max(4, Math.round(width * 0.005)))

  // 3. Render NoteCam Text Info
  const paddingX = Math.round(width * 0.035)
  const baseFontSize = Math.max(13, Math.round(width * 0.024))
  const titleFontSize = Math.max(15, Math.round(width * 0.028))

  let cursorY = bannerY + Math.round(bannerHeight * 0.22)

  // Line 1: Header / Program Name & Action Badge
  ctx.font = `bold ${titleFontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`
  ctx.fillStyle = '#ffffff'
  ctx.fillText('KISHORI VIKAS PROGRAM (SEDT)', paddingX, cursorY)

  // Badge on top right of banner
  const badgeText = action.toUpperCase()
  const badgeWidth = ctx.measureText(badgeText).width + 24
  const badgeHeight = titleFontSize + 10
  const badgeX = width - paddingX - badgeWidth
  const badgeY = cursorY - titleFontSize + 2

  ctx.fillStyle = isCheckIn ? '#059669' : '#d97706'
  ctx.beginPath()
  ctx.roundRect ? ctx.roundRect(badgeX, badgeY, badgeWidth, badgeHeight, 6) : ctx.fillRect(badgeX, badgeY, badgeWidth, badgeHeight)
  ctx.fill()

  ctx.fillStyle = '#ffffff'
  ctx.fillText(badgeText, badgeX + 12, cursorY + 1)

  // Line 2: Person & Village
  cursorY += Math.round(titleFontSize * 1.45)
  ctx.font = `600 ${baseFontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`
  const roleDisplay = role === 'volunteer' ? 'Tai' : (role === 'stakeholder' || role === 'super_admin') ? 'Stakeholder' : 'Admin'
  const userText = `👤 ${userName} (${roleDisplay})`
  const villageText = villageName ? `   📍 Village: ${villageName}` : '   📍 Village: Field'
  ctx.fillStyle = '#f1f5f9'
  ctx.fillText(userText + villageText, paddingX, cursorY)

  // Line 3: GPS Coordinates & Accuracy
  cursorY += Math.round(baseFontSize * 1.35)
  ctx.font = `normal ${baseFontSize}px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`
  let gpsText = '🌐 GPS: Not available'
  if (gps && gps.lat != null && gps.lng != null) {
    const latStr = Number(gps.lat).toFixed(6)
    const lngStr = Number(gps.lng).toFixed(6)
    const accStr = gps.accuracy_m != null ? ` (±${Math.round(gps.accuracy_m)}m)` : ''
    gpsText = `🌐 Lat: ${latStr}°, Lng: ${lngStr}°${accStr}`
  }
  ctx.fillStyle = '#38bdf8' // sky blue
  ctx.fillText(gpsText, paddingX, cursorY)

  // Line 4: Formatted Date & Time (IST)
  cursorY += Math.round(baseFontSize * 1.35)
  const now = timestamp ? new Date(timestamp) : new Date()
  const timeFormatted = now.toLocaleDateString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }) + ' · ' + now.toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  }) + ' IST'

  ctx.fillStyle = '#cbd5e1'
  ctx.fillText(`🕒 ${timeFormatted}`, paddingX, cursorY)

  // Export as compressed high quality JPEG
  const dataUrl = canvas.toDataURL('image/jpeg', 0.86)
  const blob = await new Promise((res) => canvas.toBlob(res, 'image/jpeg', 0.86))

  return { dataUrl, blob, width, height }
}
