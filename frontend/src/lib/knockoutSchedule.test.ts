import { describe, expect, it } from 'vitest'
import { KNOCKOUT_SCHEDULE } from './knockoutSchedule'

/** Kickoffs from FIFA calendar API (api.fifa.com), 2026-06-23. */
const FIFA_KNOCKOUT_UTC: Record<number, string> = {
  73: '2026-06-28T19:00:00Z',
  86: '2026-07-03T22:00:00Z',
  90: '2026-07-04T17:00:00Z',
  94: '2026-07-07T00:00:00Z',
  104: '2026-07-19T19:00:00Z',
}

describe('KNOCKOUT_SCHEDULE', () => {
  it('matches FIFA calendar kickoffs for sample knockout matches', () => {
    for (const [matchNumber, kickoff] of Object.entries(FIFA_KNOCKOUT_UTC)) {
      expect(KNOCKOUT_SCHEDULE[Number(matchNumber)]).toBe(kickoff)
    }
  })

  it('includes all knockout matches through the final', () => {
    expect(Object.keys(KNOCKOUT_SCHEDULE).map(Number).sort((a, b) => a - b)).toEqual([
      ...Array.from({ length: 32 }, (_, index) => index + 73),
    ])
  })
})
