import type { Plugin } from 'vite'
import {
  DEFAULT_SITE_URL,
  SITE_DESCRIPTION,
  SITE_NAME,
  SITE_THEME_COLOR,
  SITEMAP_PATHS,
} from '../src/seo/siteMeta'

function siteUrl(): string {
  return (process.env.VITE_SITE_URL || DEFAULT_SITE_URL).replace(/\/$/, '')
}

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('"', '&quot;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
}

function seoHeadTags(): string {
  const url = siteUrl()
  const image = `${url}/og-image.png`
  const published = process.env.VITE_APP_MODE === 'published'

  const tags = [
    `<meta name="description" content="${escapeHtml(SITE_DESCRIPTION)}" />`,
    `<meta name="theme-color" content="${SITE_THEME_COLOR}" />`,
    `<link rel="canonical" href="${url}/" />`,
    `<link rel="apple-touch-icon" href="/apple-touch-icon.png" />`,
    `<meta property="og:type" content="website" />`,
    `<meta property="og:site_name" content="${escapeHtml(SITE_NAME)}" />`,
    `<meta property="og:title" content="${escapeHtml(SITE_NAME)}" />`,
    `<meta property="og:description" content="${escapeHtml(SITE_DESCRIPTION)}" />`,
    `<meta property="og:url" content="${url}/" />`,
    `<meta property="og:image" content="${image}" />`,
    `<meta property="og:image:width" content="1200" />`,
    `<meta property="og:image:height" content="630" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:title" content="${escapeHtml(SITE_NAME)}" />`,
    `<meta name="twitter:description" content="${escapeHtml(SITE_DESCRIPTION)}" />`,
    `<meta name="twitter:image" content="${image}" />`,
    `<script type="application/ld+json">${JSON.stringify({
      '@context': 'https://schema.org',
      '@type': 'WebApplication',
      name: SITE_NAME,
      description: SITE_DESCRIPTION,
      url,
      applicationCategory: 'SportsApplication',
      operatingSystem: 'Any',
    })}</script>`,
  ]

  if (!published) {
    tags.push('<meta name="robots" content="noindex, nofollow" />')
  }

  return tags.join('\n    ')
}

function robotsTxt(): string {
  if (process.env.VITE_APP_MODE !== 'published') {
    return 'User-agent: *\nDisallow: /\n'
  }
  return 'User-agent: *\nAllow: /\n\nSitemap: ' + siteUrl() + '/sitemap.xml\n'
}

function sitemapXml(): string {
  const url = siteUrl()
  const lastmod = new Date().toISOString().slice(0, 10)
  const urls = SITEMAP_PATHS.map(
    (path) => `  <url>\n    <loc>${url}${path === '/' ? '/' : path}</loc>\n    <lastmod>${lastmod}</lastmod>\n  </url>`,
  )
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join('\n')}\n</urlset>\n`
}

export function siteSeoPlugin(): Plugin {
  return {
    name: 'site-seo',
    transformIndexHtml(html) {
      return html.replace('<!--seo-->', seoHeadTags())
    },
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'robots.txt', source: robotsTxt() })
      if (process.env.VITE_APP_MODE === 'published') {
        this.emitFile({ type: 'asset', fileName: 'sitemap.xml', source: sitemapXml() })
      }
    },
  }
}
