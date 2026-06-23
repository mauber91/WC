import { describe, expect, it } from 'vitest'
import { formatSimulationCoverage } from './simulationCoverage'

describe('formatSimulationCoverage', () => {
  it('describes stale runs before the first missing result', () => {
    const message = formatSimulationCoverage({
      is_stale: true,
      last_locked_match_number: 40,
      stale_before_match_number: 41,
      pending_result_count: 2,
      stale_before_match_label: 'M41 · Colombia vs Portugal',
      last_locked_match_label: null,
    })
    expect(message).toContain('before M41 · Colombia vs Portugal')
    expect(message).toContain('2 results not included')
  })

  it('describes fresh runs through the last locked match', () => {
    const message = formatSimulationCoverage({
      is_stale: false,
      last_locked_match_number: 72,
      stale_before_match_number: null,
      pending_result_count: 0,
      stale_before_match_label: null,
      last_locked_match_label: 'M72 · Brazil vs Morocco',
    })
    expect(message).toBe('Includes group results through M72 · Brazil vs Morocco.')
  })
})
