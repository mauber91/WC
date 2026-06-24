import { bracketRowStyle, type BracketJoin } from '../lib/bracketLayout'

const JOIN_PATH = 'M 252 25 H 280 M 252 75 H 280 M 280 25 V 75'

export function BracketJoinCell({ join, column }: { join: BracketJoin; column: number }) {
  return (
    <div className="bracket-join" style={{ ...bracketRowStyle(join.row, join.span), gridColumn: column }}>
      <svg className="bracket-join-svg" viewBox="0 0 532 100" preserveAspectRatio="none" aria-hidden>
        <path
          d={JOIN_PATH}
          fill="none"
          stroke="#2d9653"
          strokeWidth={2}
          vectorEffect="non-scaling-stroke"
          strokeLinecap="butt"
          strokeLinejoin="miter"
          className="bracket-join-line"
        />
      </svg>
    </div>
  )
}
