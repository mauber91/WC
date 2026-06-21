import { flagEmoji } from '../../lib/flags'
import type { ScenarioBracketMatch, ScenarioTeam } from './scenarioEngine'

type Slot = { match: number; row: number; span: number; sources?: [number, number] }

const R32_SLOTS: Slot[] = [
  { match: 73, row: 1, span: 1 }, { match: 75, row: 2, span: 1 },
  { match: 74, row: 3, span: 1 }, { match: 77, row: 4, span: 1 },
  { match: 83, row: 5, span: 1 }, { match: 84, row: 6, span: 1 },
  { match: 81, row: 7, span: 1 }, { match: 82, row: 8, span: 1 },
  { match: 76, row: 9, span: 1 }, { match: 78, row: 10, span: 1 },
  { match: 79, row: 11, span: 1 }, { match: 80, row: 12, span: 1 },
  { match: 86, row: 13, span: 1 }, { match: 88, row: 14, span: 1 },
  { match: 85, row: 15, span: 1 }, { match: 87, row: 16, span: 1 },
]

const R16_SLOTS: Slot[] = [
  { match: 90, row: 1, span: 2, sources: [73, 75] },
  { match: 89, row: 3, span: 2, sources: [74, 77] },
  { match: 93, row: 5, span: 2, sources: [83, 84] },
  { match: 94, row: 7, span: 2, sources: [81, 82] },
  { match: 91, row: 9, span: 2, sources: [76, 78] },
  { match: 92, row: 11, span: 2, sources: [79, 80] },
  { match: 95, row: 13, span: 2, sources: [86, 88] },
  { match: 96, row: 15, span: 2, sources: [85, 87] },
]

const QF_SLOTS: Slot[] = [
  { match: 97, row: 1, span: 4, sources: [89, 90] },
  { match: 98, row: 5, span: 4, sources: [93, 94] },
  { match: 99, row: 9, span: 4, sources: [91, 92] },
  { match: 100, row: 13, span: 4, sources: [95, 96] },
]

const SF_SLOTS: Slot[] = [
  { match: 101, row: 1, span: 8, sources: [97, 98] },
  { match: 102, row: 9, span: 8, sources: [99, 100] },
]

const FINAL_SLOT: Slot = { match: 104, row: 1, span: 16, sources: [101, 102] }

function TeamLine({ team, source }: { team: ScenarioTeam; source: string }) {
  return (
    <div className="manual-bracket-team">
      <span className="manual-bracket-flag" aria-hidden>{flagEmoji(team.fifa_code)}</span>
      <span><strong>{team.name}</strong><small>{source}</small></span>
    </div>
  )
}

function RoundOf32Card({ match }: { match: ScenarioBracketMatch }) {
  return (
    <article className="manual-bracket-card confirmed">
      <header><span>Group stage set</span><b>M{match.matchNumber}</b></header>
      <TeamLine team={match.teamA} source={match.sourceA} />
      <TeamLine team={match.teamB} source={match.sourceB} />
    </article>
  )
}

function PlaceholderCard({ slot }: { slot: Slot }) {
  return (
    <article className="manual-bracket-card placeholder">
      <header><span>Awaiting knockout</span><b>M{slot.match}</b></header>
      {slot.sources?.map(source => <div className="manual-bracket-source" key={source}>Winner M{source}</div>)}
    </article>
  )
}

function RoundColumn({ title, slots, matches }: {
  title: string
  slots: Slot[]
  matches?: Map<number, ScenarioBracketMatch>
}) {
  return (
    <section className="manual-bracket-round">
      <h3>{title}</h3>
      <div className="manual-bracket-round-grid">
        {slots.map(slot => (
          <div
            className="manual-bracket-slot"
            style={{ gridRow: `${slot.row} / span ${slot.span}` }}
            key={slot.match}
          >
            {matches?.get(slot.match)
              ? <RoundOf32Card match={matches.get(slot.match)!} />
              : <PlaceholderCard slot={slot} />}
          </div>
        ))}
      </div>
    </section>
  )
}

export function ScenarioBracket({ matches }: { matches: ScenarioBracketMatch[] }) {
  const matchMap = new Map(matches.map(match => [match.matchNumber, match]))
  return (
    <div className="manual-bracket-wrap">
      <div className="manual-bracket-note">
        <span className="local-only-badge">Browser scenario</span>
        The Round of 32 is fixed by your scores. Later rounds remain open because no knockout winners were selected.
      </div>
      <div className="manual-bracket-scroll">
        <div className="manual-bracket-columns">
          <RoundColumn title="Round of 32" slots={R32_SLOTS} matches={matchMap} />
          <RoundColumn title="Round of 16" slots={R16_SLOTS} />
          <RoundColumn title="Quarter-finals" slots={QF_SLOTS} />
          <RoundColumn title="Semi-finals" slots={SF_SLOTS} />
          <RoundColumn title="Final" slots={[FINAL_SLOT]} />
        </div>
      </div>
    </div>
  )
}
