function Formula({ children }: { children: React.ReactNode }) {
  return <pre className="method-formula">{children}</pre>
}

function Section({ eyebrow, title, children }: { eyebrow: string; title: string; children: React.ReactNode }) {
  return (
    <section className="card method-section">
      <div className="card-head"><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2></div></div>
      {children}
    </section>
  )
}

export function MethodologyPage() {
  return (
    <>
      <header className="page-header">
        <div>
          <span className="eyebrow">Model documentation</span>
          <h1>Methodology</h1>
          <p>
            How match probabilities and tournament forecasts are built. Every quantity below is implemented in the
            backend and applied consistently across the Matches tab, Monte Carlo simulation, and published bracket.
          </p>
        </div>
      </header>

      <Section eyebrow="Pipeline" title="End-to-end flow">
        <ol className="method-steps">
          <li>Fuse team strength from Elo, FIFA rank, and optional WC-winner market prices.</li>
          <li>Convert strength gap plus context (host, rest, travel) into expected goals λ<sub>A</sub>, λ<sub>B</sub>.</li>
          <li>Build a scoreline probability matrix (Poisson or negative-binomial).</li>
          <li>Sum matrix cells into 1X2 model probabilities; devig and log-pool blend with market odds when available.</li>
          <li>Run N Monte Carlo trials: lock official results, sample remaining scores, apply FIFA tiebreak rules, advance knockout rounds.</li>
        </ol>
      </Section>

      <Section eyebrow="Strength" title="Team strength">
        <p>FIFA rank r (1 = best) maps to an Elo-scale prior:</p>
        <Formula>{`E_FIFA(r) = 2200 − 15·r`}</Formula>
        <p>Live tournament Elo E is blended with the FIFA prior and, when available, a WC-champion market-implied Elo E<sub>mkt</sub>:</p>
        <Formula>{`S = (1 − w_f)·E + w_f·E_FIFA(r)                    (default w_f = 0.12)
S* = (1 − w_c)·S + w_c·E_mkt(p_champion)         (default w_c = 0.15 when market exists)`}</Formula>
        <p className="method-note">Elo ratings update after each official result during simulation. Champion-market fusion uses devigged Kalshi / Polymarket WC-winner prices.</p>
      </Section>

      <Section eyebrow="Match model" title="Expected goals">
        <p>Given fused strengths S<sub>A</sub>, S<sub>B</sub>, define the log-strength gap Δ:</p>
        <Formula>{`Δ = 1.15·(S_A − S_B) / 400
    + 0.08·𝟙[host A] − 0.08·𝟙[host B]
    + β_rest · (rest_curve(days_A) − rest_curve(days_B))
    + β_travel · (travel_curve(km_B) − travel_curve(km_A))

rest_curve(d) = min(d, 4) / 4
travel_curve(k) = min(k, 3500) / 3500          (defaults: β_rest = 0.06, β_travel = 0.05)`}</Formula>
        <p>Expected goals use a shared baseline μ₀ ≈ 1.32 goals per team:</p>
        <Formula>{`λ_A = clip( exp(ln μ₀ + Δ/2), 0.15, 4.5 )
λ_B = clip( exp(ln μ₀ − Δ/2), 0.15, 4.5 )`}</Formula>
      </Section>

      <Section eyebrow="Scorelines" title="Score distribution & 1X2">
        <p>When goal over-dispersion φ &gt; 0 (default φ = 0.15), each team&apos;s goal count follows a negative-binomial marginal with mean λ and variance λ + φ·λ². At φ = 0 the model reduces to independent Poissons. Marginals are truncated at 10 goals with tail mass folded into the last cell.</p>
        <Formula>{`P(A = i, B = j) ∝ NB(i | λ_A, φ) · NB(j | λ_B, φ)     (normalized over i,j ≤ 10)

P(A wins) = Σ_{i>j} P(i,j)
P(draw)   = Σ_i P(i,i)
P(B wins) = Σ_{i<j} P(i,j)`}</Formula>
        <p>These three sums are the <strong>model</strong> probabilities shown on the Matches tab.</p>
      </Section>

      <Section eyebrow="Markets" title="Market devigging & calibration">
        <p>Bookmaker decimal odds o<sub>k</sub> are devigged by normalizing implied probabilities:</p>
        <Formula>{`p_k = (1/o_k) / Σ_j (1/o_j)`}</Formula>
        <p>When external market data exists (bookmakers + prediction markets), model and market vectors are combined in log-probability space (a weighted geometric mean, then renormalized):</p>
        <Formula>{`log q_k = (α·log p_mkt,k + (1−α)·log p_mod,k) / (α + (1−α))
p_final,k = q_k / Σ_j q_j                         (default α = 0.85 toward market)`}</Formula>
        <p>The score matrix is reweighted so its 1X2 margins match p<sub>final</sub> while preserving relative scoreline shape within each outcome class (win / draw / loss).</p>
      </Section>

      <Section eyebrow="Simulation" title="Monte Carlo tournament">
        <p>Each trial:</p>
        <ul className="method-list">
          <li>Starts from the current official table (completed group and knockout results are locked).</li>
          <li>Draws every remaining group score from the calibrated score matrix for that fixture.</li>
          <li>Resolves group standings with FIFA May 2026 head-to-head tiebreak rules.</li>
          <li>Assigns Round-of-32 slots via the official Annex C third-place matrix.</li>
          <li>Plays out knockouts: sample 90-minute score; on a draw, sample extra time (0.3·λ Poisson per team), then penalties if still tied.</li>
          <li>Updates Elo after each sampled result.</li>
        </ul>
        <Formula>{`P̂(event) = (count of trials where event occurs) / N`}</Formula>
        <p className="method-note">Bracket, group projections, and team forecasts report these empirical frequencies. The published site pins one completed run (iterations N, seed, input cutoff).</p>
      </Section>

      <Section eyebrow="Scenario tab" title="What-if bracket (browser only)">
        <p>
          The Scenario section is separate from the Monte Carlo forecast. You enter hypothetical final scores for
          remaining group fixtures; standings and the Round-of-32 bracket are computed deterministically using the same
          FIFA tiebreak and Annex C rules—no random sampling. Inputs are saved in your browser&apos;s local storage only
          and never sent to the server.
        </p>
      </Section>
    </>
  )
}
