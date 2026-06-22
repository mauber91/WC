import { describe, expect, it } from 'vitest'

import { bracketExportFilename, scenarioBracketExportFilename } from './exportBracketPng'

describe('bracketExportFilename', () => {
  it('includes date and simulation id prefix', () => {
    const name = bracketExportFilename('abc12345-6789')
    expect(name).toMatch(/^world-cup-bracket-\d{4}-\d{2}-\d{2}-abc12345\.png$/)
  })

  it('works without simulation id', () => {
    expect(bracketExportFilename()).toMatch(/^world-cup-bracket-\d{4}-\d{2}-\d{2}\.png$/)
  })
})

describe('scenarioBracketExportFilename', () => {
  it('uses a dated your-bracket prefix', () => {
    expect(scenarioBracketExportFilename()).toMatch(/^your-bracket-\d{4}-\d{2}-\d{2}\.png$/)
  })
})
