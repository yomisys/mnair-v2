/**
 * Runs on every page load. Removes any service worker on this site that we
 * didn't publish (only /sw.js is ours) and any cache our worker didn't
 * create — leftovers from the October 2026 compromise. The server-side kill
 * switch (frontend/nginx.conf + public/sw-reset.js) covers phones where the
 * rogue worker stops this page from loading at all.
 */
const OUR_WORKER = '/sw.js'
const OUR_CACHES = new Set(['mnair-shell-v2'])

export async function cleanUpRogueWorkers(): Promise<void> {
  try {
    if ('serviceWorker' in navigator) {
      const registrations = await navigator.serviceWorker.getRegistrations()
      await Promise.all(registrations.map((reg) => {
        const worker = reg.active || reg.waiting || reg.installing
        const path = worker ? new URL(worker.scriptURL).pathname : ''
        return path === OUR_WORKER ? reg.update().catch(() => undefined) : reg.unregister()
      }))
    }
    if ('caches' in window) {
      const keys = await caches.keys()
      await Promise.all(keys.filter((k) => !OUR_CACHES.has(k)).map((k) => caches.delete(k)))
    }
  } catch {
    // Never block the app over clean-up
  }
}
