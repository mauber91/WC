export type SimulationResultCoverage = {
  is_stale: boolean
  last_locked_match_number: number | null
  stale_before_match_number: number | null
  pending_result_count: number
  stale_before_match_label: string | null
  last_locked_match_label: string | null
}

export function formatSimulationCoverage(coverage: SimulationResultCoverage | undefined): string | null {
  if (!coverage) return null
  if (coverage.is_stale && coverage.stale_before_match_number != null) {
    const label = coverage.stale_before_match_label ?? `M${coverage.stale_before_match_number}`
    const extra = coverage.pending_result_count > 1
      ? ` (${coverage.pending_result_count} results not included)`
      : ''
    return `Last updated before ${label}${extra}. Re-run the simulation to refresh.`
  }
  if (coverage.last_locked_match_number != null) {
    const label = coverage.last_locked_match_label ?? `M${coverage.last_locked_match_number}`
    return `Includes group results through ${label}.`
  }
  return 'No finished group results were locked when this run was built.'
}
