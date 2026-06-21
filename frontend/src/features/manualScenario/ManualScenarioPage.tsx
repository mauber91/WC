import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api/client'
import { flagEmoji } from '../../lib/flags'
import { ScenarioBracket } from './ScenarioBracket'
import {
  calculateScenario,
  isCompleteScore,
  type ManualScores,
  type ScenarioGroup,
  type ScenarioMatch,
  type ScenarioStanding,
} from './scenarioEngine'
import {
  clearScenarioScores,
  downloadScenarioScores,
  loadScenarioScores,
  saveScenarioScores,
} from './scenarioStorage'

function scoreValue(value: number | null | undefined): string | number {
  return value == null ? '' : value
}

function parseGoal(value: string): number | null {
  if (value === '') return null
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed >= 0 ? Math.min(parsed, 99) : null
}

function ScenarioProgress({ entered, total }: { entered: number; total: number }) {
  const percentage = total ? Math.round((entered / total) * 100) : 100
  return (
    <div className="scenario-progress" aria-label={`${entered} of ${total} results entered`}>
      <div><span>Scenario progress</span><strong>{entered} / {total}</strong></div>
      <i><em style={{ width: `${percentage}%` }} /></i>
      <small>{entered === total ? 'Bracket ready' : `${total - entered} scores still needed`}</small>
    </div>
  )
}

function FixtureScore({ match, score, onChange }: {
  match: ScenarioMatch
  score: { team_a_goals: number | null; team_b_goals: number | null } | undefined
  onChange: (side: 'team_a_goals' | 'team_b_goals', value: number | null) => void
}) {
  if (!match.team_a || !match.team_b) return null
  const complete = isCompleteScore(score)
  return (
    <div className={`scenario-fixture${complete ? ' complete' : ''}`}>
      <div className="scenario-fixture-meta">
        <span>M{match.official_match_number}</span>
        <time dateTime={match.scheduled_at}>{new Date(match.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</time>
      </div>
      <label>
        <span><span className="scenario-country-name"><span className="scenario-flag" aria-hidden>{flagEmoji(match.team_a.fifa_code)}</span>{match.team_a.name}</span><small>{match.team_a.fifa_code}</small></span>
        <input
          aria-label={`${match.team_a.name} goals against ${match.team_b.name}`}
          inputMode="numeric"
          min="0"
          max="99"
          type="number"
          value={scoreValue(score?.team_a_goals)}
          onChange={event => onChange('team_a_goals', parseGoal(event.target.value))}
        />
      </label>
      <label>
        <span><span className="scenario-country-name"><span className="scenario-flag" aria-hidden>{flagEmoji(match.team_b.fifa_code)}</span>{match.team_b.name}</span><small>{match.team_b.fifa_code}</small></span>
        <input
          aria-label={`${match.team_b.name} goals against ${match.team_a.name}`}
          inputMode="numeric"
          min="0"
          max="99"
          type="number"
          value={scoreValue(score?.team_b_goals)}
          onChange={event => onChange('team_b_goals', parseGoal(event.target.value))}
        />
      </label>
    </div>
  )
}

function GroupTable({ code, rows, complete, qualifiedThirds }: {
  code: string
  rows: ScenarioStanding[]
  complete: boolean
  qualifiedThirds: Set<number>
}) {
  return (
    <section className="scenario-table-card">
      <header><span>Group</span><strong>{code}</strong><small>{complete ? 'Complete' : 'Live preview'}</small></header>
      <table>
        <thead><tr><th>#</th><th>Team</th><th>GD</th><th>Pts</th></tr></thead>
        <tbody>{rows.map(row => {
          const status = row.position <= 2 ? 'qualified' : qualifiedThirds.has(row.team.id) ? 'third-qualified' : ''
          return <tr className={status} key={row.team.id}>
            <td>{row.position}</td><td><span className="scenario-country-name"><span className="scenario-flag" aria-hidden>{flagEmoji(row.team.fifa_code)}</span>{row.team.name}</span></td>
            <td>{row.goalDifference > 0 ? '+' : ''}{row.goalDifference}</td><td><strong>{row.points}</strong></td>
          </tr>
        })}</tbody>
      </table>
    </section>
  )
}

function ThirdPlaceTable({ rows, complete, groupByTeam }: {
  rows: ScenarioStanding[]
  complete: boolean
  groupByTeam: Map<number, string>
}) {
  function tiebreakFor(row: ScenarioStanding): { label: string; detail: string } | null {
    const pointsAndGoalDifferencePeers = rows.filter(peer =>
      peer.points === row.points && peer.goalDifference === row.goalDifference,
    )
    if (pointsAndGoalDifferencePeers.length < 2) return null

    const parts = [`GF ${row.goalsFor}`]
    const goalsScoredPeers = pointsAndGoalDifferencePeers.filter(peer => peer.goalsFor === row.goalsFor)
    if (goalsScoredPeers.length > 1) {
      const hasCompleteFairPlay = goalsScoredPeers.every(peer => peer.conductScore != null)
      if (hasCompleteFairPlay) {
        parts.push(`FP ${row.conductScore}`)
        const fairPlayPeers = goalsScoredPeers.filter(peer => peer.conductScore === row.conductScore)
        if (fairPlayPeers.length > 1) parts.push(`FIFA #${row.fifaRank ?? '—'}`)
      } else {
        parts.push(`FIFA #${row.fifaRank ?? '—'}`)
      }
    }

    return {
      label: parts.join(' → '),
      detail: `Tied on ${row.points} points and ${row.goalDifference >= 0 ? '+' : ''}${row.goalDifference} goal difference. Compared next by goals scored${parts.length > 1 ? ', then ' + (parts[1].startsWith('FP') ? 'fair play' : 'FIFA ranking') : ''}.`,
    }
  }

  return (
    <section className="card scenario-thirds">
      <div className="card-head"><div><span className="eyebrow">Cross-group ranking</span><h2>Best third-place teams</h2></div><span className="meta">{complete ? 'Top eight advance' : 'Partial table'}</span></div>
      <div className="third-tiebreak-guide" aria-label="Third-place tiebreak order">
        <strong>How equal records are split</strong>
        <ol>
          <li><b>1</b> Points</li><li><b>2</b> Goal difference</li><li><b>3</b> Goals scored</li>
          <li><b>4</b> Fair play</li><li><b>5</b> FIFA ranking</li>
        </ol>
        <p>When teams are level on points and goal difference, the deciding values are shown in the Tiebreak column.</p>
      </div>
      <div className="table-scroll"><table><thead><tr><th>#</th><th>Team</th><th>Group</th><th>P</th><th>GD</th><th>GF</th><th>Pts</th><th>Tiebreak</th><th>Status</th></tr></thead>
        <tbody>{rows.map((row, index) => {
          const tiebreak = tiebreakFor(row)
          return <tr className={`${index < 8 ? 'third-qualified' : ''} ${tiebreak ? 'tiebreak-active' : ''}`.trim()} key={row.team.id}>
          <td>{index + 1}</td><td><span className="scenario-country-name"><span className="scenario-flag" aria-hidden>{flagEmoji(row.team.fifa_code)}</span>{row.team.name}</span></td><td>{groupByTeam.get(row.team.id) ?? '—'}</td><td>{row.played}</td>
          <td>{row.goalDifference > 0 ? '+' : ''}{row.goalDifference}</td><td>{row.goalsFor}</td><td><strong>{row.points}</strong></td>
          <td>{tiebreak ? <span className="tiebreak-decision" title={tiebreak.detail}><i aria-hidden="true" />{tiebreak.label}</span> : <span className="tiebreak-none">—</span>}</td>
          <td><span className={`scenario-status ${index < 8 ? 'in' : 'out'}`}>{index < 8 ? complete ? 'Advances' : 'In top 8' : 'Out'}</span></td>
        </tr>})}</tbody>
      </table></div>
    </section>
  )
}

export function ManualScenarioPage({
  readOnly = false,
  fixedScores,
  title = 'Manual group scenario',
  description = 'Enter final scores for every unfinished group match and see the exact Round-of-32 slots those results create. This workspace never writes to the tournament database or changes simulations.',
}: {
  readOnly?: boolean
  fixedScores?: ManualScores
  title?: string
  description?: string
} = {}) {
  const groups = useQuery<ScenarioGroup[]>({ queryKey: ['groups'], queryFn: () => api('/groups') })
  const matches = useQuery<ScenarioMatch[]>({ queryKey: ['matches'], queryFn: () => api('/matches') })
  const [scores, setScores] = useState<ManualScores>(() => fixedScores ?? loadScenarioScores())

  useEffect(() => {
    if (readOnly || fixedScores) return
    saveScenarioScores(scores)
  }, [scores, readOnly, fixedScores])

  const outcome = useMemo(() => {
    if (!groups.data || !matches.data) return null
    return calculateScenario(groups.data, matches.data, scores)
  }, [groups.data, matches.data, scores])

  const remainingByGroup = useMemo(() => {
    const output = new Map<string, ScenarioMatch[]>()
    outcome?.remainingMatches.forEach(match => {
      if (!match.group_code) return
      const bucket = output.get(match.group_code) ?? []
      bucket.push(match)
      output.set(match.group_code, bucket)
    })
    return output
  }, [outcome])

  function updateScore(matchNumber: number, side: 'team_a_goals' | 'team_b_goals', value: number | null) {
    setScores(current => {
      const key = String(matchNumber)
      const nextScore = { team_a_goals: null, team_b_goals: null, ...current[key], [side]: value }
      if (nextScore.team_a_goals == null && nextScore.team_b_goals == null) {
        const rest = { ...current }
        delete rest[key]
        return rest
      }
      return { ...current, [key]: nextScore }
    })
  }

  function clearAll() {
    clearScenarioScores()
    setScores({})
  }

  function fillEmptyDraws() {
    if (!outcome) return
    setScores(current => {
      const next = { ...current }
      outcome.remainingMatches.forEach(match => {
        const key = String(match.official_match_number)
        if (!next[key] || (next[key].team_a_goals == null && next[key].team_b_goals == null)) {
          next[key] = { team_a_goals: 0, team_b_goals: 0 }
        }
      })
      return next
    })
  }

  const complete = outcome != null && outcome.enteredCount === outcome.totalRemaining
  const qualifiedThirds = new Set(complete ? outcome.thirdPlace.slice(0, 8).map(row => row.team.id) : [])
  const groupByTeam = new Map(groups.data?.flatMap(group => group.teams.map(team => [team.id, group.code] as const)) ?? [])

  return (
    <>
      <header className="page-header">
        <div><span className="eyebrow">{readOnly ? 'Published what-if' : 'What-if workspace'}</span><h1>{title}</h1><p>{description}</p></div>
        {!readOnly && <span className="local-only-badge">Saved in this browser only</span>}
      </header>

      {groups.isLoading || matches.isLoading || !outcome ? <div className="empty">Loading official tournament state…</div> : <>
        {!readOnly && <section className="card scenario-intro">
          <ScenarioProgress entered={outcome.enteredCount} total={outcome.totalRemaining} />
          <div className="scenario-actions">
            <button type="button" className="button ghost" onClick={fillEmptyDraws}>Fill empty fixtures 0–0</button>
            <button type="button" className="button ghost" disabled={!Object.keys(scores).length} onClick={() => downloadScenarioScores(scores)}>Export for publish</button>
            <button type="button" className="button ghost danger-button" disabled={!Object.keys(scores).length} onClick={clearAll}>Clear scenario</button>
          </div>
        </section>}

        {readOnly && complete && <section className="card scenario-intro read-only">
          <ScenarioProgress entered={outcome.enteredCount} total={outcome.totalRemaining} />
          <span className="meta">Fixed scenario · not part of the Monte Carlo forecast</span>
        </section>}

        {outcome.warnings.map(warning => <div className="warning" key={warning}>{warning}</div>)}

        {!readOnly && <section className="scenario-fixtures-section">
          <div className="card-head"><div><span className="eyebrow">Your inputs</span><h2>Remaining group fixtures</h2></div><span className="meta">Official completed scores are locked</span></div>
          <div className="scenario-group-grid">
            {groups.data.map(group => <section className="card scenario-group-card" id={`scenario-group-${group.code}`} key={group.code}>
              <header><div><span>Group</span><strong>{group.code}</strong></div><small>{remainingByGroup.get(group.code)?.filter(match => isCompleteScore(scores[String(match.official_match_number)])).length ?? 0} / {remainingByGroup.get(group.code)?.length ?? 0}</small></header>
              {(remainingByGroup.get(group.code) ?? []).map(match => <FixtureScore
                key={match.id}
                match={match}
                score={scores[String(match.official_match_number)]}
                onChange={(side, value) => updateScore(match.official_match_number, side, value)}
              />)}
            </section>)}
          </div>
        </section>}

        <section className="scenario-standings-section">
          <div className="card-head"><div><span className="eyebrow">{readOnly ? 'Published scenario' : 'Calculated locally'}</span><h2>Scenario standings</h2></div><span className="meta">Head-to-head rules applied</span></div>
          <div className="scenario-tables-grid">{outcome.tables.map(table => <GroupTable key={table.code} code={table.code} rows={table.rows} complete={table.complete} qualifiedThirds={qualifiedThirds} />)}</div>
        </section>

        <ThirdPlaceTable rows={outcome.thirdPlace} complete={complete} groupByTeam={groupByTeam} />

        <section className="card scenario-bracket-card">
          <div className="card-head"><div><span className="eyebrow">Official slot assignment</span><h2>Knockout bracket</h2></div><span className="meta">FIFA Annex C</span></div>
          {outcome.bracket
            ? <ScenarioBracket matches={outcome.bracket} />
            : <div className="scenario-bracket-locked"><strong>{outcome.totalRemaining - outcome.enteredCount} scores to go</strong><p>The bracket appears after every remaining group fixture has both scores.</p>{!readOnly && <a href="#scenario-group-A" className="button primary">Continue entering results</a>}</div>}
        </section>
      </>}
    </>
  )
}
