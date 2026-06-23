import type { CSSProperties } from 'react'

export type BracketSlot = { match: number; row: number; span: number }
export type BracketJoin = { row: number; span: number }

export const BRACKET_COL = {
  r32: 1,
  c1: 2,
  r16: 3,
  c2: 4,
  qf: 5,
  c3: 6,
  sf: 7,
  c4: 8,
  final: 9,
} as const

export const R32_SLOTS: BracketSlot[] = [
  { match: 73, row: 1, span: 1 }, { match: 75, row: 2, span: 1 },
  { match: 74, row: 3, span: 1 }, { match: 77, row: 4, span: 1 },
  { match: 83, row: 5, span: 1 }, { match: 84, row: 6, span: 1 },
  { match: 81, row: 7, span: 1 }, { match: 82, row: 8, span: 1 },
  { match: 76, row: 9, span: 1 }, { match: 78, row: 10, span: 1 },
  { match: 79, row: 11, span: 1 }, { match: 80, row: 12, span: 1 },
  { match: 86, row: 13, span: 1 }, { match: 88, row: 14, span: 1 },
  { match: 85, row: 15, span: 1 }, { match: 87, row: 16, span: 1 },
]

export const R16_SLOTS: BracketSlot[] = [
  { match: 90, row: 1, span: 2 }, { match: 89, row: 3, span: 2 },
  { match: 93, row: 5, span: 2 }, { match: 94, row: 7, span: 2 },
  { match: 91, row: 9, span: 2 }, { match: 92, row: 11, span: 2 },
  { match: 95, row: 13, span: 2 }, { match: 96, row: 15, span: 2 },
]

export const QF_SLOTS: BracketSlot[] = [
  { match: 97, row: 1, span: 4 },
  { match: 98, row: 5, span: 4 },
  { match: 99, row: 9, span: 4 },
  { match: 100, row: 13, span: 4 },
]

export const SF_SLOTS: BracketSlot[] = [
  { match: 101, row: 1, span: 8 },
  { match: 102, row: 9, span: 8 },
]

export const FINAL_SLOT: BracketSlot = { match: 104, row: 1, span: 16 }

export const JOIN_R32_R16: BracketJoin[] = [
  { row: 1, span: 2 }, { row: 3, span: 2 }, { row: 5, span: 2 }, { row: 7, span: 2 },
  { row: 9, span: 2 }, { row: 11, span: 2 }, { row: 13, span: 2 }, { row: 15, span: 2 },
]

export const JOIN_R16_QF: BracketJoin[] = [
  { row: 1, span: 4 }, { row: 5, span: 4 }, { row: 9, span: 4 }, { row: 13, span: 4 },
]

export const JOIN_QF_SF: BracketJoin[] = [
  { row: 1, span: 8 },
  { row: 9, span: 8 },
]

export const JOIN_SF_FINAL: BracketJoin[] = [{ row: 1, span: 16 }]

export function bracketRowStyle(row: number, span: number): CSSProperties {
  return { gridRow: `${row + 1} / span ${span}` }
}
