import type { CSSProperties } from 'react'

export type BracketSlot = { match: number; row: number; span: number }
export type BracketJoin = { row: number; span: number }

/** Grid rows between sibling matches that feed different next-round fixtures. */
export const BRACKET_PAIR_GAP_ROWS = 1

/** Leaf-level feeder pairs in the bracket (Round-of-32 slots). */
export const BRACKET_LEAF_PAIRS = 8

/** Total bracket grid rows: eight pairs of matches plus seven inter-pair gaps. */
export const BRACKET_GRID_ROWS = BRACKET_LEAF_PAIRS * (2 + BRACKET_PAIR_GAP_ROWS) - BRACKET_PAIR_GAP_ROWS

const LEAF_BLOCK = 2 + BRACKET_PAIR_GAP_ROWS

function leafMatchRow(pairIndex: number, slot: 0 | 1): number {
  return pairIndex * LEAF_BLOCK + slot + 1
}

function mergedMatchRow(pairIndex: number): number {
  return pairIndex * LEAF_BLOCK + 1
}

function mergedMatchSpan(pairSpan: number): number {
  return pairSpan * LEAF_BLOCK - BRACKET_PAIR_GAP_ROWS
}

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
  { match: 73, row: leafMatchRow(0, 0), span: 1 }, { match: 75, row: leafMatchRow(0, 1), span: 1 },
  { match: 74, row: leafMatchRow(1, 0), span: 1 }, { match: 77, row: leafMatchRow(1, 1), span: 1 },
  { match: 83, row: leafMatchRow(2, 0), span: 1 }, { match: 84, row: leafMatchRow(2, 1), span: 1 },
  { match: 81, row: leafMatchRow(3, 0), span: 1 }, { match: 82, row: leafMatchRow(3, 1), span: 1 },
  { match: 76, row: leafMatchRow(4, 0), span: 1 }, { match: 78, row: leafMatchRow(4, 1), span: 1 },
  { match: 79, row: leafMatchRow(5, 0), span: 1 }, { match: 80, row: leafMatchRow(5, 1), span: 1 },
  { match: 86, row: leafMatchRow(6, 0), span: 1 }, { match: 88, row: leafMatchRow(6, 1), span: 1 },
  { match: 85, row: leafMatchRow(7, 0), span: 1 }, { match: 87, row: leafMatchRow(7, 1), span: 1 },
]

export const R16_SLOTS: BracketSlot[] = Array.from({ length: BRACKET_LEAF_PAIRS }, (_, pairIndex) => ({
  match: [90, 89, 93, 94, 91, 92, 95, 96][pairIndex],
  row: mergedMatchRow(pairIndex),
  span: 2,
}))

export const QF_SLOTS: BracketSlot[] = Array.from({ length: 4 }, (_, pairIndex) => ({
  match: [97, 98, 99, 100][pairIndex],
  row: mergedMatchRow(pairIndex * 2),
  span: mergedMatchSpan(2),
}))

export const SF_SLOTS: BracketSlot[] = Array.from({ length: 2 }, (_, pairIndex) => ({
  match: [101, 102][pairIndex],
  row: mergedMatchRow(pairIndex * 4),
  span: mergedMatchSpan(4),
}))

export const FINAL_SLOT: BracketSlot = { match: 104, row: 1, span: mergedMatchSpan(8) }

export const JOIN_R32_R16: BracketJoin[] = Array.from({ length: BRACKET_LEAF_PAIRS }, (_, pairIndex) => ({
  row: mergedMatchRow(pairIndex),
  span: 2,
}))

export const JOIN_R16_QF: BracketJoin[] = Array.from({ length: 4 }, (_, pairIndex) => ({
  row: mergedMatchRow(pairIndex * 2),
  span: mergedMatchSpan(2),
}))

export const JOIN_QF_SF: BracketJoin[] = Array.from({ length: 2 }, (_, pairIndex) => ({
  row: mergedMatchRow(pairIndex * 4),
  span: mergedMatchSpan(4),
}))

export const JOIN_SF_FINAL: BracketJoin[] = [{ row: 1, span: mergedMatchSpan(8) }]

export function bracketRowStyle(row: number, span: number): CSSProperties {
  return { gridRow: `${row + 1} / span ${span}` }
}
