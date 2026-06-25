import { domToPng } from 'modern-screenshot'

const EXPORT_CLASS = 'bracket-grid--export'
const WRAP_EXPORT_CLASS = 'bracket-tree-wrap--exporting'
const SCROLL_EXPORT_CLASS = 'bracket-scroll--export'
const JOIN_LINE_STROKE = '#2d9653'

/** Fallback column width when the live grid cannot be measured. */
export const BRACKET_EXPORT_COL_PX = 268
export const BRACKET_EXPORT_JOIN_PX = 28
const BRACKET_EXPORT_PADDING_X = 8

export function bracketExportWidth(colPx = BRACKET_EXPORT_COL_PX): number {
  return 5 * colPx + 4 * BRACKET_EXPORT_JOIN_PX + BRACKET_EXPORT_PADDING_X
}

function waitForLayout(): Promise<void> {
  return new Promise(resolve => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
  })
}

function explicitGridColumns(colPx: number, joinPx: number): string {
  return `${colPx}px ${joinPx}px `.repeat(4).trim() + ` ${colPx}px`
}

function measureExportColumnWidth(grid: HTMLElement): number {
  const cell = grid.querySelector<HTMLElement>('.bracket-grid-cell')
  const width = cell?.getBoundingClientRect().width
  if (width && width >= 200) return Math.round(width)
  return BRACKET_EXPORT_COL_PX
}

function prepareJoinLinesForExport(root: HTMLElement): void {
  root.querySelectorAll<SVGPathElement>('.bracket-join-line').forEach(path => {
    path.setAttribute('stroke', JOIN_LINE_STROKE)
    path.setAttribute('stroke-width', '2')
    path.setAttribute('fill', 'none')
    path.setAttribute('vector-effect', 'non-scaling-stroke')
  })
}

type SavedExportState = {
  scrollStyle: string
  gridStyle: string
  scrollLeft: number
}

function applyLiveExportLayout(
  scroll: HTMLElement,
  grid: HTMLElement,
  colPx: number,
): { exportWidth: number; restore: () => void } {
  const joinPx = BRACKET_EXPORT_JOIN_PX
  const exportWidth = bracketExportWidth(colPx)
  const saved: SavedExportState = {
    scrollStyle: scroll.style.cssText,
    gridStyle: grid.style.cssText,
    scrollLeft: scroll.scrollLeft,
  }

  scroll.classList.add(SCROLL_EXPORT_CLASS)
  scroll.style.overflow = 'visible'
  scroll.style.width = `${exportWidth}px`
  scroll.style.maxWidth = `${exportWidth}px`
  scroll.scrollLeft = 0

  grid.classList.add(EXPORT_CLASS)
  grid.style.setProperty('--bracket-col', `${colPx}px`)
  grid.style.setProperty('--bracket-join', `${joinPx}px`)
  grid.style.width = `${exportWidth}px`
  grid.style.minWidth = `${exportWidth}px`
  grid.style.maxWidth = `${exportWidth}px`
  grid.style.gridTemplateColumns = explicitGridColumns(colPx, joinPx)

  return {
    exportWidth,
    restore: () => {
      scroll.classList.remove(SCROLL_EXPORT_CLASS)
      grid.classList.remove(EXPORT_CLASS)
      scroll.style.cssText = saved.scrollStyle
      grid.style.cssText = saved.gridStyle
      scroll.scrollLeft = saved.scrollLeft
    },
  }
}

async function captureBracketPng(scroll: HTMLElement): Promise<string> {
  const options = {
    backgroundColor: '#ffffff',
    filter: (node: Node) => !(node instanceof HTMLElement && node.classList.contains('bracket-r32-tip')),
  }

  for (const scale of [2, 1] as const) {
    const dataUrl = await domToPng(scroll, { ...options, scale })
    if (dataUrl.length > 20_000) return dataUrl
  }

  throw new Error('Export produced a blank image — try again after the bracket finishes loading')
}

export async function exportBracketPng(
  grid: HTMLElement,
  filename = 'world-cup-bracket.png',
): Promise<void> {
  const scroll = grid.closest('.bracket-scroll') as HTMLElement | null
  const wrap = grid.closest('.bracket-tree-wrap')
  if (!scroll) {
    throw new Error('Bracket scroll container not found')
  }

  const colPx = measureExportColumnWidth(grid)
  const { exportWidth, restore } = applyLiveExportLayout(scroll, grid, colPx)
  wrap?.classList.add(WRAP_EXPORT_CLASS)

  await waitForLayout()
  await new Promise(resolve => setTimeout(resolve, 150))
  prepareJoinLinesForExport(grid)

  const exportHeight = Math.max(scroll.scrollHeight, scroll.offsetHeight)
  if (exportWidth < 100 || exportHeight < 100) {
    wrap?.classList.remove(WRAP_EXPORT_CLASS)
    restore()
    throw new Error('Bracket export layout collapsed — try widening the window and export again')
  }

  try {
    const dataUrl = await captureBracketPng(scroll)

    const link = document.createElement('a')
    link.download = filename
    link.href = dataUrl
    link.click()
  } finally {
    wrap?.classList.remove(WRAP_EXPORT_CLASS)
    restore()
  }
}

export function bracketExportFilename(simulationId?: string): string {
  const stamp = new Date().toISOString().slice(0, 10)
  const suffix = simulationId ? `-${simulationId.slice(0, 8)}` : ''
  return `world-cup-bracket-${stamp}${suffix}.png`
}

export function scenarioBracketExportFilename(): string {
  const stamp = new Date().toISOString().slice(0, 10)
  return `your-bracket-${stamp}.png`
}
