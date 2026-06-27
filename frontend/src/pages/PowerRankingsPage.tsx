import { useQuery } from '@tanstack/react-query'
import { NavLink } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
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

  const topChart = rankings.data?.slice(0, 12) ?? []

  return (
    <>
      <PageHeader
        eyebrow="Tournament forecast"
        title="Power rankings"
        detail="All 48 teams ordered by simulated knockout reach. Strength blends live Elo, FIFA rank, and WC winner markets; the index weights how deep each team goes in the published Monte Carlo run."
      />

      {!latest && !simLoading && <Empty text="Published forecast is not available yet." />}
      {latest && rankings.isLoading && <Loading />}

      {latest && rankings.data && (
        <>
          <section className="card">
            <div className="card-head">
              <div>
                <span className="eyebrow">Top contenders</span>
                <h2>Win the tournament</h2>
              </div>
              <span className="meta">{latest.iterations.toLocaleString()} trials · seed {latest.seed}</span>
            </div>
            <div className="chart">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={topChart} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                  <XAxis type="number" tickFormatter={value => percent(value)} />
                  <YAxis dataKey="fifa_code" type="category" width={42} />
                  <Tooltip formatter={(value) => percent(Number(value))} />
                  <Bar dataKey="champion" fill="#c7ff55" radius={[0, 6, 6, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </section>

          <section className="card">
            <div className="card-head">
              <div>
                <span className="eyebrow">Full table</span>
                <h2>All 48 teams</h2>
              </div>
            </div>
            <div className="table-scroll">
              <table className="power-rankings-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Team</th>
                    <th>Grp</th>
                    <th title="Fused Elo + FIFA + WC winner market">Strength</th>
                    <th>Index</th>
                    <th>Win grp</th>
                    <th>Top 2</th>
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
                      <td>{row.group_code ?? '—'}</td>
                      <td><strong>{row.fused_strength}</strong></td>
                      <td>{row.power_score.toFixed(1)}</td>
                      <td>{percent(row.win_group)}</td>
                      <td>{percent(row.top_two)}</td>
                      <td>{percent(row.semifinal)}</td>
                      <td><strong>{percent(row.champion)}</strong></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </>
  )
}
