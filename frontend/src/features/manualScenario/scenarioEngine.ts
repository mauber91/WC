import annexCsv from '../../data/annex_c.csv?raw'
import ratingsCsv from '../../data/ratings.csv?raw'
import resultsCsv from '../../data/results.csv?raw'
import { BRACKET_MATCH_ORDER, KNOCKOUT_FEEDERS } from '../../lib/bracketPath'

export type ScenarioTeam = {
  id: number
  fifa_code: string
  name: string
}

export type ScenarioGroup = {
  id: number
  code: string
  display_name: string
  teams: ScenarioTeam[]
}

export type ScenarioMatch = {
  id: number
  official_match_number: number
  stage: string
  group_code: string | null
  team_a: ScenarioTeam | null
  team_b: ScenarioTeam | null
  scheduled_at: string
  status: string
  result?: { team_a_goals: number; team_b_goals: number; revision: number } | null
}

export type ManualScore = { team_a_goals: number | null; team_b_goals: number | null }
export type ManualScores = Record<string, ManualScore>

type MatchRecord = {
  teamAId: number
  teamBId: number
  goalsA: number
  goalsB: number
  conductA: number | null
  conductB: number | null
}

export type ScenarioStanding = {
  team: ScenarioTeam
  played: number
  won: number
  drawn: number
  lost: number
  goalsFor: number
  goalsAgainst: number
  goalDifference: number
  points: number
  conductScore: number | null
  fifaRank: number | null
  position: number
}

export type ScenarioGroupTable = {
  code: string
  rows: ScenarioStanding[]
  complete: boolean
  warnings: string[]
}

export type ScenarioBracketMatch = {
  matchNumber: number
  teamA: ScenarioTeam
  teamB: ScenarioTeam
  sourceA: string
  sourceB: string
}

export type KnockoutPicks = Record<string, number>

export type ResolvedKnockoutMatch = {
  matchNumber: number
  teamA: ScenarioTeam | null
  teamB: ScenarioTeam | null
  winnerId: number | null
  sourceA?: string
  sourceB?: string
  pendingFeeders?: number[]
}

export type ScenarioOutcome = {
  tables: ScenarioGroupTable[]
  thirdPlace: ScenarioStanding[]
  bracket: ScenarioBracketMatch[] | null
  remainingMatches: ScenarioMatch[]
  enteredCount: number
  totalRemaining: number
  warnings: string[]
}

const ROUND_OF_32: Record<number, [[string, string], [string, string]]> = {
  73: [['runner', 'A'], ['runner', 'B']],
  74: [['winner', 'E'], ['third', '74']],
  75: [['winner', 'F'], ['runner', 'C']],
  76: [['winner', 'C'], ['runner', 'F']],
  77: [['winner', 'I'], ['third', '77']],
  78: [['runner', 'E'], ['runner', 'I']],
  79: [['winner', 'A'], ['third', '79']],
  80: [['winner', 'L'], ['third', '80']],
  81: [['winner', 'D'], ['third', '81']],
  82: [['winner', 'G'], ['third', '82']],
  83: [['runner', 'K'], ['runner', 'L']],
  84: [['winner', 'H'], ['runner', 'J']],
  85: [['winner', 'B'], ['third', '85']],
  86: [['winner', 'J'], ['runner', 'H']],
  87: [['winner', 'K'], ['third', '87']],
  88: [['runner', 'D'], ['runner', 'G']],
}

const FIFA_RANKS = parseFifaRanks(ratingsCsv)
const OFFICIAL_CONDUCT = parseOfficialConduct(resultsCsv)
const THIRD_PLACE_ASSIGNMENTS = parseAnnexC(annexCsv)

function parseRows(csv: string): Record<string, string>[] {
  const lines = csv.trim().split(/\r?\n/)
  const headers = lines[0].split(',')
  return lines.slice(1).filter(Boolean).map(line => {
    const values = line.split(',')
    return Object.fromEntries(headers.map((header, index) => [header, values[index] ?? '']))
  })
}

function parseFifaRanks(csv: string): Map<string, number> {
  return new Map(
    parseRows(csv)
      .filter(row => row.rating_type === 'FIFA_RANK' && row.rank)
      .map(row => [row.fifa_code, Number(row.rank)]),
  )
}

function conductScore(row: Record<string, string>, side: 'a' | 'b'): number {
  const value = (field: string) => Number(row[`team_${side}_${field}`] || 0)
  return -(
    value('yellows')
    + 3 * value('indirect_reds')
    + 4 * value('direct_reds')
    + 5 * value('yellow_direct_reds')
  )
}

function parseOfficialConduct(csv: string): Map<number, [number, number]> {
  return new Map(
    parseRows(csv).map(row => [
      Number(row.match_number),
      [conductScore(row, 'a'), conductScore(row, 'b')],
    ]),
  )
}

function parseAnnexC(csv: string): Map<string, Map<number, string>> {
  const output = new Map<string, Map<number, string>>()
  for (const row of parseRows(csv)) {
    const groupSet = row.qualified_group_set
    const assignments = output.get(groupSet) ?? new Map<number, string>()
    assignments.set(Number(row.target_match_number), row.third_place_group_code)
    output.set(groupSet, assignments)
  }
  return output
}

export function isCompleteScore(score: ManualScore | undefined): score is { team_a_goals: number; team_b_goals: number } {
  return score != null
    && Number.isInteger(score.team_a_goals)
    && Number.isInteger(score.team_b_goals)
    && Number(score.team_a_goals) >= 0
    && Number(score.team_b_goals) >= 0
  
}

function createStanding(team: ScenarioTeam): ScenarioStanding {
  return {
    team,
    played: 0,
    won: 0,
    drawn: 0,
    lost: 0,
    goalsFor: 0,
    goalsAgainst: 0,
    goalDifference: 0,
    points: 0,
    conductScore: 0,
    fifaRank: FIFA_RANKS.get(team.fifa_code) ?? null,
    position: 0,
  }
}

function addConduct(current: number | null, value: number | null): number | null {
  return current == null || value == null ? null : current + value
}

function applyMatch(rows: Map<number, ScenarioStanding>, match: MatchRecord): void {
  const a = rows.get(match.teamAId)
  const b = rows.get(match.teamBId)
  if (!a || !b) return
  a.played += 1
  b.played += 1
  a.goalsFor += match.goalsA
  a.goalsAgainst += match.goalsB
  b.goalsFor += match.goalsB
  b.goalsAgainst += match.goalsA
  if (match.goalsA > match.goalsB) {
    a.won += 1
    b.lost += 1
    a.points += 3
  } else if (match.goalsB > match.goalsA) {
    b.won += 1
    a.lost += 1
    b.points += 3
  } else {
    a.drawn += 1
    b.drawn += 1
    a.points += 1
    b.points += 1
  }
  a.goalDifference = a.goalsFor - a.goalsAgainst
  b.goalDifference = b.goalsFor - b.goalsAgainst
  a.conductScore = addConduct(a.conductScore, match.conductA)
  b.conductScore = addConduct(b.conductScore, match.conductB)
}

function partitionBy<T>(values: T[], key: (value: T) => string | number): T[][] {
  const output: T[][] = []
  for (const value of values) {
    const last = output.at(-1)
    if (last && key(last[0]) === key(value)) last.push(value)
    else output.push([value])
  }
  return output
}

function headToHeadStats(teamIds: number[], matches: MatchRecord[]): Map<number, [number, number, number]> {
  const selected = new Set(teamIds)
  const stats = new Map(teamIds.map(teamId => [teamId, [0, 0, 0] as [number, number, number]]))
  for (const match of matches) {
    if (!selected.has(match.teamAId) || !selected.has(match.teamBId)) continue
    const a = stats.get(match.teamAId)!
    const b = stats.get(match.teamBId)!
    a[1] += match.goalsA - match.goalsB
    b[1] += match.goalsB - match.goalsA
    a[2] += match.goalsA
    b[2] += match.goalsB
    if (match.goalsA > match.goalsB) a[0] += 3
    else if (match.goalsB > match.goalsA) b[0] += 3
    else { a[0] += 1; b[0] += 1 }
  }
  return stats
}

function compareTupleDesc(a: number[], b: number[]): number {
  for (let index = 0; index < Math.max(a.length, b.length); index += 1) {
    const difference = (b[index] ?? 0) - (a[index] ?? 0)
    if (difference) return difference
  }
  return 0
}

function resolveHeadToHead(teamIds: number[], matches: MatchRecord[]): number[][] {
  if (teamIds.length <= 1) return [teamIds]
  const stats = headToHeadStats(teamIds, matches)
  const ordered = [...teamIds].sort((a, b) => compareTupleDesc(stats.get(a)!, stats.get(b)!))
  const partitions = partitionBy(ordered, teamId => stats.get(teamId)!.join(':'))
  if (partitions.length === 1) return [teamIds]
  return partitions.flatMap(partition => partition.length === 1 ? [partition] : resolveHeadToHead(partition, matches))
}

function resolveConductAndRank(rows: ScenarioStanding[], warnings: Set<string>): ScenarioStanding[] {
  if (rows.length <= 1) return rows
  let partitions: ScenarioStanding[][] = [rows]
  if (rows.every(row => row.conductScore != null)) {
    const ordered = [...rows].sort((a, b) => Number(b.conductScore) - Number(a.conductScore))
    partitions = partitionBy(ordered, row => Number(row.conductScore))
  } else {
    warnings.add('Fair-play totals are unavailable for a tied scenario; FIFA ranking resolved the tie.')
  }
  return partitions.flatMap(partition => {
    if (partition.length <= 1) return partition
    const allRanked = partition.every(row => row.fifaRank != null)
    if (!allRanked) warnings.add('A tied scenario lacked complete FIFA ranking data; team code was the final fallback.')
    return [...partition].sort((a, b) =>
      (a.fifaRank ?? Number.MAX_SAFE_INTEGER) - (b.fifaRank ?? Number.MAX_SAFE_INTEGER)
      || a.team.fifa_code.localeCompare(b.team.fifa_code),
    )
  })
}

function resolveOverall(rows: ScenarioStanding[], warnings: Set<string>): ScenarioStanding[] {
  const ordered = [...rows].sort((a, b) =>
    b.goalDifference - a.goalDifference || b.goalsFor - a.goalsFor,
  )
  return partitionBy(ordered, row => `${row.goalDifference}:${row.goalsFor}`)
    .flatMap(partition => resolveConductAndRank(partition, warnings))
}

function rankGroup(teams: ScenarioTeam[], matches: MatchRecord[]): { rows: ScenarioStanding[]; warnings: string[] } {
  const rowMap = new Map(teams.map(team => [team.id, createStanding(team)]))
  matches.forEach(match => applyMatch(rowMap, match))
  const warnings = new Set<string>()
  const byPoints = [...rowMap.values()].sort((a, b) => b.points - a.points)
  const ordered = partitionBy(byPoints, row => row.points).flatMap(tied => {
    if (tied.length === 1) return tied
    const partitions = resolveHeadToHead(tied.map(row => row.team.id), matches)
    return partitions.flatMap(partition => resolveOverall(partition.map(teamId => rowMap.get(teamId)!), warnings))
  })
  ordered.forEach((row, index) => { row.position = index + 1 })
  return { rows: ordered, warnings: [...warnings] }
}

function rankThirdPlace(rows: ScenarioStanding[]): { rows: ScenarioStanding[]; warnings: string[] } {
  const warnings = new Set<string>()
  // Third-place positions are separate from group positions. Clone the rows so
  // assigning 1–12 here cannot overwrite their 1–4 group rank.
  const ordered = rows.map(row => ({ ...row })).sort((a, b) =>
    b.points - a.points
    || b.goalDifference - a.goalDifference
    || b.goalsFor - a.goalsFor,
  )
  const resolved = partitionBy(ordered, row => `${row.points}:${row.goalDifference}:${row.goalsFor}`)
    .flatMap(partition => resolveConductAndRank(partition, warnings))
  resolved.forEach((row, index) => { row.position = index + 1 })
  return { rows: resolved, warnings: [...warnings] }
}

function matchRecord(match: ScenarioMatch, manualScores: ManualScores): MatchRecord | null {
  if (!match.team_a || !match.team_b) return null
  if (match.result) {
    const conduct = OFFICIAL_CONDUCT.get(match.official_match_number) ?? [null, null]
    return {
      teamAId: match.team_a.id,
      teamBId: match.team_b.id,
      goalsA: match.result.team_a_goals,
      goalsB: match.result.team_b_goals,
      conductA: conduct[0],
      conductB: conduct[1],
    }
  }
  const score = manualScores[String(match.official_match_number)]
  if (!isCompleteScore(score)) return null
  return {
    teamAId: match.team_a.id,
    teamBId: match.team_b.id,
    goalsA: score.team_a_goals,
    goalsB: score.team_b_goals,
    conductA: null,
    conductB: null,
  }
}

function sourceTeam(
  source: [string, string],
  tables: Map<string, ScenarioGroupTable>,
  assignments: Map<number, string>,
): { team: ScenarioTeam; label: string } {
  const [kind, reference] = source
  if (kind === 'third') {
    const groupCode = assignments.get(Number(reference))
    const team = groupCode ? tables.get(groupCode)?.rows[2]?.team : undefined
    if (!team || !groupCode) throw new Error(`Missing third-place assignment for M${reference}`)
    return { team, label: `Group ${groupCode} third` }
  }
  const table = tables.get(reference)
  const row = kind === 'winner' ? table?.rows[0] : table?.rows[1]
  if (!row) throw new Error(`Missing ${kind} for Group ${reference}`)
  return { team: row.team, label: `Group ${reference} ${kind}` }
}

export function resolveRoundOf32Bracket(tables: ScenarioGroupTable[]): ScenarioBracketMatch[] {
  const rankedThird = rankThirdPlace(tables.map(table => table.rows[2]))
  return buildRoundOf32(tables, rankedThird.rows)
}

export type SimulationGroupOutcome = {
  group_id: number
  order: number[]
  count: number
  probability: number
}

export type TeamGroupStats = {
  team_id: number
  expected_group_points: number
  expected_group_goals_for: number
  expected_group_goals_against: number
}

export function buildPredictedRoundOf32(
  groups: ScenarioGroup[],
  groupOutcomes: SimulationGroupOutcome[],
  teamStats: TeamGroupStats[],
): ScenarioBracketMatch[] | null {
  const statsById = new Map(teamStats.map(stat => [stat.team_id, stat]))
  const bestByGroupId = new Map<number, SimulationGroupOutcome>()
  for (const row of groupOutcomes) {
    const previous = bestByGroupId.get(row.group_id)
    if (!previous || row.count > previous.count) bestByGroupId.set(row.group_id, row)
  }

  const tables: ScenarioGroupTable[] = groups.map(group => {
    const best = bestByGroupId.get(group.id)
    const order = best?.order ?? group.teams.map(team => team.id)
    const teamById = new Map(group.teams.map(team => [team.id, team]))
    const rows = order.map((teamId, index) => {
      const team = teamById.get(teamId)
      if (!team) throw new Error(`Team ${teamId} missing from group ${group.code}`)
      const stats = statsById.get(teamId)
      const goalsFor = stats?.expected_group_goals_for ?? 0
      const goalsAgainst = stats?.expected_group_goals_against ?? 0
      return {
        team,
        position: index + 1,
        played: 3,
        won: 0,
        drawn: 0,
        lost: 0,
        goalsFor,
        goalsAgainst,
        goalDifference: goalsFor - goalsAgainst,
        points: stats?.expected_group_points ?? 0,
        conductScore: null,
        fifaRank: FIFA_RANKS.get(team.fifa_code) ?? null,
      } satisfies ScenarioStanding
    })
    return { code: group.code, rows, complete: true, warnings: [] }
  })

  try {
    return resolveRoundOf32Bracket(tables)
  } catch {
    return null
  }
}

function buildRoundOf32(tables: ScenarioGroupTable[], thirdPlace: ScenarioStanding[]): ScenarioBracketMatch[] {
  const groupSet = thirdPlace.slice(0, 8)
    .map(row => tables.find(table => table.rows.some(candidate => candidate.team.id === row.team.id))?.code)
    .filter((code): code is string => Boolean(code))
    .sort()
    .join('')
  const assignments = THIRD_PLACE_ASSIGNMENTS.get(groupSet)
  if (!assignments) throw new Error(`No Annex C assignment for qualifying groups ${groupSet}`)
  const tableMap = new Map(tables.map(table => [table.code, table]))
  return Object.entries(ROUND_OF_32)
    .map(([matchNumber, [sourceA, sourceB]]) => {
      const a = sourceTeam(sourceA, tableMap, assignments)
      const b = sourceTeam(sourceB, tableMap, assignments)
      return {
        matchNumber: Number(matchNumber),
        teamA: a.team,
        teamB: b.team,
        sourceA: a.label,
        sourceB: b.label,
      }
    })
    .sort((a, b) => a.matchNumber - b.matchNumber)
}

export function calculateScenario(
  groups: ScenarioGroup[],
  matches: ScenarioMatch[],
  manualScores: ManualScores,
): ScenarioOutcome {
  const groupMatches = matches.filter(match => match.group_code && match.team_a && match.team_b)
  const remainingMatches = groupMatches.filter(match => !match.result)
  const enteredCount = remainingMatches.filter(match =>
    isCompleteScore(manualScores[String(match.official_match_number)]),
  ).length
  const tables = groups.map(group => {
    const matchesForGroup = groupMatches.filter(match => match.group_code === group.code)
    const records = matchesForGroup
      .map(match => matchRecord(match, manualScores))
      .filter((record): record is MatchRecord => record != null)
    const ranked = rankGroup(group.teams, records)
    return {
      code: group.code,
      rows: ranked.rows,
      complete: records.length === matchesForGroup.length,
      warnings: ranked.warnings,
    }
  })
  const rankedThird = rankThirdPlace(tables.map(table => table.rows[2]))
  const complete = enteredCount === remainingMatches.length && tables.every(table => table.complete)
  const warnings = [...new Set([
    ...tables.flatMap(table => table.warnings),
    ...rankedThird.warnings,
  ])]
  let bracket: ScenarioBracketMatch[] | null = null
  if (complete) {
    try {
      bracket = buildRoundOf32(tables, rankedThird.rows)
    } catch (error) {
      warnings.push(error instanceof Error ? error.message : 'The Round-of-32 bracket could not be assigned.')
    }
  }
  return {
    tables,
    thirdPlace: rankedThird.rows,
    bracket,
    remainingMatches,
    enteredCount,
    totalRemaining: remainingMatches.length,
    warnings,
  }
}

export function annexCombinationCount(): number {
  return THIRD_PLACE_ASSIGNMENTS.size
}

export function resolveKnockoutBracket(
  r32Matches: ScenarioBracketMatch[],
  picks: KnockoutPicks,
): Map<number, ResolvedKnockoutMatch> {
  const r32Map = new Map(r32Matches.map(match => [match.matchNumber, match]))
  const teamsById = new Map<number, ScenarioTeam>()
  for (const match of r32Matches) {
    teamsById.set(match.teamA.id, match.teamA)
    teamsById.set(match.teamB.id, match.teamB)
  }

  const winners = new Map<number, number>()
  const output = new Map<number, ResolvedKnockoutMatch>()

  for (const matchNumber of BRACKET_MATCH_ORDER) {
    const feeders = KNOCKOUT_FEEDERS[matchNumber]
    let teamA: ScenarioTeam | null = null
    let teamB: ScenarioTeam | null = null
    let sourceA: string | undefined
    let sourceB: string | undefined
    const pendingFeeders: number[] = []

    if (!feeders) {
      const r32 = r32Map.get(matchNumber)
      if (!r32) continue
      teamA = r32.teamA
      teamB = r32.teamB
      sourceA = r32.sourceA
      sourceB = r32.sourceB
    } else {
      const winnerA = winners.get(feeders[0])
      const winnerB = winners.get(feeders[1])
      if (winnerA == null) pendingFeeders.push(feeders[0])
      else teamA = teamsById.get(winnerA) ?? null
      if (winnerB == null) pendingFeeders.push(feeders[1])
      else teamB = teamsById.get(winnerB) ?? null
    }

    const pick = picks[String(matchNumber)] ?? null
    let winnerId: number | null = null
    if (teamA && teamB && pick != null && (pick === teamA.id || pick === teamB.id)) {
      winnerId = pick
      winners.set(matchNumber, pick)
    }

    output.set(matchNumber, {
      matchNumber,
      teamA,
      teamB,
      winnerId,
      sourceA,
      sourceB,
      pendingFeeders: pendingFeeders.length ? pendingFeeders : undefined,
    })
  }

  return output
}

export function sanitizeKnockoutPicks(
  r32Matches: ScenarioBracketMatch[],
  picks: KnockoutPicks,
): KnockoutPicks {
  const clean: KnockoutPicks = {}
  const winners = new Map<number, number>()
  const r32Map = new Map(r32Matches.map(match => [match.matchNumber, match]))
  const teamsById = new Map<number, ScenarioTeam>()
  for (const match of r32Matches) {
    teamsById.set(match.teamA.id, match.teamA)
    teamsById.set(match.teamB.id, match.teamB)
  }

  for (const matchNumber of BRACKET_MATCH_ORDER) {
    const feeders = KNOCKOUT_FEEDERS[matchNumber]
    let teamA: ScenarioTeam | null = null
    let teamB: ScenarioTeam | null = null

    if (!feeders) {
      const r32 = r32Map.get(matchNumber)
      if (!r32) continue
      teamA = r32.teamA
      teamB = r32.teamB
    } else {
      const winnerA = winners.get(feeders[0])
      const winnerB = winners.get(feeders[1])
      if (winnerA == null || winnerB == null) continue
      teamA = teamsById.get(winnerA) ?? null
      teamB = teamsById.get(winnerB) ?? null
      if (!teamA || !teamB) continue
    }

    const pick = picks[String(matchNumber)]
    if (pick == null) continue
    if (pick !== teamA.id && pick !== teamB.id) continue
    clean[String(matchNumber)] = pick
    winners.set(matchNumber, pick)
  }

  return clean
}

export function applyKnockoutPick(
  r32Matches: ScenarioBracketMatch[],
  picks: KnockoutPicks,
  matchNumber: number,
  teamId: number,
): KnockoutPicks {
  const resolved = resolveKnockoutBracket(r32Matches, picks)
  const match = resolved.get(matchNumber)
  if (!match?.teamA || !match?.teamB) return picks
  if (teamId !== match.teamA.id && teamId !== match.teamB.id) return picks

  const key = String(matchNumber)
  const next = { ...picks }
  if (next[key] === teamId) delete next[key]
  else next[key] = teamId

  return sanitizeKnockoutPicks(r32Matches, next)
}
