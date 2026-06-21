import type { ManualScores } from './scenarioEngine'

export const SCENARIO_STORAGE_KEY = 'world-cup-manual-scenario:v1'

function validGoal(value: unknown): value is number | null {
  return value === null || (typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 99)
}

export function loadScenarioScores(storage: Pick<Storage, 'getItem'> = window.localStorage): ManualScores {
  try {
    const raw = storage.getItem(SCENARIO_STORAGE_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return Object.fromEntries(
      Object.entries(parsed).filter(([, value]) => {
        if (!value || typeof value !== 'object' || Array.isArray(value)) return false
        const score = value as Record<string, unknown>
        return validGoal(score.team_a_goals) && validGoal(score.team_b_goals)
      }),
    ) as ManualScores
  } catch {
    return {}
  }
}

export function saveScenarioScores(
  scores: ManualScores,
  storage: Pick<Storage, 'setItem'> = window.localStorage,
): void {
  storage.setItem(SCENARIO_STORAGE_KEY, JSON.stringify(scores))
}

export function clearScenarioScores(
  storage: Pick<Storage, 'removeItem'> = window.localStorage,
): void {
  storage.removeItem(SCENARIO_STORAGE_KEY)
}
