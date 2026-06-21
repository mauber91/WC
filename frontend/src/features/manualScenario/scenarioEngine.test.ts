import { describe, expect, it } from 'vitest'
import {
  annexCombinationCount,
  calculateScenario,
  type ScenarioGroup,
  type ScenarioMatch,
  type ScenarioTeam,
} from './scenarioEngine'

function team(id: number, code: string): ScenarioTeam {
  return { id, fifa_code: code, name: code }
}

function match(
  number: number,
  group: string,
  a: ScenarioTeam,
  b: ScenarioTeam,
  goalsA: number,
  goalsB: number,
): ScenarioMatch {
  return {
    id: number,
    official_match_number: number,
    stage: 'group',
    group_code: group,
    team_a: a,
    team_b: b,
    scheduled_at: '2026-06-01T12:00:00Z',
    status: 'final',
    result: { team_a_goals: goalsA, team_b_goals: goalsB, revision: 1 },
  }
}

describe('manual scenario standings', () => {
  it('applies head-to-head before overall goal difference', () => {
    const [a, b, c, d] = ['AAA', 'BBB', 'CCC', 'DDD'].map((code, index) => team(index + 1, code))
    const group: ScenarioGroup = { id: 1, code: 'A', display_name: 'Group A', teams: [a, b, c, d] }
    const matches = [
      match(1, 'A', a, b, 1, 0),
      match(2, 'A', a, c, 0, 4),
      match(3, 'A', a, d, 1, 0),
      match(4, 'A', b, c, 3, 0),
      match(5, 'A', b, d, 3, 0),
      match(6, 'A', c, d, 0, 0),
    ]
    const outcome = calculateScenario([group], matches, {})
    expect(outcome.tables[0].rows.slice(0, 2).map(row => row.team.fifa_code)).toEqual(['AAA', 'BBB'])
    expect(outcome.tables[0].rows[0].goalDifference).toBeLessThan(outcome.tables[0].rows[1].goalDifference)
  })

  it('recursively resolves a three-team head-to-head mini-league', () => {
    const [a, b, c, d] = ['AAA', 'BBB', 'CCC', 'DDD'].map((code, index) => team(index + 1, code))
    const group: ScenarioGroup = { id: 1, code: 'A', display_name: 'Group A', teams: [a, b, c, d] }
    const matches = [
      match(1, 'A', a, b, 1, 0),
      match(2, 'A', b, c, 1, 0),
      match(3, 'A', c, a, 2, 0),
      match(4, 'A', a, d, 1, 0),
      match(5, 'A', b, d, 1, 0),
      match(6, 'A', c, d, 1, 0),
    ]
    const outcome = calculateScenario([group], matches, {})
    expect(outcome.tables[0].rows.slice(0, 3).map(row => row.team.fifa_code)).toEqual(['CCC', 'BBB', 'AAA'])
  })
})

describe('manual scenario bracket', () => {
  it('contains all 495 official Annex C combinations', () => {
    expect(annexCombinationCount()).toBe(495)
  })

  it('builds all 16 Round-of-32 matches once every group is complete', () => {
    const groups: ScenarioGroup[] = []
    const matches: ScenarioMatch[] = []
    let teamId = 1
    let matchNumber = 1
    for (const groupCode of 'ABCDEFGHIJKL') {
      const teams = [1, 2, 3, 4].map(position => team(teamId++, `${groupCode}${position}`))
      groups.push({ id: groups.length + 1, code: groupCode, display_name: `Group ${groupCode}`, teams })
      const fixtures: Array<[number, number, number, number]> = [
        [0, 1, 1, 0], [0, 2, 1, 0], [0, 3, 1, 0],
        [1, 2, 1, 0], [1, 3, 1, 0], [2, 3, 1, 0],
      ]
      fixtures.forEach(([a, b, goalsA, goalsB]) => {
        matches.push(match(matchNumber++, groupCode, teams[a], teams[b], goalsA, goalsB))
      })
    }
    const outcome = calculateScenario(groups, matches, {})
    expect(outcome.bracket).toHaveLength(16)
    expect(outcome.tables.every(table =>
      table.rows.every((row, index) => row.position === index + 1),
    )).toBe(true)
    expect(new Set(outcome.bracket?.map(row => row.matchNumber))).toEqual(new Set(Array.from({ length: 16 }, (_, index) => 73 + index)))
    expect(outcome.bracket?.every(row => row.teamA.id !== row.teamB.id)).toBe(true)
  })
})
