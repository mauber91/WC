import { useEffect, useMemo, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, percent } from './api/client'
import { BracketBoard, type BracketRow } from './components/BracketBoard'
import type { SimulationGroupOutcome } from './features/manualScenario/scenarioEngine'
import { TeamPageView } from './components/TeamPage'
import { isPublishedMode } from './config/appMode'
import { ManualScenarioPage } from './features/manualScenario/ManualScenarioPage'
import { MethodologyPage } from './pages/MethodologyPage'
import { PowerRankingsPage } from './pages/PowerRankingsPage'
import { useLatestSimulation, useRuns, type SimulationRun } from './hooks/useLatestSimulation'
import { flagEmoji } from './lib/flags'
import { teamPath } from './lib/teamSlug'
import { RouteSeo } from './seo/RouteSeo'
import { SITE_SHORT_NAME } from './seo/siteMeta'
import './App.css'

type Team = { id: number; slug: string; fifa_code: string; name: string; country_code?: string; group_id?: number; is_host?: boolean }
type Group = { id: number; code: string; display_name: string; teams: Team[] }
type Standing = { position: number; team_id: number; name: string; played: number; won: number; drawn: number; lost: number; goals_for: number; goals_against: number; goal_difference: number; points: number }
type Match = { id: number; official_match_number: number; group_code: string; team_a: Team; team_b: Team; scheduled_at: string; status: string; result?: { team_a_goals: number; team_b_goals: number; revision: number } }
type Run = SimulationRun
type TeamForecast = { team_id: number; name: string; fifa_code: string; win_group: number; finish_1: number; finish_2: number; finish_3: number; finish_4: number; top_two: number; advance_as_third: number; round_of_32: number; round_of_16: number; quarterfinal: number; semifinal: number; final: number; champion: number; eliminated: number; expected_group_points: number; expected_group_goals_for: number; expected_group_goals_against: number; r32_rivals?: { as_winner: Array<{ team_id: number; name: string; fifa_code: string; probability: number }>; as_runner_up: Array<{ team_id: number; name: string; fifa_code: string; probability: number }>; as_third: Array<{ team_id: number; name: string; fifa_code: string; probability: number }> } }
type Projection = { teams: TeamForecast[] }
type Triple = { team_a: number; draw: number; team_b: number }
type TacticalStats = {
  possession_a: number
  possession_b: number
  shots_a: number
  shots_b: number
  sot_a: number
  sot_b: number
  xg_a: number
  xg_b: number
}
type StyleInteraction = { key: string; label: string; value: number; coefficient: number; contribution: number }
type StyleMatchup = {
  favor: 'team_a' | 'team_b' | 'even'
  net_xg_delta_a: number
  narrative: string
  interaction_scores: StyleInteraction[]
}
type MatchPrediction = {
  match_id?: number | null
  official_match_number?: number
  team_a_id?: number
  team_b_id?: number
  is_knockout?: boolean
  data_quality: string
  lambda_a: number
  lambda_b: number
  final: Triple
  model: Triple
  market: Triple | null
  score_distribution: number[][]
  tactical_stats?: TacticalStats
  style_matchup?: StyleMatchup
  advance_probability_a?: number
}
type ImportPreview = { id: string; record_count: number; status: string; errors: { row: number; message: string }[] }
type MarketSyncReport = {
  fixtures: Array<{ match_id: number; match_number: number; stored_rows: number; platforms: string[]; warnings: string[] }>
  wc_winner: { teams_matched: number; stored_rows: number; platforms: string[]; top_favorites: Array<{ fifa_code: string; probability: number }>; warnings: string[] }
}
type MatchReportData = {
  document: { filename: string; status: string; page_count: number }
  run: { status: string; quality_score: number | null; coverage: number | null; stats: Record<string, unknown> }
  pages: unknown[]
  participants: unknown[]
  observations: unknown[]
  events: unknown[]
  spatial_features: unknown[]
  network_edges: unknown[]
  timeseries_points: unknown[]
  issues: unknown[]
  [key: string]: unknown
}

type NavItem = { to: string; label: string; activePrefix?: string; featured?: boolean; hint?: string; archive?: boolean }

const knockoutNav: NavItem[] = [
  { to: '/bracket', label: 'Projected bracket', activePrefix: '/bracket', featured: true, hint: 'Advance odds · tactical fit' },
  { to: '/rankings', label: 'Power rankings', activePrefix: '/rankings' },
  { to: '/teams', label: 'Teams', activePrefix: '/teams' },
]

const scenarioNav: NavItem[] = [
  { to: '/scenario', label: 'Your bracket', activePrefix: '/scenario', hint: 'Play out scores in your browser' },
]

const groupStageArchiveNav: NavItem[] = [
  { to: '/groups/A', label: 'Final standings', activePrefix: '/groups', archive: true },
  { to: '/matches', label: 'Group matches', activePrefix: '/matches', archive: true },
]

const referenceNav: NavItem[] = [
  { to: '/methodology', label: 'Methodology', activePrefix: '/methodology', archive: true },
]

const localKnockoutNav: NavItem[] = [
  ...knockoutNav,
  { to: '/simulator', label: 'Simulator', activePrefix: '/simulator' },
]

const localAdminNav: NavItem[] = [
  { to: '/admin/data', label: 'Admin', activePrefix: '/admin', archive: true },
]

function SidebarNav({ items, sectionLabel, onNavigate }: { items: NavItem[]; sectionLabel?: string; onNavigate?: () => void }) {
  const location = useLocation()
  return (
    <div className="sidebar-nav-section">
      {sectionLabel && <span className="sidebar-section-label">{sectionLabel}</span>}
      <nav>
        {items.map(({ to, label, activePrefix, featured, hint, archive }) => {
          const active = activePrefix ? location.pathname.startsWith(activePrefix) : undefined
          return (
            <NavLink
              key={to}
              to={to}
              onClick={onNavigate}
              className={({ isActive }) => {
                const activeClass = activePrefix ? (active ? 'active' : '') : (isActive ? 'active' : '')
                return [activeClass, featured ? 'nav-featured' : '', archive ? 'nav-archive' : ''].filter(Boolean).join(' ')
              }}
            >
              <span className="nav-link-copy">
                {featured && <span className="nav-featured-mark" aria-hidden>▴</span>}
                <span className="nav-link-label">{label}</span>
                {hint && <small className="nav-link-hint">{hint}</small>}
              </span>
            </NavLink>
          )
        })}
      </nav>
    </div>
  )
}

function App() {
  const [menuOpen, setMenuOpen] = useState(false)
  return <div className="app-shell">
    <RouteSeo />
    <aside className={`sidebar${menuOpen ? ' open' : ''}`}>
      <div className="sidebar-top">
        <div className="brand"><span className="brand-mark">26</span><div><strong>{SITE_SHORT_NAME}</strong><small>{isPublishedMode ? 'Knockout stage' : 'World Cup intelligence'}</small></div></div>
        <button type="button" className="sidebar-menu-toggle" aria-label="Toggle navigation" aria-expanded={menuOpen} onClick={() => setMenuOpen(open => !open)}><span /><span /><span /></button>
      </div>
      <div className="sidebar-body">
      {isPublishedMode ? <>
        <SidebarNav items={knockoutNav} sectionLabel="Knockout stage" onNavigate={() => setMenuOpen(false)} />
        <SidebarNav items={scenarioNav} sectionLabel="What-if" onNavigate={() => setMenuOpen(false)} />
        <SidebarNav items={groupStageArchiveNav} sectionLabel="Group stage archive" onNavigate={() => setMenuOpen(false)} />
        <SidebarNav items={referenceNav} onNavigate={() => setMenuOpen(false)} />
        <SidebarPublishedStatus />
      </> : <>
        <SidebarNav items={localKnockoutNav} sectionLabel="Knockout stage" onNavigate={() => setMenuOpen(false)} />
        <SidebarNav items={scenarioNav} sectionLabel="What-if" onNavigate={() => setMenuOpen(false)} />
        <SidebarSimulationStatus />
        <SidebarNav items={groupStageArchiveNav} sectionLabel="Group stage archive" onNavigate={() => setMenuOpen(false)} />
        <SidebarNav items={referenceNav} onNavigate={() => setMenuOpen(false)} />
        <SidebarNav items={localAdminNav} onNavigate={() => setMenuOpen(false)} />
      </>}
      <div className="sidebar-note"><span className="live-dot" /> {isPublishedMode ? 'Knockout forecast live' : 'Local data workspace'}<small>{isPublishedMode ? 'Open any bracket match for advance odds and tactical fit.' : 'Probabilities, not promises.'}</small></div>
      </div>
    </aside>
    {menuOpen && <button type="button" className="sidebar-backdrop" aria-hidden tabIndex={-1} onClick={() => setMenuOpen(false)} />}
    <main className="main"><Routes>
      <Route path="/" element={<Navigate to={isPublishedMode ? '/bracket' : '/groups/A'} replace />} />
      <Route path="/groups/:code" element={<GroupPage />} />
      <Route path="/matches" element={<MatchesPage />} />
      <Route path="/matches/:id" element={<MatchPage />} />
      <Route path="/knockout/:matchNumber" element={<KnockoutMatchPage />} />
      {!isPublishedMode && <Route path="/simulator" element={<SimulatorPage />} />}
      <Route path="/scenario" element={<ManualScenarioPage />} />
      <Route path="/methodology" element={<MethodologyPage />} />
      <Route path="/bracket" element={<BracketPage />} />
      <Route path="/rankings" element={<PowerRankingsPage />} />
      <Route path="/teams" element={<TeamsPage />} />
      <Route path="/teams/:slug" element={<TeamPage />} />
      {!isPublishedMode && <Route path="/admin/data" element={<AdminPage />} />}
      {isPublishedMode && <Route path="/simulator" element={<Navigate to="/bracket" replace />} />}
      {isPublishedMode && <Route path="/admin/*" element={<Navigate to="/bracket" replace />} />}
    </Routes></main>
  </div>
}

function PageHeader({ eyebrow, title, detail, actions }: { eyebrow: string; title: string; detail: string; actions?: React.ReactNode }) {
  return <header className="page-header"><div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1><p>{detail}</p></div>{actions}</header>
}

function GroupPage() {
  const { code = 'A' } = useParams()
  const groups = useQuery<Group[]>({ queryKey: ['groups'], queryFn: () => api('/groups') })
  const standings = useQuery<{ provisional: boolean; warnings: string[]; rows: Standing[]; as_of: string }>({ queryKey: ['standings', code], queryFn: () => api(`/groups/${code}/standings`) })
  const { data: latest } = useLatestSimulation()
  const projection = useQuery<Projection>({ queryKey: ['projection', code, latest?.id], queryFn: () => api(`/groups/${code}/projection?simulation_id=${latest?.id}`), enabled: !!latest })
  const teamById = useMemo(() => {
    const map = new Map<number, Team>()
    groups.data?.forEach(group => group.teams.forEach(team => map.set(team.id, team)))
    return map
  }, [groups.data])
  return <>
    <PageHeader eyebrow="Live group state" title={`Group ${code}`} detail="Official results stay fixed. Every remaining fixture is modeled across the full tournament state." actions={<Freshness provisional={standings.data?.provisional} />} />
    <div className="group-tabs">{groups.data?.map(group => (
      <NavLink key={group.code} to={`/groups/${group.code}`} className={({ isActive }) => isActive ? 'active' : ''}>
        {group.code}
      </NavLink>
    ))}</div>
    {standings.data?.warnings.map(warning => <div className="warning" key={warning}>{warning}</div>)}
    <section className="card"><div className="card-head"><div><span className="eyebrow">Current table</span><h2>What has happened</h2></div><span className="meta">As of {standings.data ? new Date(standings.data.as_of).toLocaleString() : '—'}</span></div>
      {standings.isLoading ? <Loading /> : <table className="standings"><thead><tr><th>#</th><th>Team</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GD</th><th>Pts</th></tr></thead><tbody>{standings.data?.rows.map(row => <tr key={row.team_id}><td><span className={`rank rank-${row.position}`}>{row.position}</span></td><td className="team-name"><NavLink className="team-link" to={teamPath({ name: row.name })}>{row.name}</NavLink></td><td>{row.played}</td><td>{row.won}</td><td>{row.drawn}</td><td>{row.lost}</td><td>{row.goal_difference > 0 ? '+' : ''}{row.goal_difference}</td><td><strong>{row.points}</strong></td></tr>)}</tbody></table>}
    </section>
    <section className="card"><div className="card-head"><div><span className="eyebrow">Projection</span><h2>How the group may finish</h2></div><span className="meta">{latest ? `${latest.iterations.toLocaleString()} simulations` : isPublishedMode ? 'Awaiting published forecast' : 'Run a simulation to populate'}</span></div>
      {projection.data ? <div className="prob-grid">{[...projection.data.teams].sort((a, b) => b.win_group - a.win_group).map(team => {
        const name = teamById.get(team.team_id)?.name ?? `Team ${team.team_id}`
        return <div className="prob-row" key={team.team_id}><NavLink className="team-link" to={teamPath({ name })}>{name}</NavLink><Probability label="Win group" value={team.win_group} /><Probability label="Top two" value={team.top_two} /><Probability label="Advance third" value={team.advance_as_third} /><Probability label="Eliminated" value={team.eliminated} tone="danger" /></div>
      })}</div> : <Empty text={isPublishedMode ? 'Published forecast is not available yet.' : 'No completed simulation yet.'} />}
    </section>
  </>
}

function MatchesPage() {
  const navigate = useNavigate()
  const matches = useQuery<Match[]>({ queryKey: ['matches'], queryFn: () => api('/matches') })
  const matchIds = useMemo(() => matches.data?.map(match => match.id) ?? [], [matches.data])
  const predictions = useQuery<Record<string, MatchPrediction>>({
    queryKey: ['match-predictions', matchIds],
    queryFn: () => api<Record<string, MatchPrediction>>(`/matches/predictions?${matchIds.map(id => `match_ids=${id}`).join('&')}`),
    enabled: matchIds.length > 0,
  })
  const predictionByMatchId = useMemo(
    () => new Map(Object.entries(predictions.data ?? {}).map(([matchId, prediction]) => [Number(matchId), prediction])),
    [predictions.data],
  )

  return <>
    <PageHeader eyebrow="Fixture model" title="Match predictions" detail="Compare the independent Poisson model with devigged market consensus and the final calibrated blend." />
    <section className="card match-list">
      {matches.data?.map(match => {
        const prediction = predictionByMatchId.get(match.id)
        const hasResult = !!match.result
        return (
          <button key={match.id} type="button" className="match-list-card" onClick={() => navigate(`/matches/${match.id}`)}>
            <span className="match-no">M{match.official_match_number} · Group {match.group_code}</span>
            <div className="match-list-body">
              <div className="match-list-teams">
                <span className="match-team">
                  <span className="match-list-flag" aria-hidden>{flagEmoji(match.team_a.fifa_code)}</span>
                  {match.team_a.name}
                </span>
                <div className="match-list-center">
                  {hasResult ? (
                    <span className="match-score">{match.result!.team_a_goals}–{match.result!.team_b_goals}</span>
                  ) : (
                    <>
                      <span className="match-vs">vs</span>
                      <span className="match-date">{new Date(match.scheduled_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
                    </>
                  )}
                </div>
                <span className="match-team match-team-away">
                  <span className="match-list-flag" aria-hidden>{flagEmoji(match.team_b.fifa_code)}</span>
                  {match.team_b.name}
                </span>
              </div>
              <div className="match-outcomes">
                <span className="match-outcomes-label">Model</span>
                {prediction ? (
                  <div className="match-outcome-cols">
                    <span>
                      <strong>{percent(prediction.final.team_a)}</strong>
                      <small>{match.team_a.fifa_code}</small>
                    </span>
                    <span>
                      <strong>{percent(prediction.final.draw)}</strong>
                      <small>Draw</small>
                    </span>
                    <span>
                      <strong>{percent(prediction.final.team_b)}</strong>
                      <small>{match.team_b.fifa_code}</small>
                    </span>
                  </div>
                ) : (
                  <strong className="match-outcomes-empty">—</strong>
                )}
              </div>
            </div>
          </button>
        )
      })}
    </section>
  </>
}

function KnockoutMatchPage() {
  const { matchNumber } = useParams()
  const [searchParams] = useSearchParams()
  const teamAId = Number(searchParams.get('team_a_id'))
  const teamBId = Number(searchParams.get('team_b_id'))
  const teams = useQuery<Team[]>({ queryKey: ['teams'], queryFn: () => api('/teams') })
  const prediction = useQuery<MatchPrediction>({
    queryKey: ['knockout-prediction', matchNumber, teamAId, teamBId],
    queryFn: () => api(`/knockout/${matchNumber}/prediction?team_a_id=${teamAId}&team_b_id=${teamBId}`),
    enabled: Number.isFinite(teamAId) && Number.isFinite(teamBId) && teamAId > 0 && teamBId > 0,
  })
  const teamA = teams.data?.find(team => team.id === teamAId)
  const teamB = teams.data?.find(team => team.id === teamBId)
  const labels = [teamA?.name ?? 'Team A', 'Draw', teamB?.name ?? 'Team B']
  const tactical = prediction.data?.tactical_stats
  const matchup = prediction.data?.style_matchup
  if (!Number.isFinite(teamAId) || !Number.isFinite(teamBId)) {
    return <Empty text="Open this matchup from the bracket projection." />
  }
  return <><PageHeader eyebrow={`Knockout M${matchNumber ?? ''}`} title={`${labels[0]} vs ${labels[2]}`} detail="Style profiles use group-stage PMSR only. Advance probability includes extra time and penalties." actions={<NavLink className="button ghost" to="/bracket">Back to bracket</NavLink>} />
    <div className="two-col"><section className="card"><div className="card-head"><div><span className="eyebrow">Knockout model</span><h2>Outcome probabilities</h2></div><span className="quality">{prediction.data?.data_quality?.replace('_', ' ')}</span></div>
      <div className="outcome-grid">{prediction.data && Object.values(prediction.data.final).map((value, index) => <div key={labels[index]}><span>{labels[index]}</span><strong>{percent(value)}</strong><i style={{ width: percent(value) }} /></div>)}</div>
      {prediction.data?.advance_probability_a != null && <div className="advance-prob"><h3>Advance probability</h3><div><span>{labels[0]}</span><strong>{percent(prediction.data.advance_probability_a)}</strong></div><div><span>{labels[2]}</span><strong>{percent(1 - prediction.data.advance_probability_a)}</strong></div></div>}
    </section><section className="card"><div className="card-head"><div><span className="eyebrow">Score model</span><h2>Expected goals</h2></div></div><div className="xg"><div><span>{labels[0]}</span><strong>{prediction.data?.lambda_a.toFixed(2) ?? '—'}</strong></div><b>—</b><div><span>{labels[2]}</span><strong>{prediction.data?.lambda_b.toFixed(2) ?? '—'}</strong></div></div><ScoreMatrix matrix={prediction.data?.score_distribution} /></section></div>
    {tactical && matchup ? <TacticalFit teamA={labels[0]} teamB={labels[2]} tactical={tactical} matchup={matchup} /> : prediction.isSuccess && <section className="card"><p className="tactical-narrative">Tactical style data is not available yet for one or both teams (need prior group-stage PMSR reports).</p></section>}
  </>
}

function MatchPage() {
  const { id } = useParams()
  const match = useQuery<Match>({ queryKey: ['match', id], queryFn: () => api(`/matches/${id}`) })
  const prediction = useQuery<MatchPrediction>({ queryKey: ['prediction', id], queryFn: () => api(`/matches/${id}/prediction`) })
  const labels = [match.data?.team_a.name ?? 'Team A', 'Draw', match.data?.team_b.name ?? 'Team B']
  const tactical = prediction.data?.tactical_stats
  const matchup = prediction.data?.style_matchup
  return <><PageHeader eyebrow={`Match ${match.data?.official_match_number ?? ''}`} title={`${labels[0]} vs ${labels[2]}`} detail="Normal-time probabilities. Knockout advancement accounts for extra time and penalties separately." actions={<NavLink className="button ghost" to="/matches">All matches</NavLink>} />
    <div className="two-col"><section className="card"><div className="card-head"><div><span className="eyebrow">Final blend</span><h2>Outcome probabilities</h2></div><span className="quality">{prediction.data?.data_quality?.replace('_', ' ')}</span></div>
      <div className="outcome-grid">{prediction.data && Object.values(prediction.data.final).map((value, index) => <div key={labels[index]}><span>{labels[index]}</span><strong>{percent(value)}</strong><i style={{ width: percent(value) }} /></div>)}</div>
      <div className="model-compare"><h3>Market vs model</h3>{labels.map((label, index) => { const key = ['team_a', 'draw', 'team_b'][index]; return <div key={label}><span>{label}</span><small>Model {prediction.data ? percent(prediction.data.model[key]) : '—'}</small><small>Market {prediction.data?.market ? percent(prediction.data.market[key]) : 'No market'}</small></div> })}</div>
      {prediction.data?.advance_probability_a != null && <div className="advance-prob"><h3>Advance probability</h3><div><span>{labels[0]}</span><strong>{percent(prediction.data.advance_probability_a)}</strong></div><div><span>{labels[2]}</span><strong>{percent(1 - prediction.data.advance_probability_a)}</strong></div></div>}
    </section><section className="card"><div className="card-head"><div><span className="eyebrow">Score model</span><h2>Expected goals</h2></div></div><div className="xg"><div><span>{labels[0]}</span><strong>{prediction.data?.lambda_a.toFixed(2) ?? '—'}</strong></div><b>—</b><div><span>{labels[2]}</span><strong>{prediction.data?.lambda_b.toFixed(2) ?? '—'}</strong></div></div><ScoreMatrix matrix={prediction.data?.score_distribution} /></section></div>
    {tactical && matchup && <TacticalFit teamA={labels[0]} teamB={labels[2]} tactical={tactical} matchup={matchup} />}
  </>
}

function TacticalFit({ teamA, teamB, tactical, matchup }: { teamA: string; teamB: string; tactical: TacticalStats; matchup: StyleMatchup }) {
  const favorLabel = matchup.favor === 'team_a' ? teamA : matchup.favor === 'team_b' ? teamB : 'Even'
  const maxContrib = Math.max(...matchup.interaction_scores.map(item => Math.abs(item.contribution)), 0.01)
  const interactionLabel = (label: string) => label.replaceAll('Team A', teamA).replaceAll('Team B', teamB)
  const narrative = interactionLabel(matchup.narrative)
  return <section className="card tactical-fit"><div className="card-head"><div><span className="eyebrow">Tactical fit</span><h2>Style matchup</h2></div><span className={`tactical-favor favor-${matchup.favor}`}>{favorLabel}</span></div>
    <p className="tactical-narrative">{narrative}</p>
    <div className="tactical-stats-grid">
      <div><span>{teamA}</span><small>Poss {tactical.possession_a.toFixed(0)}%</small><small>Shots {tactical.shots_a.toFixed(1)}</small><small>SOT {tactical.sot_a.toFixed(1)}</small><strong>xG {tactical.xg_a.toFixed(2)}</strong></div>
      <div><span>{teamB}</span><small>Poss {tactical.possession_b.toFixed(0)}%</small><small>Shots {tactical.shots_b.toFixed(1)}</small><small>SOT {tactical.sot_b.toFixed(1)}</small><strong>xG {tactical.xg_b.toFixed(2)}</strong></div>
    </div>
    <div className="interaction-bars"><h3>Interaction effects</h3>{matchup.interaction_scores.slice(0, 6).map(item => <div key={item.key} className="interaction-row"><span>{interactionLabel(item.label)}</span><div className="interaction-bar"><i style={{ width: `${Math.abs(item.contribution) / maxContrib * 100}%`, background: item.contribution >= 0 ? '#c7ff55' : '#ff6b6b' }} /></div><small>{item.contribution >= 0 ? '+' : ''}{item.contribution.toFixed(2)} xG</small></div>)}</div>
  </section>
}

function SimulatorPage() {
  const client = useQueryClient()
  const runs = useRuns()
  const [iterations, setIterations] = useState(10000)
  const [seed, setSeed] = useState(2026)
  const [trackedRunId, setTrackedRunId] = useState<string | null>(null)
  const [runNotice, setRunNotice] = useState<string | null>(null)
  const mutation = useMutation({
    mutationFn: () => api<Run>('/simulations', { method: 'POST', body: JSON.stringify({ iterations, seed }) }),
    onSuccess: (run) => {
      setRunNotice(run.status === 'completed' ? 'Reused the latest cached run for this tournament state.' : 'Simulation started.')
      setTrackedRunId(run.id)
      client.invalidateQueries({ queryKey: ['runs'] })
    },
    onError: (error) => setRunNotice(error instanceof Error ? error.message : 'Simulation failed to start.'),
  })
  const cancelMutation = useMutation({
    mutationFn: (runId: string) => api<Run>(`/simulations/${runId}/cancel`, { method: 'POST' }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['runs'] }),
  })
  const active = useMemo(() => {
    const list = runs.data ?? []
    if (trackedRunId) {
      const tracked = list.find(run => run.id === trackedRunId)
      if (tracked && (tracked.status === 'queued' || tracked.status === 'running')) return tracked
    }
    return list.find(run => run.status === 'running' || run.status === 'queued')
  }, [runs.data, trackedRunId])
  const latestCompleted = runs.data?.find(run => run.status === 'completed')
  const displayRun = active ?? latestCompleted
  const teams = useQuery<TeamForecast[]>({
    queryKey: ['simulation-teams', latestCompleted?.id],
    queryFn: () => api(`/simulations/${latestCompleted!.id}/teams`),
    enabled: latestCompleted?.status === 'completed',
  })
  useEffect(() => {
    if (!trackedRunId || !runs.data) return
    const run = runs.data.find(item => item.id === trackedRunId)
    if (!run || run.status === 'queued' || run.status === 'running') return
    client.invalidateQueries({ queryKey: ['simulation-teams'] })
    client.invalidateQueries({ queryKey: ['projection'] })
    client.invalidateQueries({ queryKey: ['bracket'] })
  }, [runs.data, trackedRunId, client])
  return <><PageHeader eyebrow="Monte Carlo lab" title="Tournament simulator" detail="Run a reproducible tournament distribution. Completed matches are locked and future scores remain probabilistic." actions={<button className="button primary" disabled={!!active || mutation.isPending} onClick={() => { setRunNotice(null); mutation.mutate() }}>{mutation.isPending ? 'Starting…' : 'Run simulation'}</button>} />
    {runNotice && <div className={`warning${mutation.isError ? '' : ''}`}>{runNotice}</div>}
    <section className="card controls"><label>Simulation depth<select value={iterations} onChange={event => setIterations(Number(event.target.value))} disabled={!!active}><option value={10000}>10,000 · Fast</option><option value={100000}>100,000 · Precise</option><option value={1000000}>1,000,000 · Research</option></select></label><label>Random seed<input type="number" value={seed} onChange={event => setSeed(Number(event.target.value))} disabled={!!active} /></label>
      {active ? <SimulationProgress run={active} onCancel={() => cancelMutation.mutate(active.id)} cancelling={cancelMutation.isPending} variant="compact" /> : <div className="run-state idle"><span>Status</span><strong>{displayRun ? 'Ready for next run' : 'No runs yet'}</strong>{displayRun && <small>Last run: {displayRun.iterations.toLocaleString()} trials · seed {displayRun.seed}</small>}</div>}
    </section>
    {active && <SimulationProgress run={active} onCancel={() => cancelMutation.mutate(active.id)} cancelling={cancelMutation.isPending} />}
    <section className="card"><div className="card-head"><div><span className="eyebrow">Stage reach</span><h2>Who goes deepest</h2></div>{latestCompleted && !active && <span className="meta">Seed {latestCompleted.seed} · {latestCompleted.model_version}{latestCompleted.duration_ms ? ` · ${formatDuration(latestCompleted.duration_ms)}` : ''}</span>}</div>{teams.data && !active ? <><div className="chart"><ResponsiveContainer width="100%" height={280}><BarChart data={[...teams.data].sort((a,b) => b.champion-a.champion).slice(0,12)} layout="vertical"><CartesianGrid strokeDasharray="3 3" horizontal={false} /><XAxis type="number" tickFormatter={value => percent(value)} /><YAxis dataKey="fifa_code" type="category" width={42} /><Tooltip formatter={(value) => percent(Number(value))} /><Bar dataKey="champion" fill="#c7ff55" radius={[0,6,6,0]} /></BarChart></ResponsiveContainer></div><StageTable teams={teams.data} /></> : <Empty text={active ? 'Results will appear when the run finishes.' : 'Run the simulator to calculate stage probabilities.'} />}</section>
  </>
}

function BracketPage() {
  const { data: latest } = useLatestSimulation()
  const teams = useQuery<Team[]>({ queryKey: ['teams'], queryFn: () => api('/teams') })
  const groups = useQuery<Group[]>({ queryKey: ['groups'], queryFn: () => api('/groups') })
  const bracket = useQuery<BracketRow[]>({
    queryKey: ['bracket', latest?.id],
    queryFn: () => api(`/simulations/${latest!.id}/bracket`),
    enabled: !!latest,
  })
  const simulationGroups = useQuery<SimulationGroupOutcome[]>({
    queryKey: ['sim-groups', latest?.id],
    queryFn: () => api(`/simulations/${latest!.id}/groups`),
    enabled: !!latest,
  })
  const teamExpectations = useQuery<TeamForecast[]>({
    queryKey: ['sim-teams', latest?.id],
    queryFn: () => api(`/simulations/${latest!.id}/teams`),
    enabled: !!latest,
  })
  return <>
    <PageHeader
      eyebrow="Path distribution"
      title="Projected bracket"
      detail="Knockout tree built from the most likely group-stage outcome in each group, official slot rules, and conditional advance rates from your latest simulation."
    />
    {!latest && <Empty text={isPublishedMode ? 'Published forecast is not available yet.' : 'Complete a simulation to build matchup probabilities.'} />}
    {latest && teams.data && bracket.data && groups.data && simulationGroups.data && teamExpectations.data && (
      <BracketBoard
        rows={bracket.data}
        teams={teams.data}
        iterations={latest.iterations}
        simulationId={latest.id}
        resultCoverage={latest.result_coverage}
        groups={groups.data}
        simulationGroups={simulationGroups.data}
        teamExpectations={teamExpectations.data}
      />
    )}
    {latest && (!teams.data || !bracket.data || !groups.data || !simulationGroups.data || !teamExpectations.data) && <Loading />}
  </>
}

function TeamsPage() {
  const navigate = useNavigate()
  const teams = useQuery<Team[]>({ queryKey: ['teams'], queryFn: () => api('/teams') })
  return (
    <>
      <PageHeader eyebrow="Team intelligence" title="All 48 teams" detail="Open a team to inspect fixtures, advancement probability, and its likely route through the bracket." />
      <section className="team-grid">
        {teams.data?.map(team => (
          <button className="card" onClick={() => navigate(teamPath(team))} key={team.id}>
            <span>{team.fifa_code}</span>
            <strong>{team.name}</strong>
            <small>View team forecast →</small>
          </button>
        ))}
      </section>
    </>
  )
}

function TeamPage() {
  const { slug } = useParams()
  const { data: latest } = useLatestSimulation()
  if (!slug) return null
  return <TeamPageView slug={slug} latestSimulationId={latest?.id} simulationIterations={latest?.iterations} />
}

function AdminPage() {
  const client = useQueryClient(); const matches = useQuery<Match[]>({ queryKey: ['matches'], queryFn: () => api('/matches') })
  const [matchId, setMatchId] = useState(''); const [a, setA] = useState(0); const [b, setB] = useState(0); const [file, setFile] = useState<File>(); const [dataset, setDataset] = useState('results'); const [preview, setPreview] = useState<ImportPreview>()
  const [marketSyncMatch, setMarketSyncMatch] = useState(''); const [marketSyncReport, setMarketSyncReport] = useState<MarketSyncReport>()
  const [reportMatchId, setReportMatchId] = useState(''); const [reportData, setReportData] = useState<MatchReportData>()
  const resultMutation = useMutation({ mutationFn: () => api(`/admin/matches/${matchId}/result`, { method:'PUT', body:JSON.stringify({ team_a_goals_90:a, team_b_goals_90:b, team_a_yellows:0, team_b_yellows:0, team_a_indirect_reds:0, team_b_indirect_reds:0, team_a_direct_reds:0, team_b_direct_reds:0, team_a_yellow_direct_reds:0, team_b_yellow_direct_reds:0 }) }), onSuccess: () => client.invalidateQueries() })
  const marketSyncMutation = useMutation({
    mutationFn: () => {
      const query = marketSyncMatch ? `?match_number=${encodeURIComponent(marketSyncMatch)}` : ''
      return api<MarketSyncReport>(`/admin/markets/sync${query}`, { method: 'POST' })
    },
    onSuccess: (report) => { setMarketSyncReport(report); client.invalidateQueries() },
  })
  const reportMutation = useMutation({
    mutationFn: () => api<MatchReportData>(`/admin/matches/${reportMatchId}/report-data?limit=200`),
    onSuccess: setReportData,
  })
  async function upload() { if (!file) return; const form = new FormData(); form.append('file', file); form.append('source','manual-csv'); setPreview(await api<ImportPreview>(`/admin/imports/${dataset}/preview`, { method:'POST', body:form })) }
  async function commit() { if (!preview) return; await api(`/admin/imports/${preview.id}/commit`, { method:'POST' }); setPreview(undefined); client.invalidateQueries() }
  const fixtureRows = marketSyncReport?.fixtures.reduce((sum, row) => sum + row.stored_rows, 0) ?? 0
  const syncWarnings = [
    ...(marketSyncReport?.fixtures.flatMap(row => row.warnings) ?? []),
    ...(marketSyncReport?.wc_winner.warnings ?? []),
  ]
  return <><PageHeader eyebrow="Data operations" title="Admin workspace" detail="Validate imports before committing them. Result corrections create a new immutable revision." />
    <div className="two-col"><section className="card form-card"><span className="eyebrow">Manual result</span><h2>Record a final score</h2><label>Fixture<select value={matchId} onChange={e=>setMatchId(e.target.value)}><option value="">Select match</option>{matches.data?.map(match=><option value={match.id} key={match.id}>M{match.official_match_number} · {match.team_a.name} vs {match.team_b.name}</option>)}</select></label><div className="score-input"><input type="number" min="0" value={a} onChange={e=>setA(Number(e.target.value))}/><span>—</span><input type="number" min="0" value={b} onChange={e=>setB(Number(e.target.value))}/></div><button className="button primary" disabled={!matchId || resultMutation.isPending} onClick={()=>resultMutation.mutate()}>Save revision</button></section>
      <section className="card form-card"><span className="eyebrow">CSV ingestion</span><h2>Preview an import</h2><label>Dataset<select value={dataset} onChange={e=>setDataset(e.target.value)}>{['teams','fixtures','results','ratings','bookmaker_odds','prediction_markets'].map(value=><option key={value}>{value}</option>)}</select></label><label className="file-input"><input type="file" accept=".csv" onChange={e=>setFile(e.target.files?.[0])}/><span>{file?.name ?? 'Choose CSV file'}</span></label><button className="button ghost" disabled={!file} onClick={upload}>Validate file</button>{preview && <div className="preview"><strong>{preview.record_count} rows · {preview.status}</strong>{preview.errors.map(error=><small key={error.row}>{error.message}</small>)}{preview.status==='validated'&&<button className="button primary" onClick={commit}>Commit import</button>}</div>}</section>
      <section className="card form-card"><span className="eyebrow">Prediction markets</span><h2>Sync Polymarket &amp; Kalshi</h2><p><small>Fetch 1X2 quotes for upcoming group fixtures and WC winner prices via Attena/Kalshi.</small></p><label>Fixture <small>(optional)</small><select value={marketSyncMatch} onChange={e=>setMarketSyncMatch(e.target.value)}><option value="">All upcoming group matches</option>{matches.data?.filter(match => match.status !== 'final').map(match=><option value={match.official_match_number} key={match.id}>M{match.official_match_number} · {match.team_a.name} vs {match.team_b.name}</option>)}</select></label><button className="button primary" disabled={marketSyncMutation.isPending} onClick={()=>marketSyncMutation.mutate()}>{marketSyncMutation.isPending ? 'Syncing…' : 'Sync markets'}</button>{marketSyncMutation.isError && <div className="warning">{marketSyncMutation.error.message}</div>}{marketSyncReport && <div className="preview"><strong>{fixtureRows} fixture rows · {marketSyncReport.wc_winner.stored_rows} WC winner rows</strong><small>{marketSyncReport.fixtures.length} fixtures · {marketSyncReport.wc_winner.teams_matched} teams matched</small>{marketSyncReport.wc_winner.top_favorites.length > 0 && <small>Top: {marketSyncReport.wc_winner.top_favorites.map(team => `${team.fifa_code} ${percent(team.probability, 1)}`).join(' · ')}</small>}{syncWarnings.map(warning => <small key={warning}>{warning}</small>)}</div>}</section>
      <section className="card form-card"><span className="eyebrow">Match reports</span><h2>Inspect extracted data</h2><label>Fixture<select value={reportMatchId} onChange={e=>{ setReportMatchId(e.target.value); setReportData(undefined) }}><option value="">Select match</option>{matches.data?.map(match=><option value={match.id} key={match.id}>M{match.official_match_number} · {match.team_a.name} vs {match.team_b.name}</option>)}</select></label><button className="button primary" disabled={!reportMatchId || reportMutation.isPending} onClick={()=>reportMutation.mutate()}>{reportMutation.isPending ? 'Loading…' : 'Load report data'}</button>{reportMutation.isError && <div className="warning">{reportMutation.error.message}</div>}{reportData && <div className="preview report-preview"><strong>{reportData.document.filename} · {reportData.run.status}</strong><div className="report-stats"><span>{reportData.document.page_count} pages</span><span>{reportData.participants.length} participants</span><span>{reportData.observations.length} observations</span><span>{reportData.events.length} events</span><span>{reportData.spatial_features.length} spatial</span><span>{reportData.network_edges.length} edges</span><span>{reportData.timeseries_points.length} time points</span><span>{reportData.issues.length} issues</span></div><pre>{JSON.stringify(reportData, null, 2)}</pre></div>}</section></div>
  </>
}

function Probability({ label, value, tone }: { label: string; value: number; tone?: string }) { return <div className={`prob ${tone??''}`}><span>{label}<b>{percent(value)}</b></span><i><em style={{ width: percent(value) }} /></i></div> }
function Freshness({ provisional }: { provisional?: boolean }) { const pendingOrProvisional = provisional !== false; return <div className={`freshness ${pendingOrProvisional?'provisional':''}`}><span />{pendingOrProvisional?'Provisional data':'Data complete'}</div> }
function Loading() { return <div className="empty">Loading tournament state…</div> }
function Empty({ text }: { text: string }) { return <div className="empty">{text}</div> }

function SidebarPublishedStatus() {
  const { data: latest, isLoading } = useLatestSimulation()
  if (isLoading || !latest) return null
  return <div className="sidebar-published">
    <span className="eyebrow">Knockout forecast</span>
    <strong>{latest.iterations.toLocaleString()} trials</strong>
    <small>Seed {latest.seed} · cutoff {new Date(latest.input_cutoff_at).toLocaleDateString()}</small>
  </div>
}

function SidebarSimulationStatus() {
  const runs = useRuns()
  const active = runs.data?.find(run => run.status === 'running' || run.status === 'queued')
  if (!active) return null
  return <div className="sidebar-sim"><NavLink to="/simulator"><SimulationProgress run={active} variant="sidebar" /></NavLink></div>
}

function SimulationProgress({ run, onCancel, cancelling, variant = 'full' }: {
  run: Run
  onCancel?: () => void
  cancelling?: boolean
  variant?: 'full' | 'compact' | 'sidebar'
}) {
  const pct = simulationPercent(run)
  const statusLabel = run.status === 'queued' ? 'Queued' : run.status === 'running' ? 'Running' : run.status
  const trialsLabel = `${run.progress_iterations.toLocaleString()} / ${run.iterations.toLocaleString()} trials`
  if (variant === 'sidebar') {
    return <div className="sim-progress sidebar"><div className="sim-progress-head"><span className={`sim-status ${run.status}`}>{statusLabel}</span><strong>{pct}%</strong></div><div className="sim-progress-track"><i style={{ width: `${pct}%` }} /></div><small>{trialsLabel}</small></div>
  }
  if (variant === 'compact') {
    return <div className="sim-progress compact"><div className="sim-progress-head"><span className={`sim-status ${run.status}`}>{statusLabel}</span><strong>{trialsLabel}</strong></div><div className="sim-progress-track"><i style={{ width: `${pct}%` }} /></div></div>
  }
  return <section className="card sim-progress-card"><div className="sim-progress-head"><div><span className="eyebrow">Simulation progress</span><h2>{statusLabel}</h2></div><div className="sim-progress-actions">{onCancel && (run.status === 'running' || run.status === 'queued') && <button className="button ghost" disabled={cancelling} onClick={onCancel}>{cancelling ? 'Cancelling…' : 'Cancel run'}</button>}<strong className="sim-percent">{pct}%</strong></div></div><div className="sim-progress-track large"><i style={{ width: `${pct}%` }} /></div><div className="sim-progress-meta"><span>{trialsLabel}</span>{run.status === 'queued' && <span>Waiting for worker…</span>}{run.status === 'running' && <span>Updating every 0.5s</span>}</div>{run.error_message && <div className="warning">{run.error_message}</div>}</section>
}

function simulationPercent(run: Run) {
  if (!run.iterations) return 0
  return Math.min(100, Math.round((run.progress_iterations / run.iterations) * 1000) / 10)
}

function formatDuration(ms: number) {
  if (!Number.isFinite(ms) || ms < 0) return '—'
  const seconds = Math.ceil(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const rem = seconds % 60
  return rem ? `${minutes}m ${rem}s` : `${minutes}m`
}

function ScoreMatrix({ matrix }: { matrix?: number[][] }) { const cells = useMemo(()=>{ if(!matrix) return []; const output=[]; for(let a=0;a<5;a++) for(let b=0;b<5;b++) output.push({a,b,p:matrix[a][b]}); return output },[matrix]); return <div className="score-matrix">{cells.map(cell=><div key={`${cell.a}-${cell.b}`} style={{background:`rgba(199,255,85,${Math.min(.85,cell.p*5)})`}}><small>{cell.a}–{cell.b}</small><strong>{percent(cell.p)}</strong></div>)}</div> }
function StageTable({ teams }: { teams: TeamForecast[] }) { return <div className="table-scroll"><table><thead><tr><th>Team</th><th>R32</th><th>R16</th><th>QF</th><th>SF</th><th>Final</th><th>Champion</th></tr></thead><tbody>{[...teams].sort((a,b)=>b.champion-a.champion).map(team=><tr key={team.team_id}><td className="team-name"><b>{team.fifa_code}</b> {team.name}</td>{['round_of_32','round_of_16','quarterfinal','semifinal','final','champion'].map(key=><td key={key}>{percent(team[key as keyof TeamForecast] as number)}</td>)}</tr>)}</tbody></table></div> }

export default App
