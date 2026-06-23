import { describe, expect, it } from 'vitest'
import { percent } from './client'

describe('percent', () => {
  it('formats normal and small probabilities', () => {
    expect(percent(0.612)).toBe('61%')
    expect(percent(0.004)).toBe('0.4%')
  })

  it('supports explicit precision for near-certain slot shares', () => {
    expect(percent(0.996, 2)).toBe('99.60%')
    expect(percent(0.004, 2)).toBe('0.40%')
  })
})
