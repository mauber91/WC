import { toPng } from 'html-to-image'

const EXPORT_CLASS = 'bracket-grid--export'
const WRAP_EXPORT_CLASS = 'bracket-tree-wrap--exporting'

function waitForLayout(): Promise<void> {
  return new Promise(resolve => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
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

  try {
    const width = grid.scrollWidth
    const height = grid.scrollHeight
    const dataUrl = await toPng(grid, {
      cacheBust: true,
      pixelRatio: 2,
      backgroundColor: '#ffffff',
      width,
      height,
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
