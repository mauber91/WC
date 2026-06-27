import { useQuery } from '@tanstack/react-query'
import { NavLink } from 'react-router-dom'
import { api, percent } from '../api/client'
import { flagEmoji } from '../lib/flags'
import { teamPath } from '../lib/teamSlug'
import { useLatestSimulation } from '../hooks/useLatestSimulation'

export type PowerRankingRow = {
  rank: number
  team_id: number
  slug: string
  fifa_code: string
  name: string
  group_code: string | null
  is_host: boolean
  fifa_rank: number
  tournament_elo: number
  fused_strength: number
  power_score: number
  win_group: number
  top_two: number
  round_of_32: number
  round_of_16: number
  quarterfinal: number
  semifinal: number
  final: number
  champion: number
}

const SCORE_GUIDE = [
  {
    term: 'Strength',
    detail: 'Pre-tournament rating on the Elo scale: live tournament Elo blended with FIFA rank and WC winner market prices.',
  },
  {
    term: 'Index',
    detail: 'Overall rank score from the published simulation — knockout rounds weighted (champion counts most, then final, semi, quarter, etc.).',
  },
  {
    term: 'SF',
    detail: 'Share of simulations where the team reaches the semi-finals.',
  },
  {
    term: 'Win WC',
    detail: 'Share of simulations where the team wins the World Cup.',
  },
] as const

function PageHeader({ eyebrow, title, detail }: { eyebrow: string; title: string; detail: string }) {
  return (
    <header className="page-header">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{detail}</p>
      </div>
    </header>
  )
}

function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>
}

function Loading() {
  return <div className="empty">Loading tournament state…</div>
}

export function PowerRankingsPage() {
  const { data: latest, isLoading: simLoading } = useLatestSimulation()
  const rankings = useQuery<PowerRankingRow[]>({
    queryKey: ['power-rankings', latest?.id],
    queryFn: () => api(`/simulations/${latest!.id}/power-rankings`),
    enabled: !!latest,
  })

  return (
    <>
      <PageHeader
        eyebrow="Tournament forecast"
        title="Power Rankings"
        detail="All 48 teams ordered by simulated knockout reach from the published Monte Carlo run."
      />

      {!latest && !simLoading && <Empty text="Published forecast is not available yet." />}
      {latest && rankings.isLoading && <Loading />}

      {latest && rankings.data && (
        <section className="card">
          <div className="card-head">
            <div>
              <span className="eyebrow">Full table</span>
              <h2>All 48 teams</h2>
            </div>
            <span className="meta">{latest.iterations.toLocaleString()} trials · seed {latest.seed}</span>
          </div>

          <dl className="power-rank-legend">
            {SCORE_GUIDE.map(({ term, detail }) => (
              <div key={term}>
                <dt>{term}</dt>
                <dd>{detail}</dd>
              </div>
            ))}
          </dl>

          <div className="table-scroll">
            <table className="power-rankings-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Team</th>
                  <th>Strength</th>
                  <th>Index</th>
                  <th>SF</th>
                  <th>Win WC</th>
                </tr>
              </thead>
              <tbody>
                {rankings.data.map(row => (
                  <tr key={row.team_id} className={row.rank <= 8 ? 'power-rank-top' : undefined}>
                    <td><span className="power-rank-no">{row.rank}</span></td>
                    <td className="team-name">
                      <NavLink className="team-link power-rank-team" to={teamPath({ name: row.name })}>
                        <span aria-hidden>{flagEmoji(row.fifa_code)}</span>
                        <span>{row.name}</span>
                        {row.is_host && <small className="power-rank-host">Host</small>}
                      </NavLink>
                    </td>
                    <td><strong>{row.fused_strength}</strong></td>
                    <td>{row.power_score.toFixed(1)}</td>
                    <td>{percent(row.semifinal)}</td>
                    <td><strong>{percent(row.champion)}</strong></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  )
}
