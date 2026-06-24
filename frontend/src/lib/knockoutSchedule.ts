import knockoutCsv from '../../../data/seed/knockout_fixtures.csv?raw'

export type KnockoutFixture = {
  scheduledAt: string
  venue: string
  hostCountry: string
}

/** Official knockout fixtures — sourced from data/seed/knockout_fixtures.csv (FIFA calendar). */
export function parseKnockoutFixtures(csv: string): Record<number, KnockoutFixture> {
  const fixtures: Record<number, KnockoutFixture> = {}
  for (const line of csv.trim().split('\n').slice(1)) {
    const [matchNumber, scheduledAt, venue, hostCountry] = line.split(',', 4)
    if (!matchNumber || !scheduledAt) continue
    fixtures[Number(matchNumber)] = {
      scheduledAt,
      venue: venue ?? '',
      hostCountry: hostCountry ?? '',
    }
  }
  return fixtures
}

export const KNOCKOUT_FIXTURES = parseKnockoutFixtures(knockoutCsv)

export const KNOCKOUT_SCHEDULE: Record<number, string> = Object.fromEntries(
  Object.entries(KNOCKOUT_FIXTURES).map(([matchNumber, fixture]) => [Number(matchNumber), fixture.scheduledAt]),
)

export function getKnockoutFixture(matchNumber: number): KnockoutFixture | undefined {
  return KNOCKOUT_FIXTURES[matchNumber]
}

export type KnockoutKickoffLabel = {
  day: string
  time: string
  date: string
  venue: string | null
}

export function formatKnockoutKickoff(
  scheduledAt: string | null | undefined,
  matchNumber: number,
): KnockoutKickoffLabel {
  const fixture = getKnockoutFixture(matchNumber)
  const iso = scheduledAt ?? fixture?.scheduledAt
  if (!iso) {
    return { day: 'TBD', time: '—', date: `M${matchNumber}`, venue: fixture?.venue ?? null }
  }
  const date = new Date(iso)
  return {
    day: date.toLocaleDateString(undefined, { weekday: 'short' }).toUpperCase(),
    time: date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false }),
    date: date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }).toUpperCase(),
    venue: fixture?.venue ?? null,
  }
}
