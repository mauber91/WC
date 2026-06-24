import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { documentTitle, pageTitleForPath, SITE_DESCRIPTION } from './siteMeta'

function upsertMeta(name: string, content: string, attribute: 'name' | 'property' = 'name') {
  const selector = `meta[${attribute}="${name}"]`
  let element = document.head.querySelector(selector)
  if (!element) {
    element = document.createElement('meta')
    element.setAttribute(attribute, name)
    document.head.appendChild(element)
  }
  element.setAttribute('content', content)
}

export function RouteSeo() {
  const { pathname } = useLocation()

  useEffect(() => {
    const pageTitle = pageTitleForPath(pathname)
    document.title = documentTitle(pageTitle)
    upsertMeta('description', SITE_DESCRIPTION)
    upsertMeta('og:title', document.title, 'property')
    upsertMeta('twitter:title', document.title)
  }, [pathname])

  return null
}
