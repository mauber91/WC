import { KNOCKOUT_HOST_COUNTRY, venueHomeBoost } from './knockoutVenues'

export type BracketRow = {
  match_number: number
  team_a_id: number
  team_b_id: number
  meeting_count: number
  matchup_probability: number
  team_a_advance_probability: number
}

export const KNOCKOUT_FEEDERS: Record<number, [number, number]> = {
  89: [74, 77], 90: [73, 75], 91: [76, 78], 92: [79, 80],
  93: [83, 84], 94: [81, 82], 95: [86, 88], 96: [85, 87],
  97: [89, 90], 98: [93, 94], 99: [91, 92], 100: [95, 96],
  101: [97, 98], 102: [99, 100], 104: [101, 102],
}

/** Process earlier feeders before downstream matches. */
export const BRACKET_MATCH_ORDER = [
  73, 75, 74, 77, 83, 84, 81, 82, 76, 78, 79, 80, 86, 88, 85, 87,
  90, 89, 93, 94, 91, 92, 95, 96,
  97, 98, 99, 100,
  101, 102,
  104,
] as const

/** Human labels for each side of a Round-of-32 slot (matches backend ROUND_32). */
export const R32_SLOT_SOURCES: Record<number, [string, string]> = {
  73: ['Group A 2nd', 'Group B 2nd'],
  74: ['Group E winner', '3rd place'],
  75: ['Group F winner', 'Group C 2nd'],
  76: ['Group C winner', 'Group F 2nd'],
  77: ['Group I winner', '3rd place'],
  78: ['Group E 2nd', 'Group I 2nd'],
  79: ['Group A winner', '3rd place'],
  80: ['Group L winner', '3rd place'],
  81: ['Group D winner', '3rd place'],
  82: ['Group G winner', '3rd place'],
  83: ['Group K 2nd', 'Group L 2nd'],
  84: ['Group H winner', 'Group J 2nd'],
  85: ['Group B winner', '3rd place'],
  86: ['Group J winner', 'Group H 2nd'],
  87: ['Group K winner', '3rd place'],
  88: ['Group D 2nd', 'Group G 2nd'],
}

export type R32SlotCandidate = {
  teamId: number
  probability: number
}

export type R32MatchSlotLeaders = {
  sideA: { label: string; candidates: R32SlotCandidate[] }
  sideB: { label: string; candidates: R32SlotCandidate[] }
}

export function topR32SideTeams(
  rows: BracketRow[],
  matchNumber: number,
  side: 'a' | 'b',
  iterations: number,
  limit = 3,
): R32SlotCandidate[] {
  if (iterations <= 0) return []

  const counts = new Map<number, number>()
  for (const row of rows) {
    if (row.match_number !== matchNumber) continue
    const teamId = side === 'a' ? row.team_a_id : row.team_b_id
    counts.set(teamId, (counts.get(teamId) ?? 0) + row.meeting_count)
  }

  return [...counts.entries()]
    .map(([teamId, count]) => ({ teamId, probability: count / iterations }))
    .sort((a, b) => b.probability - a.probability)
    .slice(0, limit)
}

export function buildR32SlotLeaderboards(
  rows: BracketRow[],
  iterations: number,
): Map<number, R32MatchSlotLeaders> {
  const output = new Map<number, R32MatchSlotLeaders>()
  for (const matchNumber of Object.keys(R32_SLOT_SOURCES).map(Number)) {
    const labels = R32_SLOT_SOURCES[matchNumber]
    const sideA = topR32SideTeams(rows, matchNumber, 'a', iterations)
    const sideB = topR32SideTeams(rows, matchNumber, 'b', iterations)
    if (sideA.length > 0 || sideB.length > 0) {
      output.set(matchNumber, {
        sideA: { label: labels[0], candidates: sideA },
        sideB: { label: labels[1], candidates: sideB },
      })
    }
  }
  return output
}

export type BracketTeam = { id: number; name: string; fifaCode: string; countryCode: string; advanceProb: number; homeBoost: boolean }

export type BracketMatch = {
  matchNumber: number
  matchupProbability: number
  hostCountry: string | null
  teamA: BracketTeam
  teamB: BracketTeam
  scheduledAt: string | null
}

export type PredictedR32Pairing = { teamAId: number; teamBId: number }

function samePairing(a1: number, a2: number, b1: number, b2: number): boolean {
  return (a1 === b1 && a2 === b2) || (a1 === b2 && a2 === b1)
}

function pickModalRowWithoutConflicts(
  rows: BracketRow[],
  usedTeams: ReadonlySet<number>,
): BracketRow | undefined {
  return [...rows]
    .sort((a, b) => b.meeting_count - a.meeting_count)
    .find(row => !usedTeams.has(row.team_a_id) && !usedTeams.has(row.team_b_id))
}

function pickRowForPairing(rows: BracketRow[], teamA: number, teamB: number): BracketRow | undefined {
  return rows
    .filter(row => samePairing(row.team_a_id, row.team_b_id, teamA, teamB))
    .sort((a, b) => b.meeting_count - a.meeting_count)[0]
}

function advanceProbabilityFor(row: BracketRow, teamId: number): number {
  if (row.team_a_id === teamId) return row.team_a_advance_probability
  if (row.team_b_id === teamId) return 1 - row.team_a_advance_probability
  return 0.5
}

function projectedWinnerId(row: BracketRow): number {
  return row.team_a_advance_probability >= 0.5 ? row.team_a_id : row.team_b_id
}

export function buildCoherentMatchMap(
  rows: BracketRow[],
  teams: Array<{ id: number; fifa_code: string; name: string; country_code: string }>,
  schedule: Record<number, string>,
  predictedR32?: Map<number, PredictedR32Pairing>,
): Map<number, BracketMatch> {
  const teamById = new Map(teams.map(team => [team.id, team]))
  const grouped = new Map<number, BracketRow[]>()
  for (const row of rows) {
    const bucket = grouped.get(row.match_number) ?? []
    bucket.push(row)
    grouped.set(row.match_number, bucket)
  }

  const winners = new Map<number, number>()
  const output = new Map<number, BracketMatch>()
  const usedR32Teams = new Set<number>()

  for (const matchNumber of BRACKET_MATCH_ORDER) {
    const matchRows = grouped.get(matchNumber)
    if (!matchRows?.length) continue

    const feeders = KNOCKOUT_FEEDERS[matchNumber]
    let teamAId: number
    let teamBId: number
    let sourceRow: BracketRow | undefined
    let advanceA: number
    let matchupProbability: number

    if (!feeders) {
      const predicted = predictedR32?.get(matchNumber)
      if (predicted) {
        teamAId = predicted.teamAId
        teamBId = predicted.teamBId
        sourceRow = pickRowForPairing(matchRows, teamAId, teamBId)
        advanceA = sourceRow ? advanceProbabilityFor(sourceRow, teamAId) : 0.5
        matchupProbability = sourceRow?.matchup_probability ?? 0
        winners.set(matchNumber, advanceA >= 0.5 ? teamAId : teamBId)
      } else {
        sourceRow = pickModalRowWithoutConflicts(matchRows, usedR32Teams)
        if (!sourceRow) continue
        teamAId = sourceRow.team_a_id
        teamBId = sourceRow.team_b_id
        usedR32Teams.add(teamAId)
        usedR32Teams.add(teamBId)
        advanceA = sourceRow.team_a_advance_probability
        matchupProbability = sourceRow.matchup_probability
        winners.set(matchNumber, projectedWinnerId(sourceRow))
      }
    } else {
      const feederA = winners.get(feeders[0])
      const feederB = winners.get(feeders[1])
      if (feederA == null || feederB == null) continue

      teamAId = feederA
      teamBId = feederB
      sourceRow = pickRowForPairing(matchRows, teamAId, teamBId)
      advanceA = sourceRow ? advanceProbabilityFor(sourceRow, teamAId) : 0.5
      matchupProbability = sourceRow?.matchup_probability ?? 0
      winners.set(matchNumber, advanceA >= 0.5 ? teamAId : teamBId)
    }

    const teamA = teamById.get(teamAId)
    const teamB = teamById.get(teamBId)
    if (!teamA || !teamB) continue

    const hostCountry = KNOCKOUT_HOST_COUNTRY[matchNumber] ?? null

    output.set(matchNumber, {
      matchNumber,
      matchupProbability,
      hostCountry,
      teamA: {
        id: teamA.id,
        name: teamA.name,
        fifaCode: teamA.fifa_code,
        countryCode: teamA.country_code,
        advanceProb: advanceA,
        homeBoost: venueHomeBoost(teamA.country_code, matchNumber),
      },
      teamB: {
        id: teamB.id,
        name: teamB.name,
        fifaCode: teamB.fifa_code,
        countryCode: teamB.country_code,
        advanceProb: 1 - advanceA,
        homeBoost: venueHomeBoost(teamB.country_code, matchNumber),
      },
      scheduledAt: schedule[matchNumber] ?? null,
    })
  }

  return output
}
