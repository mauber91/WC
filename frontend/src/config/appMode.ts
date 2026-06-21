import type { ManualScores } from '../features/manualScenario/scenarioEngine'

export const isPublishedMode = import.meta.env.VITE_APP_MODE === 'published'

export const publishedSimulationId = import.meta.env.VITE_PUBLISHED_SIMULATION_ID as string | undefined

export const publishedScenarioTitle =
  (import.meta.env.VITE_PUBLISHED_SCENARIO_TITLE as string | undefined) ?? 'Author scenario'

export const publishedScenarioDescription =
  (import.meta.env.VITE_PUBLISHED_SCENARIO_DESCRIPTION as string | undefined) ??
  'A fixed what-if bracket built from chosen group-stage results. Separate from the Monte Carlo forecast.'

export function parsePublishedScenario(): ManualScores | null {
  const raw = import.meta.env.VITE_PUBLISHED_SCENARIO
  if (!raw) return null
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    return parsed as ManualScores
  } catch {
    return null
  }
}

export const publishedScenario = isPublishedMode ? parsePublishedScenario() : null
