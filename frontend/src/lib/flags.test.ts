import { describe, expect, it } from 'vitest'
import { flagEmoji } from './flags'

describe('flagEmoji', () => {
  it('maps FIFA codes to regional indicator emoji', () => {
    expect(flagEmoji('GER')).toBe('🇩🇪')
    expect(flagEmoji('SUI')).toBe('🇨🇭')
    expect(flagEmoji('NED')).toBe('🇳🇱')
    expect(flagEmoji('PAR')).toBe('🇵🇾')
    expect(flagEmoji('KOR')).toBe('🇰🇷')
  })

  it('returns a fallback for unknown codes', () => {
    expect(flagEmoji('XXX')).toBe('🏳️')
  })
})
