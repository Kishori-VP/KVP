import { t } from './i18n'

// The server is a Vercel function, which refuses request bodies over ~4.5 MB.
export const MAX_UPLOAD_BYTES = 4 * 1024 * 1024
const MAX_DIMENSION = 1600 // px on the long side: sharp on screen and in reports
const JPEG_QUALITY = 0.82

async function decode(file) {
  if (window.createImageBitmap) {
    try {
      return await createImageBitmap(file, { imageOrientation: 'from-image' })
    } catch { /* fall back to <img> */ }
  }
  const url = URL.createObjectURL(file)
  try {
    const img = new Image()
    img.src = url
    await img.decode()
    return img
  } finally {
    URL.revokeObjectURL(url)
  }
}

async function compressImage(file) {
  const img = await decode(file)
  const w0 = img.width || img.naturalWidth
  const h0 = img.height || img.naturalHeight
  const scale = Math.min(1, MAX_DIMENSION / Math.max(w0, h0))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(w0 * scale)
  canvas.height = Math.round(h0 * scale)
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#fff' // transparent PNGs get a white background instead of black
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
  img.close?.()
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY))
  if (!blob) throw new Error('encode failed')
  const name = `${(file.name || 'photo').replace(/\.[^.]+$/, '')}.jpg`
  return new File([blob], name, { type: 'image/jpeg', lastModified: file.lastModified })
}

/**
 * Get a picked file ready to upload: photos are resized and saved as JPEG (a 6 MB phone photo
 * becomes ~300 KB), other files are checked against the size limit. Throws an Error with a
 * readable message when the file cannot be sent.
 */
export async function prepareUpload(file) {
  if (file.type?.startsWith('image/') && !/gif|svg/.test(file.type)) {
    try {
      const small = await compressImage(file)
      return small.size < file.size || file.size > MAX_UPLOAD_BYTES ? small : file
    } catch {
      // The browser cannot read this format (e.g. HEIC on Chrome): send the original if it fits.
    }
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    throw new Error(t('{name} is too large ({mb} MB). The limit is 4 MB, so please choose a smaller file.', {
      name: file.name, mb: (file.size / 1024 / 1024).toFixed(1),
    }))
  }
  return file
}

/**
 * Current position, or null. Never hangs: if the permission prompt is ignored the browser calls
 * neither callback, so give up after `timeoutMs`.
 */
export function getCoords(timeoutMs = 6000) {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null)
    const timer = setTimeout(() => resolve(null), timeoutMs)
    navigator.geolocation.getCurrentPosition(
      (p) => { clearTimeout(timer); resolve(p.coords) },
      () => { clearTimeout(timer); resolve(null) },
      { timeout: timeoutMs - 500, maximumAge: 60000 },
    )
  })
}
