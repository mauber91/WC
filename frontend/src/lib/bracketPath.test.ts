import { describe, expect, it } from 'vitest'
import { buildCoherentMatchMap, topR32SideTeams, type BracketRow } from './bracketPath'

const teams = [
  { id: 1, fifa_code: 'KOR', name: 'Korea Republic', country_code: 'KR' },
  { id: 2, fifa_code: 'SUI', name: 'Switzerland', country_code: 'CH' },
  { id: 3, fifa_code: 'NED', name: 'Netherlands', country_code: 'NL' },
  { id: 4, fifa_code: 'MAR', name: 'Morocco', country_code: 'MA' },
]

describe('buildCoherentMatchMap', () => {
  it('propagates favored winners into downstream matchups', () => {
    const rows: BracketRow[] = [
      { match_number: 73, team_a_id: 1, team_b_id: 2, meeting_count: 500_000, matchup_probability: 0.5, team_a_advance_probability: 0.42 },
      { match_number: 75, team_a_id: 3, team_b_id: 4, meeting_count: 500_000, matchup_probability: 0.5, team_a_advance_probability: 0.58 },
      { match_number: 90, team_a_id: 1, team_b_id: 3, meeting_count: 300_000, matchup_probability: 0.3, team_a_advance_probability: 0.33 },
      { match_number: 90, team_a_id: 2, team_b_id: 3, meeting_count: 200_000, matchup_probability: 0.2, team_a_advance_probability: 0.45 },
    ]

    const matchMap = buildCoherentMatchMap(rows, teams, {})
    const m90 = matchMap.get(90)

    expect(m90?.teamA.id).toBe(2)
    expect(m90?.teamB.id).toBe(3)
    expect(m90?.teamA.advanceProb).toBe(0.45)
    expect(m90?.teamB.advanceProb).toBe(0.55)
  })

  it('uses predicted round-of-32 pairings when provided', () => {
    const bel = 10
    const alg = 11
    const aus = 12
    const irn = 13
    const egy = 14
    const extendedTeams = [
      ...teams,
      { id: bel, fifa_code: 'BEL', name: 'Belgium', country_code: 'BE' },
      { id: alg, fifa_code: 'ALG', name: 'Algeria', country_code: 'DZ' },
      { id: aus, fifa_code: 'AUS', name: 'Australia', country_code: 'AU' },
      { id: irn, fifa_code: 'IRN', name: 'IR Iran', country_code: 'IR' },
      { id: egy, fifa_code: 'EGY', name: 'Egypt', country_code: 'EG' },
    ]
    const rows: BracketRow[] = [
      { match_number: 82, team_a_id: bel, team_b_id: alg, meeting_count: 91_295, matchup_probability: 0.091, team_a_advance_probability: 0.62 },
      { match_number: 82, team_a_id: egy, team_b_id: alg, meeting_count: 62_000, matchup_probability: 0.062, team_a_advance_probability: 0.58 },
      { match_number: 88, team_a_id: aus, team_b_id: bel, meeting_count: 405_284, matchup_probability: 0.405, team_a_advance_probability: 0.55 },
      { match_number: 88, team_a_id: aus, team_b_id: irn, meeting_count: 161_043, matchup_probability: 0.161, team_a_advance_probability: 0.58 },
    ]
    const predictedR32 = new Map([
      [82, { teamAId: egy, teamBId: alg }],
      [88, { teamAId: aus, teamBId: irn }],
    ])

    const matchMap = buildCoherentMatchMap(rows, extendedTeams, {}, predictedR32)
    const m82 = matchMap.get(82)
    const m88 = matchMap.get(88)

    expect(m82?.teamA.id).toBe(egy)
    expect(m82?.teamB.id).toBe(alg)
    expect(m88?.teamA.id).toBe(aus)
    expect(m88?.teamB.id).toBe(irn)
    const r32Teams = [...matchMap.entries()]
      .filter(([matchNumber]) => matchNumber <= 88)
      .flatMap(([, match]) => [match.teamA.id, match.teamB.id])
    expect(r32Teams.length).toBe(new Set(r32Teams).size)
  })

  it('flags venue home boost for co-host teams playing in their country', () => {
    const rows: BracketRow[] = [
      { match_number: 79, team_a_id: 1, team_b_id: 2, meeting_count: 500_000, matchup_probability: 0.5, team_a_advance_probability: 0.83 },
    ]
    const mxTeams = [
      { id: 1, fifa_code: 'MEX', name: 'Mexico', country_code: 'MX' },
      { id: 2, fifa_code: 'SCO', name: 'Scotland', country_code: 'GB' },
    ]
    const m79 = buildCoherentMatchMap(rows, mxTeams, {})?.get(79)
    expect(m79?.hostCountry).toBe('MX')
    expect(m79?.teamA.homeBoost).toBe(true)
    expect(m79?.teamB.homeBoost).toBe(false)
  })
})

describe('topR32SideTeams', () => {
  it('ranks teams independently for each side of a round-of-32 slot', () => {
    const rows: BracketRow[] = [
      { match_number: 73, team_a_id: 1, team_b_id: 2, meeting_count: 400_000, matchup_probability: 0.4, team_a_advance_probability: 0.42 },
      { match_number: 73, team_a_id: 1, team_b_id: 3, meeting_count: 100_000, matchup_probability: 0.1, team_a_advance_probability: 0.55 },
      { match_number: 73, team_a_id: 4, team_b_id: 2, meeting_count: 50_000, matchup_probability: 0.05, team_a_advance_probability: 0.3 },
    ]

    const sideA = topR32SideTeams(rows, 73, 'a', 1_000_000)
    const sideB = topR32SideTeams(rows, 73, 'b', 1_000_000)

    expect(sideA.map(entry => entry.teamId)).toEqual([1, 4])
    expect(sideA[0].probability).toBeCloseTo(0.5)
    expect(sideB.map(entry => entry.teamId)).toEqual([2, 3])
    expect(sideB[0].probability).toBeCloseTo(0.45)
  })
})
