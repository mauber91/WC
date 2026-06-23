import { useMemo, useRef, useState, type CSSProperties } from 'react'
import { percent } from '../api/client'
import { bracketExportFilename, exportBracketPng } from '../lib/exportBracketPng'
import { flagEmoji } from '../lib/flags'
import { formatSimulationCoverage, type SimulationResultCoverage } from '../lib/simulationCoverage'
import { buildCoherentMatchMap, buildR32SlotLeaderboards, type BracketMatch, type BracketRow, type R32MatchSlotLeaders } from '../lib/bracketPath'
import { KNOCKOUT_SCHEDULE } from '../lib/knockoutSchedule'
import {
  BRACKET_COL as COL,
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
  type BracketJoin as Join,
  type BracketSlot,
} from '../lib/bracketLayout'

export type { BracketRow }

type Team = { id: number; fifa_code: string; name: string; country_code?: string }

function formatSchedule(iso: string | null, matchNumber: number) {
  if (!iso) return { day: 'TBD', time: '—', date: `M${matchNumber}` }
  const date = new Date(iso)
  return {
    day: date.toLocaleDateString(undefined, { weekday: 'short' }).toUpperCase(),
    time: date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false }),
    date: date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }).toUpperCase(),
  }
}

function buildMatchMap(rows: BracketRow[], teams: Team[]): Map<number, BracketMatch> {
  const normalized = teams.map(team => ({
    ...team,
    country_code: team.country_code ?? '',
  }))
  return buildCoherentMatchMap(rows, normalized, KNOCKOUT_SCHEDULE)
}

function rowStyle(row: number, span: number): CSSProperties {
  return bracketRowStyle(row, span)
}

function BracketMatchCard({ match, matchNumber, isFinal = false }: {
  match: BracketMatch | undefined
  matchNumber: number
  isFinal?: boolean
}) {
  if (!match) {
    return <div className="bracket-match-card empty"><span className="bracket-badge">Awaiting sim</span><p>M{matchNumber}</p></div>
  }
  const schedule = formatSchedule(match.scheduledAt, match.matchNumber)
  const label = match.matchupProbability >= 0.15 ? 'Most likely' : 'Projected'
  return (
    <article className={`bracket-match-card${isFinal ? ' final' : ''}`}>
      <div className="bracket-match-body">
        <header className="bracket-match-head">
          <span className="bracket-badge">{label}</span>
          <span className="bracket-match-no">M{match.matchNumber}</span>
        </header>
        <div className="bracket-teams">
          <TeamLine team={match.teamA} />
          <TeamLine team={match.teamB} />
        </div>
      </div>
      <aside className="bracket-schedule">
        <span>{schedule.day}</span>
        <strong>{schedule.time}</strong>
        <span>{match.scheduledAt ? schedule.date : `M${match.matchNumber}`}</span>
      </aside>
    </article>
  )
}

function TeamLine({ team }: { team: BracketMatch['teamA'] }) {
  const favored = team.advanceProb >= 0.5
  return (
    <div className={`bracket-team${favored ? ' favored' : ''}`}>
      <span className="bracket-flag" aria-hidden>{flagEmoji(team.fifaCode)}</span>
      <span className="bracket-team-name" title={team.name}>{team.name}</span>
      {team.homeBoost && (
        <span className="bracket-home-boost" title="Venue home boost applied in model">H</span>
      )}
      <strong className="bracket-team-pct">{percent(team.advanceProb)}</strong>
    </div>
  )
}

function R32SlotSideList({ candidates, teams }: {
  candidates: Array<{ teamId: number; probability: number }>
  teams: Team[]
}) {
  const teamById = new Map(teams.map(team => [team.id, team]))
  return (
    <ol className="bracket-r32-tip-list">
      {candidates.map(candidate => {
        const team = teamById.get(candidate.teamId)
        if (!team) return null
        return (
          <li key={candidate.teamId}>
            <span className="bracket-r32-tip-team">
              <span aria-hidden>{flagEmoji(team.fifa_code)}</span>
              <span className="bracket-r32-tip-name" title={team.name}>{team.name}</span>
            </span>
            <strong className="bracket-r32-tip-pct">{percent(candidate.probability, 2)}</strong>
          </li>
        )
      })}
    </ol>
  )
}

function R32SlotTooltip({ matchNumber, leaders, teams }: {
  matchNumber: number
  leaders: R32MatchSlotLeaders
  teams: Team[]
}) {
  return (
    <div className="bracket-r32-tip" role="tooltip">
      <p className="bracket-r32-tip-title">M{matchNumber} slot chances</p>
      <p className="bracket-r32-tip-sub">Top 3 per bracket side from the group stage</p>
      <div className="bracket-r32-tip-sides">
        <section>
          <h4>{leaders.sideA.label}</h4>
          <R32SlotSideList candidates={leaders.sideA.candidates} teams={teams} />
        </section>
        <section>
          <h4>{leaders.sideB.label}</h4>
          <R32SlotSideList candidates={leaders.sideB.candidates} teams={teams} />
        </section>
      </div>
    </div>
  )
}

function R32MatchCell({ slot, matchMap, slotLeaders, teams }: {
  slot: BracketSlot
  matchMap: Map<number, BracketMatch>
  slotLeaders: Map<number, R32MatchSlotLeaders>
  teams: Team[]
}) {
  const leaders = slotLeaders.get(slot.match)
  const tipAbove = slot.row >= 9
  return (
    <div
      className={`bracket-grid-cell has-r32-tip${tipAbove ? ' tip-above' : ''}`}
      style={{ ...rowStyle(slot.row, slot.span), gridColumn: COL.r32 }}
      tabIndex={0}
    >
      <BracketMatchCard match={matchMap.get(slot.match)} matchNumber={slot.match} />
      {leaders && (
        <R32SlotTooltip matchNumber={slot.match} leaders={leaders} teams={teams} />
      )}
    </div>
  )
}

function MatchCell({ slot, column, matchMap, isFinal }: {
  slot: BracketSlot
  column: number
  matchMap: Map<number, BracketMatch>
  isFinal?: boolean
}) {
  return (
    <div className="bracket-grid-cell" style={{ ...rowStyle(slot.row, slot.span), gridColumn: column }}>
      <BracketMatchCard match={matchMap.get(slot.match)} matchNumber={slot.match} isFinal={isFinal} />
    </div>
  )
}

/** One SVG per gap: horizontals from feeder card edges, vertical at next-card edge. */
function JoinCell({ join, column }: { join: Join; column: number }) {
  return (
    <div className="bracket-join" style={{ ...rowStyle(join.row, join.span), gridColumn: column }}>
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

export function BracketBoard({
  rows,
  teams,
  iterations,
  simulationId,
  resultCoverage,
}: {
  rows: BracketRow[]
  teams: Team[]
  iterations: number
  simulationId?: string
  resultCoverage?: SimulationResultCoverage
}) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const gridRef = useRef<HTMLDivElement>(null)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const matchMap = useMemo(() => buildMatchMap(rows, teams), [rows, teams])
  const r32SlotLeaders = useMemo(() => buildR32SlotLeaderboards(rows, iterations), [rows, iterations])

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
      await exportBracketPng(grid, bracketExportFilename(simulationId))
    } catch (error) {
      setExportError(error instanceof Error ? error.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  const coverageMessage = formatSimulationCoverage(resultCoverage)

  return (
    <div className="bracket-tree-wrap">
      {coverageMessage && (
        <div className={`bracket-coverage${resultCoverage?.is_stale ? ' stale' : ''}`}>
          {coverageMessage}
        </div>
      )}
      <div className="bracket-toolbar">
        <p className="bracket-meta">
          One projected path through the bracket from {iterations.toLocaleString()} simulations.
          Each match shows the favored winner from the round before; percentages are sim win rates for that pairing.
          Hover a Round-of-32 match to see the top 3 teams for each side of that slot.
          <span className="bracket-meta-home"> H = venue home boost (MX/US/CA playing in their host country).</span>
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
        <div className="bracket-grid-head" style={{ gridColumn: COL.r32 }}>Round of 32</div>
        <div className="bracket-grid-head" style={{ gridColumn: COL.r16 }}>Round of 16</div>
        <div className="bracket-grid-head" style={{ gridColumn: COL.qf }}>Quarter-finals</div>
        <div className="bracket-grid-head" style={{ gridColumn: COL.sf }}>Semi-finals</div>
        <div className="bracket-grid-head" style={{ gridColumn: COL.final }}>Final</div>

        {R32_SLOTS.map(slot => (
          <R32MatchCell key={slot.match} slot={slot} matchMap={matchMap} slotLeaders={r32SlotLeaders} teams={teams} />
        ))}
        {JOIN_R32_R16.map((join, index) => <JoinCell key={`j1-${index}`} join={join} column={COL.c1} />)}

        {R16_SLOTS.map(slot => <MatchCell key={slot.match} slot={slot} column={COL.r16} matchMap={matchMap} />)}
        {JOIN_R16_QF.map((join, index) => <JoinCell key={`j2-${index}`} join={join} column={COL.c2} />)}

        {QF_SLOTS.map(slot => <MatchCell key={slot.match} slot={slot} column={COL.qf} matchMap={matchMap} />)}
        {JOIN_QF_SF.map((join, index) => <JoinCell key={`j3-${index}`} join={join} column={COL.c3} />)}

        {SF_SLOTS.map(slot => <MatchCell key={slot.match} slot={slot} column={COL.sf} matchMap={matchMap} />)}
        {JOIN_SF_FINAL.map((join, index) => <JoinCell key={`j4-${index}`} join={join} column={COL.c4} />)}

        <MatchCell slot={FINAL_SLOT} column={COL.final} matchMap={matchMap} isFinal />
        </div>
      </div>
    </div>
  )
}
