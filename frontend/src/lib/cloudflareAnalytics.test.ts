/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { initCloudflareWebAnalytics } from './cloudflareAnalytics'

describe('initCloudflareWebAnalytics', () => {
  afterEach(() => {
    document.head.innerHTML = ''
    vi.unstubAllEnvs()
  })

  it('does nothing when token is unset', () => {
    vi.stubEnv('VITE_CF_WEB_ANALYTICS_TOKEN', '')
    initCloudflareWebAnalytics()
    expect(document.querySelector('script[src="https://static.cloudflareinsights.com/beacon.min.js"]')).toBeNull()
  })

  it('injects the beacon script when token is set', () => {
    vi.stubEnv('VITE_CF_WEB_ANALYTICS_TOKEN', 'test-token-123')
    initCloudflareWebAnalytics()
    const script = document.querySelector('script[src="https://static.cloudflareinsights.com/beacon.min.js"]')
    expect(script).not.toBeNull()
    expect(script?.getAttribute('data-cf-beacon')).toBe(JSON.stringify({ token: 'test-token-123' }))
  })

  it('only injects once', () => {
    vi.stubEnv('VITE_CF_WEB_ANALYTICS_TOKEN', 'test-token-123')
    initCloudflareWebAnalytics()
    initCloudflareWebAnalytics()
    expect(document.querySelectorAll('script[src="https://static.cloudflareinsights.com/beacon.min.js"]')).toHaveLength(1)
  })
})
