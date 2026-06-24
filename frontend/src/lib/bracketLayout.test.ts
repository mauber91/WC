import { describe, expect, it } from 'vitest'
import {
  BRACKET_GRID_ROWS,
  BRACKET_LEAF_PAIRS,
  FINAL_SLOT,
  JOIN_R32_R16,
  R16_SLOTS,
  R32_SLOTS,
} from './bracketLayout'

describe('bracketLayout', () => {
  it('inserts a gap row between feeder pairs in the Round of 32', () => {
    const m75 = R32_SLOTS.find(slot => slot.match === 75)!
    const m74 = R32_SLOTS.find(slot => slot.match === 74)!
    expect(m74.row - m75.row).toBe(2)
  })

  it('keeps joins aligned with their feeder pair rows', () => {
    expect(JOIN_R32_R16[0]).toEqual({ row: 1, span: 2 })
    expect(JOIN_R32_R16[1]).toEqual({ row: 4, span: 2 })
  })

  it('offsets later rounds to follow the widened leaf layout', () => {
    expect(R16_SLOTS[1]).toEqual({ match: 89, row: 4, span: 2 })
    expect(FINAL_SLOT.span).toBe(BRACKET_LEAF_PAIRS * 3 - 1)
    expect(BRACKET_GRID_ROWS).toBe(23)
  })
})
