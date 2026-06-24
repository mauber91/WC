import { describe, expect, it } from 'vitest'
import { KNOCKOUT_FIXTURES, KNOCKOUT_SCHEDULE, formatKnockoutKickoff, getKnockoutFixture } from './knockoutSchedule'

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

  it('includes venue metadata for each knockout match', () => {
    expect(getKnockoutFixture(104)).toEqual({
      scheduledAt: '2026-07-19T19:00:00Z',
      venue: 'MetLife Stadium',
      hostCountry: 'US',
    })
  })

  it('formats kickoff day, time, date, and venue', () => {
    const label = formatKnockoutKickoff('2026-07-19T19:00:00Z', 104)
    expect(label.day).toMatch(/^(SUN|MON|TUE|WED|THU|FRI|SAT)$/)
    expect(label.time).toMatch(/^\d{2}:\d{2}$/)
    expect(label.date).toMatch(/19/)
    expect(label.venue).toBe('MetLife Stadium')
  })

  it('keeps schedule and fixtures in sync', () => {
    for (const [matchNumber, fixture] of Object.entries(KNOCKOUT_FIXTURES)) {
      expect(KNOCKOUT_SCHEDULE[Number(matchNumber)]).toBe(fixture.scheduledAt)
    }
  })
})
