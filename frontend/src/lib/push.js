import api from './api'

function urlBase64ToUint8Array(base64) {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)
  const raw = atob((base64 + padding).replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)))
}

export function pushSupported() {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

export async function currentSubscription() {
  if (!pushSupported()) return null
  const reg = await navigator.serviceWorker.getRegistration('/')
  return reg ? reg.pushManager.getSubscription() : null
}

/** Ask permission, subscribe this browser and register it with the backend. */
export async function enablePush() {
  if (!pushSupported()) throw new Error('This browser does not support push notifications')
  const { data } = await api.get('/push/public-key')
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') throw new Error('Notification permission was not granted')
  const reg = await navigator.serviceWorker.register('/sw.js')
  await navigator.serviceWorker.ready
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: urlBase64ToUint8Array(data.public_key) })
  const json = sub.toJSON()
  await api.post('/push/subscriptions', { endpoint: json.endpoint, keys: json.keys, user_agent: navigator.userAgent })
  return sub
}

export async function disablePush() {
  const sub = await currentSubscription()
  if (!sub) return
  await api.delete('/push/subscriptions', { params: { endpoint: sub.endpoint } })
  await sub.unsubscribe()
}
