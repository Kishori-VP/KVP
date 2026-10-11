/* KVP service worker: receives Web Push notifications. */
self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()))

const LINKS = { case: '/cases/', event: '/events/', home_visit: '/field', target: '/targets', generated_report: '/reports' }

self.addEventListener('push', (event) => {
  let data = {}
  try {
    data = event.data ? event.data.json() : {}
  } catch {
    data = { title: 'KVP', body: event.data ? event.data.text() : '' }
  }
  const base = LINKS[data.entity_type]
  const url = base ? (base.endsWith('/') && data.entity_id ? base + data.entity_id : base) : '/notifications'
  event.waitUntil(
    self.registration.showNotification(data.title || 'Kishori Vikas Programme', {
      body: data.body || '',
      icon: '/favicon.svg',
      badge: '/favicon.svg',
      tag: data.id,
      data: { url },
    }),
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data?.url || '/'
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((wins) => {
      const existing = wins.find((w) => new URL(w.url).origin === self.location.origin)
      if (existing) {
        existing.navigate(url)
        return existing.focus()
      }
      return self.clients.openWindow(url)
    }),
  )
})
