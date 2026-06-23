import { describe, expect, it } from 'vitest'
import { teamSlug } from './teamSlug'

describe('teamSlug', () => {
  it('slugifies team names for routes', () => {
    expect(teamSlug('Mexico')).toBe('mexico')
    expect(teamSlug('Korea Republic')).toBe('korea-republic')
  })
})
