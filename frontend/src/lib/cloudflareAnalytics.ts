const BEACON_SRC = 'https://static.cloudflareinsights.com/beacon.min.js'

export function initCloudflareWebAnalytics(): void {
  const token = import.meta.env.VITE_CF_WEB_ANALYTICS_TOKEN?.trim()
  if (!token) return
  if (document.querySelector(`script[src="${BEACON_SRC}"]`)) return

  const script = document.createElement('script')
  script.defer = true
  script.src = BEACON_SRC
  script.setAttribute('data-cf-beacon', JSON.stringify({ token }))
  document.head.appendChild(script)
}
