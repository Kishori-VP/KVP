import axios from 'axios'
import { t } from './i18n'

const TOKEN_KEY = 'kvp_token'

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage unavailable (private mode) - session ends on reload */
  }
}

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 90000, // 90s timeout to survive Render free tier cold-starts
})

let wakingTimeout = null

api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`

  // Notify UI if request is taking longer than 2.5s (likely Render cold-start)
  if (!wakingTimeout) {
    wakingTimeout = setTimeout(() => {
      window.dispatchEvent(new CustomEvent('kvp:backend-waking', { detail: { waking: true } }))
    }, 2500)
  }

  return config
})

api.interceptors.response.use(
  (res) => {
    if (wakingTimeout) {
      clearTimeout(wakingTimeout)
      wakingTimeout = null
    }
    window.dispatchEvent(new CustomEvent('kvp:backend-waking', { detail: { waking: false } }))
    return res
  },
  async (err) => {
    if (wakingTimeout) {
      clearTimeout(wakingTimeout)
      wakingTimeout = null
    }

    const config = err.config || {}
    const isColdStart =
      !err.response ||
      err.response.status === 502 ||
      err.response.status === 503 ||
      err.response.status === 504 ||
      err.code === 'ECONNABORTED'

    // Automatically retry up to 2 times for cold-start wake-up errors
    if (isColdStart && (config._retryCount || 0) < 2) {
      config._retryCount = (config._retryCount || 0) + 1
      window.dispatchEvent(new CustomEvent('kvp:backend-waking', { detail: { waking: true } }))
      await new Promise((resolve) => setTimeout(resolve, 3000))
      return api(config)
    }

    window.dispatchEvent(new CustomEvent('kvp:backend-waking', { detail: { waking: false } }))

    if (err.response?.status === 401 && !err.config?.url?.includes('/auth/login')) {
      setToken(null)
      window.dispatchEvent(new Event('kvp:logout'))
    }
    return Promise.reject(err)
  },
)

/** Human-readable message from a FastAPI error response. */
export function errorMessage(err) {
  const detail = err?.response?.data?.detail
  if (!detail) return err?.message || t('Something went wrong')
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((d) => `${(d.loc || []).slice(1).join('.') || 'field'}: ${d.msg}`).join('; ')
  }
  if (detail.validation_errors) return detail.validation_errors.join('; ')
  if (detail.message) return detail.message
  return JSON.stringify(detail)
}

/** Download a file endpoint (PDF/Excel) with auth. */
export async function download(url, params = {}, fallbackName = 'download') {
  const res = await api.get(url, { params, responseType: 'blob' })
  const cd = res.headers['content-disposition'] || ''
  const match = cd.match(/filename="?([^"]+)"?/)
  const href = URL.createObjectURL(res.data)
  const a = document.createElement('a')
  a.href = href
  a.download = match ? match[1] : fallbackName
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(href), 1000)
}

/** Drop empty values so they are not sent as query params. */
export function clean(params) {
  return Object.fromEntries(Object.entries(params).filter(([, v]) => v !== '' && v !== null && v !== undefined))
}

export default api
