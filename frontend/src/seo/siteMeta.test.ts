import { describe, expect, it } from 'vitest'
import { documentTitle, pageTitleForPath } from './siteMeta'

describe('siteMeta', () => {
  it('builds document titles', () => {
    expect(documentTitle()).toBe('WC Knockout Predictor')
    expect(documentTitle('Projected bracket')).toBe('Projected bracket · WC Knockout Predictor')
  })

  it('resolves route page titles', () => {
    expect(pageTitleForPath('/bracket')).toBe('Projected bracket')
    expect(pageTitleForPath('/teams/argentina')).toBe('Team')
    expect(pageTitleForPath('/groups/B')).toBe('Group')
  })
})
