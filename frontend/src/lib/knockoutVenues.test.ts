import { describe, expect, it } from 'vitest'
import { venueHomeBoost } from './knockoutVenues'

describe('venueHomeBoost', () => {
  it('gives Mexico a boost in Mexico City (M79) but not Los Angeles (M73)', () => {
    expect(venueHomeBoost('MX', 79)).toBe(true)
    expect(venueHomeBoost('MX', 73)).toBe(false)
  })

  it('gives USA and Canada boosts only in their host countries', () => {
    expect(venueHomeBoost('US', 89)).toBe(true)
    expect(venueHomeBoost('CA', 83)).toBe(true)
    expect(venueHomeBoost('US', 83)).toBe(false)
  })
})
