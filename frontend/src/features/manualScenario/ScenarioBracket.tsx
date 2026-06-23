import { useRef, useState } from 'react'
import { exportBracketPng, scenarioBracketExportFilename } from '../../lib/exportBracketPng'
import { flagEmoji } from '../../lib/flags'
import {
  BRACKET_COL,
  FINAL_SLOT,
  JOIN_QF_SF,
  JOIN_R16_QF,
  JOIN_R32_R16,
  JOIN_SF_FINAL,
  QF_SLOTS,
  R16_SLOTS,
  R32_SLOTS,
  SF_SLOTS,
  bracketRowStyle,
  type BracketJoin,
  type BracketSlot,
} from '../../lib/bracketLayout'
import type { ResolvedKnockoutMatch, ScenarioTeam } from './scenarioEngine'

function PickableTeam({
  team,
  source,
  picked,
  disabled,
  onPick,
}: {
  team: ScenarioTeam
  source?: string
  picked: boolean
  disabled: boolean
  onPick: () => void
}) {
  return (
    <button
      type="button"
      className={`bracket-team scenario-pickable${picked ? ' scenario-picked' : ''}`}
      disabled={disabled}
      aria-pressed={picked}
      onClick={onPick}
    >
      <span className="bracket-flag" aria-hidden>{flagEmoji(team.fifa_code)}</span>
      <span>
        <span className="bracket-team-name" title={team.name}>{team.name}</span>
        {source && <small className="scenario-bracket-source">{source}</small>}
      </span>
      {picked && <span className="scenario-pick-badge">Your pick</span>}
    </button>
  )
}

function KnockoutMatchCard({
  match,
  isFinal = false,
  interactive,
  exporting,
  onPick,
}: {
  match: ResolvedKnockoutMatch
  isFinal?: boolean
  interactive: boolean
  exporting: boolean
  onPick: (matchNumber: number, teamId: number) => void
}) {
  const ready = match.teamA != null && match.teamB != null
  const badge = ready
    ? (match.winnerId != null
      ? (exporting ? 'Your pick' : 'Your pick set')
      : (exporting ? 'Open' : 'Click to advance'))
    : 'Awaiting picks'

  return (
    <article className={`bracket-match-card scenario-knockout-card${isFinal ? ' final' : ''}${ready ? '' : ' empty'}`}>
      <div className="bracket-match-body">
        <header className="bracket-match-head">
          <span className="bracket-badge">{badge}</span>
          <span className="bracket-match-no">M{match.matchNumber}</span>
        </header>
        {ready ? (
          <div className="bracket-teams">
            <PickableTeam
              team={match.teamA!}
              source={match.sourceA}
              picked={match.winnerId === match.teamA!.id}
              disabled={!interactive}
              onPick={() => onPick(match.matchNumber, match.teamA!.id)}
            />
            <PickableTeam
              team={match.teamB!}
              source={match.sourceB}
              picked={match.winnerId === match.teamB!.id}
              disabled={!interactive}
              onPick={() => onPick(match.matchNumber, match.teamB!.id)}
            />
          </div>
        ) : (
          <div className="scenario-knockout-feeders">
            {match.pendingFeeders?.map(feeder => (
              <div className="scenario-knockout-feeder" key={feeder}>Winner M{feeder}</div>
            )) ?? <p>Enter group scores to set Round-of-32 slots.</p>}
          </div>
        )}
      </div>
    </article>
  )
}

function JoinCell({ join, column }: { join: BracketJoin; column: number }) {
  return (
    <div className="bracket-join" style={{ ...bracketRowStyle(join.row, join.span), gridColumn: column }}>
      <svg className="bracket-join-svg" viewBox="0 0 532 100" preserveAspectRatio="none" aria-hidden>
        <path
          d="M 252 25 H 280 M 252 75 H 280 M 280 25 V 75"
          fill="none"
          className="bracket-join-line"
        />
      </svg>
    </div>
  )
}

function MatchCell({
  slot,
  column,
  matchMap,
  isFinal = false,
  interactive,
  exporting,
  onPick,
}: {
  slot: BracketSlot
  column: number
  matchMap: Map<number, ResolvedKnockoutMatch>
  isFinal?: boolean
  interactive: boolean
  exporting: boolean
  onPick: (matchNumber: number, teamId: number) => void
}) {
  const match = matchMap.get(slot.match)
  return (
    <div className="bracket-grid-cell" style={{ ...bracketRowStyle(slot.row, slot.span), gridColumn: column }}>
      {match
        ? <KnockoutMatchCard match={match} isFinal={isFinal} interactive={interactive} exporting={exporting} onPick={onPick} />
        : null}
    </div>
  )
}

export function ScenarioBracket({
  resolvedMatches,
  interactive = true,
  onPick,
}: {
  resolvedMatches: Map<number, ResolvedKnockoutMatch>
  interactive?: boolean
  onPick: (matchNumber: number, teamId: number) => void
}) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const gridRef = useRef<HTMLDivElement>(null)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  function scrollToEdge(edge: 'start' | 'end') {
    const node = scrollRef.current
    if (!node) return
    node.scrollTo({ left: edge === 'start' ? 0 : node.scrollWidth, behavior: 'smooth' })
  }

  async function handleExportPng() {
    const grid = gridRef.current
    if (!grid || exporting) return
    setExportError(null)
    setExporting(true)
    try {
      await exportBracketPng(grid, scenarioBracketExportFilename())
    } catch (error) {
      setExportError(error instanceof Error ? error.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="bracket-tree-wrap scenario-bracket-tree">
      <div className="bracket-toolbar">
        <p className="bracket-meta">
          <span className="local-only-badge">Browser scenario</span>
          Round-of-32 pairings follow your group scores and FIFA Annex C. Click a team in each match to pick who
          advances — later rounds fill in as you go. Picks stay in this browser only.
        </p>
        <div className="bracket-jump">
          <button type="button" className="button ghost" onClick={() => scrollToEdge('start')}>Round of 32</button>
          <button type="button" className="button ghost" onClick={() => scrollToEdge('end')}>Final</button>
          <button
            type="button"
            className="button ghost"
            onClick={() => void handleExportPng()}
            disabled={exporting}
          >
            {exporting ? 'Exporting…' : 'Export PNG'}
          </button>
        </div>
      </div>
      {exportError && <p className="bracket-export-error" role="alert">{exportError}</p>}
      <div className="bracket-scroll" ref={scrollRef}>
        <div className="bracket-grid" ref={gridRef}>
          <div className="bracket-grid-head" style={{ gridColumn: BRACKET_COL.r32 }}>Round of 32</div>
          <div className="bracket-grid-head" style={{ gridColumn: BRACKET_COL.r16 }}>Round of 16</div>
          <div className="bracket-grid-head" style={{ gridColumn: BRACKET_COL.qf }}>Quarter-finals</div>
          <div className="bracket-grid-head" style={{ gridColumn: BRACKET_COL.sf }}>Semi-finals</div>
          <div className="bracket-grid-head" style={{ gridColumn: BRACKET_COL.final }}>Final</div>

          {R32_SLOTS.map(slot => (
            <MatchCell key={slot.match} slot={slot} column={BRACKET_COL.r32} matchMap={resolvedMatches} interactive={interactive} exporting={exporting} onPick={onPick} />
          ))}
          {JOIN_R32_R16.map((join, index) => (
            <JoinCell key={`j1-${index}`} join={join} column={BRACKET_COL.c1} />
          ))}

          {R16_SLOTS.map(slot => (
            <MatchCell key={slot.match} slot={slot} column={BRACKET_COL.r16} matchMap={resolvedMatches} interactive={interactive} exporting={exporting} onPick={onPick} />
          ))}
          {JOIN_R16_QF.map((join, index) => (
            <JoinCell key={`j2-${index}`} join={join} column={BRACKET_COL.c2} />
          ))}

          {QF_SLOTS.map(slot => (
            <MatchCell key={slot.match} slot={slot} column={BRACKET_COL.qf} matchMap={resolvedMatches} interactive={interactive} exporting={exporting} onPick={onPick} />
          ))}
          {JOIN_QF_SF.map((join, index) => (
            <JoinCell key={`j3-${index}`} join={join} column={BRACKET_COL.c3} />
          ))}

          {SF_SLOTS.map(slot => (
            <MatchCell key={slot.match} slot={slot} column={BRACKET_COL.sf} matchMap={resolvedMatches} interactive={interactive} exporting={exporting} onPick={onPick} />
          ))}
          {JOIN_SF_FINAL.map((join, index) => (
            <JoinCell key={`j4-${index}`} join={join} column={BRACKET_COL.c4} />
          ))}

          <MatchCell slot={FINAL_SLOT} column={BRACKET_COL.final} matchMap={resolvedMatches} isFinal interactive={interactive} exporting={exporting} onPick={onPick} />
        </div>
      </div>
    </div>
  )
}
