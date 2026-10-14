/* MNAIR service-worker kill switch.
 *
 * nginx serves this file for ANY .js request outside /assets/ other than
 * /sw.js (see frontend/nginx.conf). A phone that picked up a rogue service
 * worker during the October 2026 site compromise re-checks that worker's
 * script URL on its next visit, receives this file instead, and runs it:
 * it deletes every cache, unregisters itself and reloads open tabs, so the
 * next load comes straight from the real site.
 */
self.addEventListener('install', () => self.skipWaiting())

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys()
    await Promise.all(keys.map((k) => caches.delete(k)))
    await self.registration.unregister()
    const tabs = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    for (const tab of tabs) {
      try { tab.navigate(tab.url) } catch (_) { /* tab may be gone */ }
    }
  })())
})

// Never answer requests: everything goes to the network (the real site)
