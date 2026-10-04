import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { labApi } from '../api/lab';
import type { CurveSet, LabActivity, LabExperiment, LabState, ScoringRow } from '../api/lab-types';
import { HypothesisSymbol, ScientificText } from '../components/ScientificText';
import { sounds } from '../hooks/useSound';
import { useLab } from './LabContext';

/* Benchmark claims supplied by the team brief — not served by the lab feed. */
const COMPUTE_SAVING = 35.15;
const LANG_CHAIN = ['Python', 'Rust', 'Julia'];

const f = (n: number | null | undefined, d = 3) => (n == null || Number.isNaN(n) ? '—' : Number(n.toFixed(d)).toString());

export const SAMPLE_STORY: { state: LabState; activity: LabActivity[]; experiment: LabExperiment } = (() => {
  const rows: ScoringRow[] = [
    { id: 'E1', title: 'Entropy features predict stagnation on static landscapes', kind: 'detection', stage: 'exploratory', eig_bits: 0.412, utility: 0.871, feasible: true, violations: [], est_wall_seconds: 140, hypotheses: ['H1', 'H2'] },
    { id: 'E2', title: 'Dispersion features on shifting landscapes', kind: 'detection', stage: 'exploratory', eig_bits: 0.268, utility: 0.604, feasible: true, violations: [], est_wall_seconds: 210, hypotheses: ['H3'] },
  ];
  const shifts = Array.from({ length: 40 }, (_, i) => i * 5);
  const curve = (a: number, b: number) => shifts.map((s) => a * Math.exp(-s / 60) + b + Math.sin(s / 9) * 0.04);
  return {
    state: {
      question: 'Does falling population entropy predict stagnation in genetic algorithms earlier than fitness plateaus do?',
      compute_seconds: { used: 140, budget: 900 },
      hypotheses: [
        { id: 'H1', family: 'detection', origin: 'literature', statement: 'Population entropy drop precedes fitness plateau by ≥ 10 generations', status: 'supported', posterior: 0.78, n_direct_tests: 1, last: null },
        { id: 'H2', family: 'detection', origin: 'designer', statement: 'Entropy AUROC exceeds dispersion AUROC by ΔAUROC ≥ 0.01', status: 'open', posterior: 0.56, n_direct_tests: 1, last: null },
      ],
      evidence: [], candidates: [], selected: 'E1',
      latest_scoring_round: { round: 1, argmax: 'E1' },
      next_decision: null, events: 0,
      prereg_sha256: '9f3c1a7be04d2c58e61f0a93b7d42e8c15a6f09d3b2e7c4a8f1d6e0b9c3a5f72',
      trajectories: {
        H1: [{ seq: 1, posterior: 0.5, label: 'prior' }, { seq: 9, posterior: 0.78, label: 'E1', verdict: 'supported', experiment: 'E1' }],
        H2: [{ seq: 1, posterior: 0.5, label: 'prior' }, { seq: 9, posterior: 0.56, label: 'E1', verdict: 'open', experiment: 'E1' }],
      },
      rounds: [{ round: 1, seq: 4, argmax: 'E1', selected: 'E1', followed_argmax: true, justification: 'E1 has the highest expected information gain per compute second and tests two hypotheses at once.', rows }],
      decisions: [
        { seq: 2, by: 'pi', decision: 'Explore detection features broadly', rationale: 'No result yet.', next_experiment: 'E1' },
        { seq: 10, by: 'pi', decision: 'Confirm H1 on held-out shifting landscapes', rationale: 'E1 supported H1 with a 95% interval excluding zero.', next_experiment: 'E4' },
      ],
      analyses: {}, completed: ['E1'],
    },
    activity: [
      { t: 1, kind: 'handoff', from: 'pi', to: 'designer', title: 'Propose experiments', state: 'finished' },
      { t: 2, kind: 'tool', agent: 'designer', name: 'score_candidates', args: 'round=1' },
      { t: 3, kind: 'handoff', from: 'designer', to: 'pi', title: 'Ranking ready', state: 'finished' },
      { t: 4, kind: 'tool', agent: 'pi', name: 'run_experiment', args: 'id=E1 seeds=30' },
      { t: 5, kind: 'handoff', from: 'pi', to: 'critic', title: 'Interpret E1', state: 'finished' },
    ],
    experiment: {
      id: 'E1',
      verdicts: { H1: { verdict: 'supported', measure: 'AUROC_{entropy} − AUROC_{fitness}', effect: { estimate: 0.084, ci95: [0.031, 0.137] }, standardised_effect: 0.62, n_units: 30 } },
      curves: { static: { shifts, controllers: { adaptive: { n_runs: 30, log10_best_err_mean: curve(2, -1), entropy_mean: curve(1.4, 0.3), p_mut_mean: [] } } } },
    },
  };
})();

function Step({ n, title, children, tone }: { n: number; title: string; children: ReactNode; tone?: string }) {
  const ref = useRef<HTMLElement>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => { if (e?.isIntersecting) { setSeen(true); io.disconnect(); } }, { threshold: 0.2 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return (
    <section ref={ref} className={`story-step ${seen ? 'is-seen' : ''} ${tone ?? ''}`}>
      <span className="story-node" aria-hidden="true">{n}</span>
      <div className="story-card">
        <p className="eyebrow">{String(n).padStart(2, '0')} · {title}</p>
        {children}
      </div>
    </section>
  );
}

function DrawnChart({ curves, play }: { curves: CurveSet; play: boolean }) {
  const ctrl = Object.values(curves.controllers)[0];
  if (!ctrl) return null;
  const W = 520, H = 160;
  const path = (ys: number[]) => {
    if (!ys.length) return '';
    const lo = Math.min(...ys), hi = Math.max(...ys) || 1;
    return ys.map((y, i) => `${i ? 'L' : 'M'}${((i / Math.max(1, ys.length - 1)) * W).toFixed(1)},${(H - 8 - ((y - lo) / (hi - lo || 1)) * (H - 16)).toFixed(1)}`).join(' ');
  };
  return (
    <svg className={`story-chart ${play ? 'is-drawing' : ''}`} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Error and entropy curves">
      <path d={path(ctrl.log10_best_err_mean)} pathLength={1} className="line-err" />
      <path d={path(ctrl.entropy_mean)} pathLength={1} className="line-ent" />
    </svg>
  );
}

export function DiscoveryStory({ state, activity, kind, sampleExperiment }: { state: LabState; activity: LabActivity[]; kind: 'live' | 'record' | 'sample'; sampleExperiment?: LabExperiment }) {
  const lab = useLab();
  const round = state.rounds[state.rounds.length - 1];
  const top = [...(round?.rows ?? [])].sort((a, b) => b.utility - a.utility).slice(0, 2);
  const chosenId = round?.selected ?? state.selected;
  const resultId = state.completed[state.completed.length - 1] ?? null;
  const [exp, setExp] = useState<LabExperiment | null>(sampleExperiment ?? null);
  const [play, setPlay] = useState(false);
  const [skipped, setSkipped] = useState<string | null>(null);
  const [lines, setLines] = useState(0);
  const termRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (sampleExperiment || !resultId || !lab.sourceId) return;
    let off = false;
    const ids = [...state.completed].reverse();
    const src = lab.sourceId;
    (async () => {
      for (const id of ids) {
        try {
          const e = await labApi.experiment(lab.baseUrl, src, id);
          if (off) return;
          setExp(e);
          setSkipped(id === resultId ? null : resultId);
          return;
        } catch { /* feed could not summarise this experiment; try the previous one */ }
      }
      if (!off) setSkipped(resultId);
    })();
    return () => { off = true; };
  }, [sampleExperiment, resultId, lab.baseUrl, lab.sourceId, state.completed]);

  const log = useMemo(() => activity.filter((a) => a.kind === 'tool' || a.kind === 'handoff').slice(-10), [activity]);

  useEffect(() => {
    const el = termRef.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => {
      if (!e?.isIntersecting) return;
      io.disconnect();
      sounds.hum();
      let i = 0;
      const id = window.setInterval(() => {
        i += 1;
        setLines(i);
        if (log[i - 1]?.kind === 'handoff') sounds.tick();
        if (i >= log.length) { window.clearInterval(id); setPlay(true); window.setTimeout(sounds.chime, 1400); }
      }, 260);
    }, { threshold: 0.4 });
    io.observe(el);
    return () => io.disconnect();
  }, [log]);

  const verdict = exp?.verdicts ? Object.entries(exp.verdicts)[0] : undefined;
  const curves = exp?.curves ? Object.values(exp.curves)[0] : undefined;
  const maxU = Math.max(0.0001, ...top.map((r) => r.utility));
  const firstDecision = state.decisions[0];
  const lastDecision = state.decisions[state.decisions.length - 1];
  const label = kind === 'live' ? 'LIVE' : kind === 'record' ? 'RECORDED' : 'SAMPLE';

  return (
    <div className="discovery-story" aria-label="Discovery story">
      <div className="story-glow" aria-hidden="true" />
      <Step n={1} title="Research question">
        <h2 className="story-question">{state.question}</h2>
      </Step>

      <Step n={2} title="Competing experiments">
        {top.length ? (
          <div className="story-pair">
            {top.map((r) => (
              <article key={r.id} className={`story-exp ${r.id === chosenId ? 'is-chosen' : ''}`}>
                <span className="mono">{r.id}</span>
                <strong>{r.title}</strong>
                <span className="quiet">Tests {r.hypotheses.map((h) => <HypothesisSymbol key={h} id={h} />).reduce<ReactNode[]>((acc, x, i) => (i ? [...acc, ', ', x] : [x]), [])} · ~{Math.round(r.est_wall_seconds)} s</span>
              </article>
            ))}
          </div>
        ) : <p className="quiet">No scoring round recorded yet.</p>}
      </Step>

      <Step n={3} title="Deterministic value-of-information ranking">
        <div className="story-rank">
          {top.map((r) => (
            <div key={r.id} className="rank-row">
              <span className="mono">{r.id}</span>
              <span className="rank-bar"><i style={{ width: `${(r.utility / maxU) * 100}%` }} /></span>
              <span className="math-expression">EIG = {f(r.eig_bits)} bits</span>
              <span className="math-expression">U = {f(r.utility)}</span>
            </div>
          ))}
          <p className="quiet small">U = expected information gain per unit compute, subject to feasibility rules. Same inputs → same ranking.</p>
        </div>
      </Step>

      <Step n={4} title="Agent selection" tone="is-accent">
        <p><strong className="mono">{chosenId ?? '—'}</strong> chosen by the principal investigator{round?.followed_argmax === false ? ' — overriding the top score' : round?.followed_argmax ? ' — matches the top score' : ''}.</p>
        {round?.justification ? <blockquote className="story-quote">{round.justification}</blockquote> : null}
      </Step>

      <Step n={5} title="Computation executes">
        <pre ref={termRef} className="story-terminal" aria-live="polite">
          <span className="term-head">noesis@lab · {label} · {lab.sourceId ?? 'sample'}</span>{'\n'}
          {log.slice(0, lines).map((a, i) => (
            <span key={i} className="term-line">
              {a.kind === 'tool' ? `$ ${a.agent} › ${a.name}(${a.args.slice(0, 60)})` : `→ ${a.from} hands off to ${a.to ?? '…'}: ${a.title}`}{'\n'}
            </span>
          ))}
          {lines < log.length ? <span className="term-cursor">▋</span> : <span className="term-done">✓ run complete{'\n'}</span>}
        </pre>
      </Step>

      <Step n={6} title="Result · uncertainty · verdict">
        {skipped ? <p className="quiet small">The lab feed could not summarise {skipped}{exp ? `; showing ${exp.id} instead` : ''}.</p> : null}
        {curves ? <DrawnChart curves={curves} play={play} /> : null}
        <div className="story-legend"><span className="lg-err">log₁₀ best error</span><span className="lg-ent">population entropy</span></div>
        {verdict ? (
          <div className="story-verdict">
            <span className={`badge badge-${verdict[1].verdict === 'supported' ? 'ok' : verdict[1].verdict === 'refuted' ? 'bad' : 'warn'}`}>{verdict[1].verdict}</span>
            <span><HypothesisSymbol id={verdict[0]} /> · <ScientificText>{verdict[1].measure}</ScientificText></span>
            <span className="math-expression">θ̂ = {f(verdict[1].effect.estimate)}</span>
            <span className="math-expression">95% CI [{f(verdict[1].effect.ci95?.[0])}, {f(verdict[1].effect.ci95?.[1])}]</span>
            {verdict[1].standardised_effect != null ? <span className="math-expression">d = {f(verdict[1].standardised_effect, 2)}</span> : null}
            <span className="math-expression"><i>n</i> = {verdict[1].n_units}</span>
          </div>
        ) : <p className="quiet">{!resultId ? 'No completed experiment yet.' : skipped && !exp ? 'No result summary available.' : 'Loading result…'}</p>}
      </Step>

      <Step n={7} title="Bayesian belief update">
        <div className="story-beliefs">
          {Object.entries(state.trajectories).slice(0, 5).map(([id, pts]) => {
            const before = pts[0]?.posterior ?? 0.5;
            const after = pts[pts.length - 1]?.posterior ?? before;
            return (
              <div key={id} className="belief-row">
                <HypothesisSymbol id={id} />
                <span className="belief-track">
                  <i className="b-before" style={{ width: `${before * 100}%` }} />
                  <i className={`b-after ${play ? 'is-on' : ''}`} style={{ width: `${after * 100}%` }} />
                </span>
                <span className="math-expression">{f(before, 2)} → {f(after, 2)}</span>
              </div>
            );
          })}
        </div>
      </Step>

      <Step n={8} title="Next decision changes" tone="is-accent">
        {lastDecision ? (
          <div className="story-pivot">
            <div className="pivot-before"><span className="eyebrow">Before</span><p>{firstDecision && firstDecision !== lastDecision ? firstDecision.decision : 'Initial plan'}</p></div>
            <span className="pivot-arrow" aria-hidden="true">→</span>
            <div className="pivot-after"><span className="eyebrow">After</span><p>{lastDecision.decision}</p>{lastDecision.next_experiment ? <span className="mono">next: {lastDecision.next_experiment}</span> : null}</div>
          </div>
        ) : <p className="quiet">No updated decision yet.</p>}
      </Step>

      <Step n={9} title="Impact">
        <div className="story-impact">
          <strong>{COMPUTE_SAVING}%</strong>
          <span>compute saved vs. exhaustive testing</span>
          <span className="badge badge-warn">BENCHMARK · team-reported</span>
        </div>
      </Step>

      <Step n={10} title="Provenance & interoperability">
        <div className="story-prov">
          <span className="mono hash">prereg sha256 · {state.prereg_sha256 ? `${state.prereg_sha256.slice(0, 16)}…${state.prereg_sha256.slice(-8)}` : 'not recorded'}</span>
          <span className="mono hash">source · {label} · {state.completed.join(' ') || '—'}</span>
          <span className="lang-chain">{LANG_CHAIN.map((l, i) => <span key={l}>{i ? <i>→</i> : null}<b>{l}</b></span>)}<em>BENCHMARK</em></span>
        </div>
      </Step>
    </div>
  );
}
