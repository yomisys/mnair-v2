/* MNAIR service worker — Web Push reminders + a tiny offline shell.
 *
 * Push payloads come from backend/app/channels/webpush.py as
 * {title, body, url}. Clicking the notification focuses an open learner
 * tab if there is one, otherwise opens /learn.
 */

const SHELL_CACHE = 'mnair-shell-v1'
const SHELL = ['/', '/learn', '/manifest.webmanifest']

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL)).catch(() => undefined)
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== SHELL_CACHE).map((k) => caches.delete(k))))
  )
  self.clients.claim()
})

// Network-first for navigations (so deploys show up), cache fallback offline.
self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET' || request.mode !== 'navigate') return
  event.respondWith(
    fetch(request)
      .then((response) => {
        const copy = response.clone()
        caches.open(SHELL_CACHE).then((cache) => cache.put(request, copy)).catch(() => undefined)
        return response
      })
      .catch(() => caches.match(request).then((hit) => hit || caches.match('/learn')))
  )
})

self.addEventListener('push', (event) => {
  let data = { title: 'MNAIR', body: 'Your next AI lesson is waiting.', url: '/learn' }
  try {
    if (event.data) data = { ...data, ...event.data.json() }
  } catch (_) { /* keep defaults */ }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/images/icon-192.png',
      badge: '/images/icon-192.png',
      data: { url: data.url },
      tag: 'mnair-reminder',
      renotify: true,
    })
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const target = (event.notification.data && event.notification.data.url) || '/learn'
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clients) => {
      for (const client of clients) {
        if ('focus' in client && new URL(client.url).pathname.startsWith('/learn')) {
          client.navigate(target).catch(() => undefined)
          return client.focus()
        }
      }
      return self.clients.openWindow(target)
    })
  )
})
