import { toPng } from 'html-to-image'

const EXPORT_CLASS = 'bracket-grid--export'
const WRAP_EXPORT_CLASS = 'bracket-tree-wrap--exporting'
const SCROLL_EXPORT_CLASS = 'bracket-scroll--export'
const JOIN_LINE_STROKE = '#2d9653'

/** Fixed layout for PNG export — must match `.bracket-grid--export` in App.css */
export const BRACKET_EXPORT_COL_PX = 268
export const BRACKET_EXPORT_JOIN_PX = 28
const BRACKET_EXPORT_PADDING_X = 8

export function bracketExportWidth(): number {
  return 5 * BRACKET_EXPORT_COL_PX + 4 * BRACKET_EXPORT_JOIN_PX + BRACKET_EXPORT_PADDING_X
}

function waitForLayout(): Promise<void> {
  return new Promise(resolve => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
  })
}

function prepareJoinLinesForExport(root: HTMLElement): void {
  root.querySelectorAll<SVGPathElement>('.bracket-join-line').forEach(path => {
    path.setAttribute('stroke', JOIN_LINE_STROKE)
    path.setAttribute('stroke-width', '2')
    path.setAttribute('fill', 'none')
    path.setAttribute('vector-effect', 'non-scaling-stroke')
  })
}

function applyExportLayout(grid: HTMLElement, scroll: HTMLElement | null): () => void {
  const exportWidth = bracketExportWidth()
  const saved = {
    grid: grid.style.cssText,
    scroll: scroll?.style.cssText ?? '',
  }

  grid.style.setProperty('--bracket-col', `${BRACKET_EXPORT_COL_PX}px`)
  grid.style.setProperty('--bracket-join', `${BRACKET_EXPORT_JOIN_PX}px`)
  grid.style.setProperty('--bracket-row', '116px')
  grid.style.width = `${exportWidth}px`
  grid.style.minWidth = `${exportWidth}px`
  grid.style.maxWidth = `${exportWidth}px`

  if (scroll) {
    scroll.style.width = `${exportWidth}px`
    scroll.style.maxWidth = `${exportWidth}px`
    scroll.style.overflow = 'visible'
  }

  return () => {
    grid.style.cssText = saved.grid
    if (scroll) scroll.style.cssText = saved.scroll
  }
}

export async function exportBracketPng(
  grid: HTMLElement,
  filename = 'world-cup-bracket.png',
): Promise<void> {
  const wrap = grid.closest('.bracket-tree-wrap')
  const scroll = grid.closest('.bracket-scroll') as HTMLElement | null
  const exportWidth = bracketExportWidth()

  grid.classList.add(EXPORT_CLASS)
  wrap?.classList.add(WRAP_EXPORT_CLASS)
  scroll?.classList.add(SCROLL_EXPORT_CLASS)
  const restoreLayout = applyExportLayout(grid, scroll)

  await waitForLayout()
  await new Promise(resolve => setTimeout(resolve, 60))
  prepareJoinLinesForExport(grid)

  try {
    const height = grid.scrollHeight
    const dataUrl = await toPng(grid, {
      cacheBust: true,
      pixelRatio: 2,
      backgroundColor: '#ffffff',
      width: exportWidth,
      height,
      includeStyleProperties: ['stroke', 'stroke-width', 'fill', 'opacity', 'color'],
      style: {
        width: `${exportWidth}px`,
        height: `${height}px`,
        transform: 'none',
      },
      filter: node => !(node instanceof HTMLElement && node.classList.contains('bracket-r32-tip')),
    })

    const link = document.createElement('a')
    link.download = filename
    link.href = dataUrl
    link.click()
  } finally {
    grid.classList.remove(EXPORT_CLASS)
    wrap?.classList.remove(WRAP_EXPORT_CLASS)
    scroll?.classList.remove(SCROLL_EXPORT_CLASS)
    restoreLayout()
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
