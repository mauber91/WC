import { describe, expect, it } from 'vitest'
import { percent } from './client'

describe('percent', () => {
  it('formats normal and small probabilities', () => {
    expect(percent(0.612)).toBe('61%')
    expect(percent(0.004)).toBe('0.4%')
  })
})
