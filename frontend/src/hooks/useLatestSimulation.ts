import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { isPublishedMode, publishedSimulationId } from '../config/appMode'

export type SimulationRun = {
  id: string
  status: string
  iterations: number
  progress_iterations: number
  seed: number
  input_cutoff_at: string
  model_version: string
  ruleset_version: string
  duration_ms?: number
  error_message?: string
}

type PublishedMeta = {
  simulation_id: string
  iterations: number
  seed: number
  input_cutoff_at: string
  model_version: string
  ruleset_version: string
  completed_at?: string
  duration_ms?: number
}

function usePublishedSimulation() {
  return useQuery<SimulationRun>({
    queryKey: ['published-simulation', publishedSimulationId],
    queryFn: async () => {
      if (publishedSimulationId) {
        return api<SimulationRun>(`/simulations/${publishedSimulationId}`)
      }
      const meta = await api<PublishedMeta>('/published')
      return api<SimulationRun>(`/simulations/${meta.simulation_id}`)
    },
    enabled: isPublishedMode,
    staleTime: 60_000,
  })
}

function useLocalRuns() {
  return useQuery<SimulationRun[]>({
    queryKey: ['runs'],
    queryFn: () => api('/simulations'),
    refetchInterval: query =>
      query.state.data?.some(run => run.status === 'running' || run.status === 'queued') ? 500 : 10_000,
    enabled: !isPublishedMode,
  })
}

export function useLatestSimulation() {
  const published = usePublishedSimulation()
  const runs = useLocalRuns()

  if (isPublishedMode) {
    const run = published.data?.status === 'completed' ? published.data : undefined
    return {
      data: run,
      isLoading: published.isLoading,
      error: published.error,
      active: undefined as SimulationRun | undefined,
    }
  }

  const active = runs.data?.find(run => run.status === 'running' || run.status === 'queued')
  const latest = runs.data?.find(run => run.status === 'completed')
  return {
    data: latest,
    isLoading: runs.isLoading,
    error: runs.error,
    active,
    runs: runs.data,
  }
}

export function useRuns() {
  const published = usePublishedSimulation()
  const runs = useLocalRuns()

  if (isPublishedMode) {
    return {
      ...published,
      data: published.data ? [published.data] : [],
    }
  }

  return runs
}
