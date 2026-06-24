import { toPng } from 'html-to-image'

const EXPORT_CLASS = 'bracket-grid--export'
const WRAP_EXPORT_CLASS = 'bracket-tree-wrap--exporting'
const JOIN_LINE_STROKE = '#2d9653'

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

export async function exportBracketPng(
  grid: HTMLElement,
  filename = 'world-cup-bracket.png',
): Promise<void> {
  const wrap = grid.closest('.bracket-tree-wrap')
  grid.classList.add(EXPORT_CLASS)
  wrap?.classList.add(WRAP_EXPORT_CLASS)

  await waitForLayout()
  prepareJoinLinesForExport(grid)

  try {
    const width = grid.scrollWidth
    const height = grid.scrollHeight
    const dataUrl = await toPng(grid, {
      cacheBust: true,
      pixelRatio: 2,
      backgroundColor: '#ffffff',
      width,
      height,
      includeStyleProperties: ['stroke', 'stroke-width', 'fill', 'opacity', 'color'],
      style: {
        width: `${width}px`,
        height: `${height}px`,
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
