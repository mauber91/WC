import type { ReactNode } from 'react'
import { useQueries, useQuery } from '@tanstack/react-query'
import { NavLink } from 'react-router-dom'
import { api, percent } from '../api/client'
import { flagEmoji } from '../lib/flags'

export type TeamListItem = {
  id: number
  slug: string
  fifa_code: string
  name: string
  group_id?: number
  is_host?: boolean
}

export type TeamStanding = {
  position: number
  played: number
  won: number
  drawn: number
  lost: number
  goals_for: number
  goals_against: number
  goal_difference: number
  points: number
}

export type TeamDetail = {
  id: number
  slug: string
  fifa_code: string
  name: string
  confederation: string
  group_code: string | null
  is_host: boolean
  ratings: { elo: number | null; fifa_rank: number | null }
  standing: TeamStanding | null
  fixtures: TeamFixture[]
  squad: SquadPlayer[]
}

export type SquadPlayer = {
  id: number
  name: string
  position: string
  squad_number: number
  fc26_overall: number
  market_value_meur: number
  season_ratings: { '2025_26': number | null; '2024_25': number | null; '2023_24': number | null }
  rating: number
  lengthy_injuries: Array<{ started_on: string; ended_on: string | null; days_out: number }>
}

const SHOW_SQUAD = false

export type TeamFixture = {
  id: number
  official_match_number: number
  group_code: string
  team_a: { id: number; name: string; fifa_code: string }
  team_b: { id: number; name: string; fifa_code: string }
  scheduled_at: string
  status: string
  host_country?: string | null
  result?: { team_a_goals: number; team_b_goals: number }
}

const CO_HOST_FIFA: Record<string, string> = {
  USA: 'US',
  CAN: 'CA',
  MEX: 'MX',
}

function hostPlaysAtHome(fifaCode: string, hostCountry?: string | null): boolean {
  if (!hostCountry) return false
  return CO_HOST_FIFA[fifaCode] === hostCountry
}

export type TeamForecast = {
  team_id: number
  win_group: number
  finish_1: number
  finish_2: number
  finish_3: number
  finish_4: number
  top_two: number
  advance_as_third: number
  round_of_32: number
  round_of_16: number
  quarterfinal: number
  semifinal: number
  final: number
  champion: number
  eliminated: number
  expected_group_points: number
  expected_group_goals_for: number
  expected_group_goals_against: number
}

type MatchPrediction = { final: { team_a: number; draw: number; team_b: number } }

function PageHeader({ eyebrow, title, detail, actions }: {
  eyebrow: string
  title: string
  detail: string
  actions?: ReactNode
}) {
  return (
    <header className="page-header">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{detail}</p>
      </div>
      {actions}
    </header>
  )
}

function Probability({ label, value, tone }: { label: string; value: number; tone?: string }) {
  return (
    <div className={`prob ${tone ?? ''}`}>
      <span>{label}<b>{percent(value)}</b></span>
      <i><em style={{ width: percent(value) }} /></i>
    </div>
  )
}

function teamMatchWinProb(teamId: number, match: TeamFixture, prediction: MatchPrediction | undefined): number | null {
  if (!prediction) return null
  if (match.team_a.id === teamId) return prediction.final.team_a
  if (match.team_b.id === teamId) return prediction.final.team_b
  return null
}

function formatValue(value: number): string {
  if (value >= 100) return `€${value.toFixed(0)}m`
  if (value >= 10) return `€${value.toFixed(1)}m`
  return `€${value.toFixed(2)}m`
}

const SEASON_WEIGHTS = [0.5, 0.3, 0.2] as const

function seasonPerformanceScore(seasonRatings: SquadPlayer['season_ratings']): number | null {
  const ratings = [seasonRatings['2025_26'], seasonRatings['2024_25'], seasonRatings['2023_24']]
  const available = SEASON_WEIGHTS.flatMap((weight, index) => {
    const rating = ratings[index]
    return rating == null ? [] : [[weight, rating] as const]
  })
  if (available.length === 0) return null
  const totalWeight = available.reduce((sum, [weight]) => sum + weight, 0)
  const weighted = available.reduce((sum, [weight, rating]) => sum + weight * rating, 0) / totalWeight
  return Math.max(1, Math.min(99, Math.round(weighted * 9.8 + 1)))
}

function seasonRatingTooltip(seasonRatings: SquadPlayer['season_ratings']): string | undefined {
  const labels = ['25/26', '24/25', '23/24'] as const
  const ratings = [seasonRatings['2025_26'], seasonRatings['2024_25'], seasonRatings['2023_24']]
  const parts = labels.flatMap((label, index) => {
    const rating = ratings[index]
    return rating == null ? [] : [`${label}: ${rating.toFixed(1)}`]
  })
  return parts.length > 0 ? parts.join(' · ') : undefined
}

function SquadRatingBar({ rating }: { rating: number }) {
  const tone = rating >= 85 ? 'elite' : rating >= 78 ? 'strong' : ''
  return (
    <div className={`squad-rating ${tone}`}>
      <strong>{rating}</strong>
      <i><em style={{ width: `${rating}%` }} /></i>
    </div>
  )
}

export function TeamPageView({ slug, latestSimulationId }: { slug: string; latestSimulationId?: string }) {
  const team = useQuery<TeamDetail>({
    queryKey: ['team', slug],
    queryFn: () => api(`/teams/${slug}`),
  })

  const forecast = useQuery<TeamForecast>({
    queryKey: ['team-forecast', slug, latestSimulationId],
    queryFn: () => api(`/teams/${slug}/forecast?simulation_id=${latestSimulationId}`),
    enabled: !!latestSimulationId,
  })

  const upcoming = team.data?.fixtures.filter(match => !match.result) ?? []
  const predictions = useQueries({
    queries: upcoming.map(match => ({
      queryKey: ['match-prediction', match.id],
      queryFn: () => api<MatchPrediction>(`/matches/${match.id}/prediction`),
    })),
  })

  const predictionByMatchId = new Map(
    upcoming.map((match, index) => [match.id, predictions[index]?.data]),
  )

  const groupOutcomes = forecast.data ? [
    ['Win group', forecast.data.finish_1],
    ['Finish 2nd', forecast.data.finish_2],
    ['Finish 3rd', forecast.data.finish_3],
    ['Finish 4th', forecast.data.finish_4],
    ['Top two', forecast.data.top_two],
    ['Advance as 3rd', forecast.data.advance_as_third],
  ] as const : []

  const knockoutOutcomes = forecast.data ? [
    ['Round of 32', forecast.data.round_of_32],
    ['Round of 16', forecast.data.round_of_16],
    ['Quarter-final', forecast.data.quarterfinal],
    ['Semi-final', forecast.data.semifinal],
    ['Final', forecast.data.final],
    ['Champion', forecast.data.champion],
    ['Eliminated pre-R32', forecast.data.eliminated],
  ] as const : []

  return (
    <>
      <PageHeader
        eyebrow={[team.data?.fifa_code, team.data?.group_code ? `Group ${team.data.group_code}` : null, team.data?.is_host ? 'Host' : null].filter(Boolean).join(' · ') || 'Team'}
        title={team.data?.name ?? 'Team detail'}
        detail="Live group standing, fixture outlook, and full simulation probabilities."
        actions={<NavLink className="button ghost" to="/teams">All teams</NavLink>}
      />

      {team.data && (
        <div className="team-profile-strip">
          <div><span>Flag</span><strong aria-hidden>{flagEmoji(team.data.fifa_code)}</strong></div>
          <div><span>FIFA rank</span><strong>{team.data.ratings.fifa_rank ?? '—'}</strong></div>
          <div><span>Elo</span><strong>{team.data.ratings.elo ? Math.round(team.data.ratings.elo) : '—'}</strong></div>
          <div><span>Confederation</span><strong>{team.data.confederation}</strong></div>
          {team.data.standing && (
            <div><span>Group pts</span><strong>{team.data.standing.points} ({team.data.standing.played} played)</strong></div>
          )}
        </div>
      )}

      {team.data?.standing && (
        <section className="card">
          <div className="card-head">
            <div><span className="eyebrow">Live table</span><h2>Group {team.data.group_code} standing</h2></div>
          </div>
          <div className="team-standing-summary">
            <span>#{team.data.standing.position}</span>
            <span>{team.data.standing.won}W {team.data.standing.drawn}D {team.data.standing.lost}L</span>
            <span>GD {team.data.standing.goal_difference >= 0 ? '+' : ''}{team.data.standing.goal_difference}</span>
            <span>{team.data.standing.goals_for}–{team.data.standing.goals_against}</span>
          </div>
        </section>
      )}

      {SHOW_SQUAD && team.data && team.data.squad.length > 0 && (
        <section className="card">
          <div className="card-head">
            <div>
              <span className="eyebrow">Squad</span>
              <h2>Player ratings</h2>
            </div>
            <span className="meta">Transfermarkt · EA FC · API-Football (season form)</span>
          </div>
          <table className="standings squad-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Player</th>
                <th>Pos</th>
                <th>FC26</th>
                <th>Season</th>
                <th>Value</th>
                <th>Rating</th>
              </tr>
            </thead>
            <tbody>
              {team.data.squad.map(player => (
                <tr key={player.id} className={player.lengthy_injuries.length > 0 ? 'squad-injured' : undefined}>
                  <td><span className="squad-number">{player.squad_number}</span></td>
                  <td className="team-name">
                    {player.name}
                    {player.lengthy_injuries.length > 0 && (
                      <small className="squad-injury-tag" title={`${player.lengthy_injuries[0].days_out} days out in last 12 months`}>
                        injury
                      </small>
                    )}
                  </td>
                  <td>{player.position}</td>
                  <td>{player.fc26_overall}</td>
                  <td title={seasonRatingTooltip(player.season_ratings)}>
                    {seasonPerformanceScore(player.season_ratings) ?? '—'}
                  </td>
                  <td>{formatValue(player.market_value_meur)}</td>
                  <td><SquadRatingBar rating={player.rating} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {forecast.data && (
        <>
          <section className="card">
            <div className="card-head">
              <div><span className="eyebrow">Simulation</span><h2>Group-stage outcomes</h2></div>
              <span className="meta">From latest completed run</span>
            </div>
            <div className="prob-grid">
              {groupOutcomes.map(([label, value]) => (
                <Probability key={label} label={label} value={value} tone={label === 'Win group' ? 'highlight' : undefined} />
              ))}
            </div>
            <div className="team-expected-row">
              <span>Expected group points <strong>{forecast.data.expected_group_points.toFixed(2)}</strong></span>
              <span>Expected GF/GA <strong>{forecast.data.expected_group_goals_for.toFixed(2)} / {forecast.data.expected_group_goals_against.toFixed(2)}</strong></span>
            </div>
          </section>

          <section className="card">
            <div className="card-head">
              <div><span className="eyebrow">Simulation</span><h2>Knockout path</h2></div>
            </div>
            <div className="prob-grid">
              {knockoutOutcomes.map(([label, value]) => (
                <Probability key={label} label={label} value={value} tone={label === 'Champion' ? 'highlight' : undefined} />
              ))}
            </div>
          </section>
        </>
      )}

      {!forecast.data && latestSimulationId === undefined && (
        <div className="empty">Run a simulation to populate team probabilities.</div>
      )}

      <section className="card">
        <div className="card-head">
          <div><span className="eyebrow">Schedule</span><h2>Fixtures</h2></div>
        </div>
        {team.data?.fixtures.map(match => {
          const opponent = match.team_a.id === team.data?.id ? match.team_b : match.team_a
          const winProb = team.data ? teamMatchWinProb(team.data.id, match, predictionByMatchId.get(match.id)) : null
          const teamHome = hostPlaysAtHome(team.data!.fifa_code, match.host_country)
          const opponentHome = hostPlaysAtHome(opponent.fifa_code, match.host_country)
          return (
            <div className="team-fixture" key={match.id}>
              <span className="team-fixture-meta">M{match.official_match_number} · Group {match.group_code}</span>
              <div className="team-fixture-main">
                <strong>
                  vs {flagEmoji(opponent.fifa_code)} {opponent.name}
                  {teamHome && (
                    <small className="team-fixture-home" title="Co-host playing in their host country">Home</small>
                  )}
                  {!teamHome && opponentHome && (
                    <small className="team-fixture-home opponent" title="Opponent co-host playing in their host country">
                      {opponent.fifa_code} home
                    </small>
                  )}
                </strong>
                <span>
                  {match.result
                    ? `${match.result.team_a_goals}–${match.result.team_b_goals} (FT)`
                    : new Date(match.scheduled_at).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
                </span>
              </div>
              {winProb != null && !match.result && (
                <div className="team-fixture-model">
                  <span>Model win</span><strong>{percent(winProb)}</strong>
                  <span>Draw {percent(predictionByMatchId.get(match.id)!.final.draw)}</span>
                </div>
              )}
            </div>
          )
        })}
      </section>
    </>
  )
}
