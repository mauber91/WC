import { useMemo, useState } from 'react'
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
    detail: 'Pre-tournament rating on the Elo scale: mostly live tournament Elo (results so far), with smaller blends from FIFA rank and WC winner markets.',
  },
  {
    term: 'Index',
    detail: '70% simulation knockout reach + 30% WC-winner market prices (normalized), on a 0–100 scale.',
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

type SortKey = 'rank' | 'team' | 'strength' | 'index' | 'sf' | 'champion'

const SORT_COLUMNS: { key: SortKey; label: string; align: 'left' | 'right' }[] = [
  { key: 'rank', label: '#', align: 'left' },
  { key: 'team', label: 'Team', align: 'left' },
  { key: 'strength', label: 'Strength', align: 'right' },
  { key: 'index', label: 'Index', align: 'right' },
  { key: 'sf', label: 'SF', align: 'right' },
  { key: 'champion', label: 'Win WC', align: 'right' },
]

const HOST_TOOLTIP = 'Co-host nation — receives a small model boost when playing at home.'

function sortValue(row: PowerRankingRow, key: SortKey): number | string {
  switch (key) {
    case 'rank': return row.rank
    case 'team': return row.name
    case 'strength': return row.fused_strength
    case 'index': return row.power_score
    case 'sf': return row.semifinal
    case 'champion': return row.champion
  }
}

function compareRows(a: PowerRankingRow, b: PowerRankingRow, key: SortKey, dir: 'asc' | 'desc'): number {
  const av = sortValue(a, key)
  const bv = sortValue(b, key)
  let cmp = 0
  if (typeof av === 'string' && typeof bv === 'string') {
    cmp = av.localeCompare(bv)
  } else {
    cmp = (av as number) - (bv as number)
  }
  if (cmp === 0) cmp = a.name.localeCompare(b.name)
  return dir === 'asc' ? cmp : -cmp
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
  const [sortKey, setSortKey] = useState<SortKey>('index')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const rankings = useQuery<PowerRankingRow[]>({
    queryKey: ['power-rankings', latest?.id],
    queryFn: () => api(`/simulations/${latest!.id}/power-rankings`),
    enabled: !!latest,
  })

  const sortedRows = useMemo(() => {
    if (!rankings.data) return []
    return [...rankings.data].sort((a, b) => compareRows(a, b, sortKey, sortDir))
  }, [rankings.data, sortKey, sortDir])

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(dir => (dir === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir(key === 'team' ? 'asc' : 'desc')
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Tournament forecast"
        title="Power Rankings"
        detail="All 48 teams ranked by Index (simulation reach blended with WC-winner markets). Click a column header to sort."
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
                  {SORT_COLUMNS.map(({ key, label, align }) => (
                    <th
                      key={key}
                      className={align === 'left' ? 'power-rank-col-left' : 'power-rank-col-num'}
                      aria-sort={sortKey === key ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                    >
                      <button
                        type="button"
                        className={`power-rank-sort${sortKey === key ? ' active' : ''}${align === 'right' ? ' power-rank-sort-end' : ''}`}
                        onClick={() => toggleSort(key)}
                      >
                        {label}
                        {sortKey === key && (
                          <span className="power-rank-sort-mark" aria-hidden>{sortDir === 'asc' ? '↑' : '↓'}</span>
                        )}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedRows.map((row, index) => (
                  <tr key={row.team_id} className={index < 8 ? 'power-rank-top' : undefined}>
                    <td className="power-rank-col-left"><span className="power-rank-no">{index + 1}</span></td>
                    <td className="team-name power-rank-col-left">
                      <NavLink className="team-link power-rank-team" to={teamPath({ name: row.name })}>
                        <span aria-hidden>{flagEmoji(row.fifa_code)}</span>
                        <span>{row.name}</span>
                        {row.is_host && (
                          <small className="power-rank-host" title={HOST_TOOLTIP}>Host</small>
                        )}
                      </NavLink>
                    </td>
                    <td className="power-rank-col-num"><strong>{row.fused_strength}</strong></td>
                    <td className="power-rank-col-num">{row.power_score.toFixed(1)}</td>
                    <td className="power-rank-col-num">{percent(row.semifinal)}</td>
                    <td className="power-rank-col-num"><strong>{percent(row.champion)}</strong></td>
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
