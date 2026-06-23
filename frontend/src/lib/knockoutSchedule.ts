import knockoutCsv from '../../../data/seed/knockout_fixtures.csv?raw'

/** Official knockout kickoffs — sourced from data/seed/knockout_fixtures.csv (FIFA calendar). */
export function parseKnockoutSchedule(csv: string): Record<number, string> {
  const schedule: Record<number, string> = {}
  for (const line of csv.trim().split('\n').slice(1)) {
    const [matchNumber, scheduledAt] = line.split(',', 2)
    if (!matchNumber || !scheduledAt) continue
    schedule[Number(matchNumber)] = scheduledAt
  }
  return schedule
}

export const KNOCKOUT_SCHEDULE = parseKnockoutSchedule(knockoutCsv)
