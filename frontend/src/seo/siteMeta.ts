export const SITE_NAME = 'WC Knockout Predictor'
export const SITE_SHORT_NAME = 'Knockout Predictor'
export const SITE_DESCRIPTION =
  'Monte Carlo knockout forecasts, live bracket projections, and calibrated match probabilities for FIFA World Cup 2026.'
export const SITE_THEME_COLOR = '#153d2b'
export const DEFAULT_SITE_URL = 'https://wc-forecast.pages.dev'

export const SITEMAP_PATHS = [
  '/',
  '/bracket',
  '/groups/A',
  '/matches',
  '/teams',
  '/methodology',
  '/scenario',
] as const

export const ROUTE_PAGE_TITLES: Array<{ prefix: string; title: string }> = [
  { prefix: '/matches/', title: 'Match detail' },
  { prefix: '/teams/', title: 'Team' },
  { prefix: '/groups/', title: 'Group' },
  { prefix: '/bracket', title: 'Projected bracket' },
  { prefix: '/matches', title: 'Match predictions' },
  { prefix: '/teams', title: 'Teams' },
  { prefix: '/methodology', title: 'Methodology' },
  { prefix: '/scenario', title: 'Knockout Builder' },
  { prefix: '/simulator', title: 'Tournament simulator' },
  { prefix: '/admin', title: 'Admin' },
]

export function pageTitleForPath(pathname: string): string | undefined {
  const match = ROUTE_PAGE_TITLES.find(({ prefix }) => pathname.startsWith(prefix))
  return match?.title
}

export function documentTitle(pageTitle?: string): string {
  return pageTitle ? `${pageTitle} · ${SITE_NAME}` : SITE_NAME
}
