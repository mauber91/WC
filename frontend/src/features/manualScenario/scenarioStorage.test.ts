import { describe, expect, it } from 'vitest'
import {
  clearScenarioScores,
  loadKnockoutPicks,
  loadScenarioScores,
  saveKnockoutPicks,
  saveScenarioScores,
  SCENARIO_STORAGE_KEY,
} from './scenarioStorage'

function fakeStorage(initial?: string) {
  const values = new Map<string, string>()
  if (initial != null) values.set(SCENARIO_STORAGE_KEY, initial)
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value) },
    removeItem: (key: string) => { values.delete(key) },
  }
}

describe('manual scenario local storage', () => {
  it('round trips scores and clears them', () => {
    const storage = fakeStorage()
    const scores = { '49': { team_a_goals: 2, team_b_goals: 1 } }
    saveScenarioScores(scores, storage)
    expect(loadScenarioScores(storage)).toEqual(scores)
    clearScenarioScores(storage)
    expect(loadScenarioScores(storage)).toEqual({})
    expect(loadKnockoutPicks(storage)).toEqual({})
  })

  it('round trips knockout picks', () => {
    const storage = fakeStorage()
    saveKnockoutPicks({ '73': 12, '89': 5 }, storage)
    expect(loadKnockoutPicks(storage)).toEqual({ '73': 12, '89': 5 })
  })

  it('rejects malformed or out-of-range entries', () => {
    const storage = fakeStorage(JSON.stringify({
      49: { team_a_goals: 2, team_b_goals: 1 },
      50: { team_a_goals: -1, team_b_goals: 4 },
      bad: 'score',
    }))
    expect(loadScenarioScores(storage)).toEqual({ '49': { team_a_goals: 2, team_b_goals: 1 } })
    expect(loadScenarioScores(fakeStorage('{broken'))).toEqual({})
  })
})
