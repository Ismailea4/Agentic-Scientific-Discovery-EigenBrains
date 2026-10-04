import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { ApiError } from '../api/client';
import { labApi } from '../api/lab';
import type { CI, CurveSet, LabActivity, LabEvidence, LabExperiment, LabHypothesis, LabState } from '../api/lab-types';
import { ObjectInspector } from '../components/ObjectInspector';
import { HypothesisSymbol, PosteriorProbability, ScientificText } from '../components/ScientificText';
import { useShell } from '../components/shell';
import { EmptyState, StatusBadge } from '../components/ui';
import { useLab } from './LabContext';

/* ------------------------------------------------------------ helpers */

const STAGES = ['Question', 'Evidence', 'Hypothesis', 'Experiment', 'Result', 'Updated decision'] as const;

const AGENTS: { id: string; label: string; role: string }[] = [
  { id: 'pi', label: 'Principal investigator', role: 'Chooses, runs and concludes experiments' },
  { id: 'literature', label: 'Literature analyst', role: 'Records verified prior work' },
  { id: 'designer', label: 'Experiment designer', role: 'Proposes and scores competing experiments' },
  { id: 'critic', label: 'Scientific critic', role: 'Interprets results, flags threats to validity' },
];

const fmt = (n: number | null | undefined, d = 3) => (n == null || Number.isNaN(n) ? '—' : Number(n.toFixed(d)).toString());
const fmtCI = (c: CI | undefined) => (!c ? '—' : `${fmt(c.estimate)}${c.ci95 ? ` [${fmt(c.ci95[0])}, ${fmt(c.ci95[1])}]` : ''}`);
const pct = (n: number) => `${Math.round(n * 100)}%`;
const time = (t: number) => new Date(t * 1000).toISOString().slice(11, 19);

function verdictTone(v: string | undefined | null) {
  return v === 'supported' ? 'ok' : v === 'refuted' ? 'bad' : v === 'open' || v === 'inconclusive' ? 'warn' : 'idle';
}

function sourceHref(e: LabEvidence) {
  if (!e.source_id) return null;
  return e.source === 'arXiv' ? `https://arxiv.org/abs/${e.source_id}` : `https://openalex.org/${e.source_id}`;
}

function reachedStage(s: LabState): number {
  if (s.decisions.length) return 5;
  if (s.completed.length) return 4;
  if (s.candidates.length) return 3;
  if (s.hypotheses.length) return 2;
  if (s.evidence.length) return 1;
  return 0;
}

function LoopStrip({ reached }: { reached: number }) {
  return (
    <ol className="lab-loop" aria-label="Discovery loop progress">
      {STAGES.map((label, i) => (
        <li key={label} className={i < reached ? 'is-done' : i === reached ? 'is-current' : undefined}>
          <span>{i + 1}</span>{label}
        </li>
      ))}
    </ol>
  );
}

function Loading({ label }: { label: string }) {
  const lab = useLab();
  if (lab.error) return <p className="alert" role="alert">{lab.error}</p>;
  return <p className="quiet" role="status">{label}</p>;
}

/* ------------------------------------------------------- Discovery Loop */

function achievements(id: string, s: LabState, activity: LabActivity[]): string[] {
  const calls = (name: string) => activity.filter((a) => a.kind === 'tool' && a.agent === id && a.name === name).length;
  const byOrigin = (who: string) => s.hypotheses.filter((h) => h.origin.includes(who)).length;
  const lastSay = [...activity].reverse().find((a) => a.kind === 'say' && a.agent === id);
  const out: string[] = [];
  if (id === 'pi') {
    const runs = calls('run_experiment');
    out.push(`Selected ${s.rounds.filter((r) => r.selected).length} experiment(s) from ${s.rounds.length} scoring round(s)`);
    out.push(`Ran ${runs || s.completed.length} experiment(s): ${s.completed.join(', ') || 'none yet'}`);
    out.push(`Recorded ${s.decisions.length} updated decision(s)`);
  } else if (id === 'literature') {
    const n = s.evidence.length;
    const hyps = new Set(s.evidence.map((e) => e.hypothesis_id).filter(Boolean));
    out.push(`Recorded ${n} verified source(s) covering ${hyps.size} hypothesis(es)`);
    out.push(`Ran ${calls('search_literature') + calls('search_arxiv_papers')} literature search(es)`);
  } else if (id === 'designer') {
    out.push(`Proposed ${s.candidates.filter((c) => c.proposed_by === 'designer').length || s.candidates.length} competing experiment(s)`);
    out.push(`Scored candidates ${calls('score_experiments')} time(s) by information gain`);
  } else if (id === 'critic') {
    const a = Object.values(s.analyses).filter((x) => x.by === 'critic');
    out.push(`Analysed ${a.length} result(s): ${Object.keys(s.analyses).join(', ') || 'none yet'}`);
    out.push(`Flagged ${a.reduce((n, x) => n + x.threats_to_validity.length, 0)} threat(s) to validity`);
    const added = byOrigin('critic');
    if (added) out.push(`Proposed ${added} new hypothesis(es)`);
  }
  if (lastSay && lastSay.kind === 'say') out.push(`Latest: ${lastSay.text.replace(/[*#]/g, '').slice(0, 180)}${lastSay.text.length > 180 ? '…' : ''}`);
  return out;
}

export function LiveDiscovery() {
  const { state, activity } = useLab();
  const { setInspector, setInspectorOpen } = useShell();
  const [active, setActive] = useState<string | null>(null);

  const perAgent = useMemo(() => {
    const map: Record<string, { tools: number; running: boolean; last: LabActivity | null }> = {};
    for (const a of AGENTS) map[a.id] = { tools: 0, running: false, last: null };
    for (const item of activity) {
      const who = item.kind === 'handoff' ? item.to ?? '' : item.agent;
      const entry = map[who];
      if (!entry) continue;
      if (item.kind === 'tool') entry.tools += 1;
      if (item.kind === 'handoff') entry.running = item.state === 'running';
      entry.last = item;
    }
    return map;
  }, [activity]);

  useEffect(() => {
    if (!active) return;
    const agent = AGENTS.find((a) => a.id === active);
    const items = activity.filter((x) => (x.kind === 'handoff' ? x.to : x.agent) === active).slice(-25).reverse();
    setInspector(
      <ObjectInspector
        kind="Omnigent agent"
        title={agent?.label ?? active}
        status={perAgent[active]?.running ? 'Working' : 'Idle'}
        details={<ul className="lab-feed compact">{items.map((x, i) => <ActivityRow key={`${x.t}-${i}`} item={x} />)}</ul>}
      />,
    );
    return () => setInspector(null);
  }, [active, activity, perAgent, setInspector]);

  if (!state) return <Loading label="Loading lab state…" />;

  return (
    <section className="experience experience-workspace lab-view">
      <p className="lab-question"><span className="eyebrow">Question</span>{state.question}</p>
      <LoopStrip reached={reachedStage(state)} />
      <div className="lab-agents">
        {AGENTS.map((a) => {
          const info = perAgent[a.id];
          return (
            <button key={a.id} type="button" className={`lab-agent${info?.running ? ' is-running' : ''}${active === a.id ? ' is-selected' : ''}`} onClick={() => { setActive(a.id); setInspectorOpen(true); }}>
              <span className="lab-agent-dot" aria-hidden="true" />
              <strong>{a.label}</strong>
              <small>{a.role}</small>
              <ul className="lab-achieved">{achievements(a.id, state, activity).map((line, i) => <li key={i}>{line}</li>)}</ul>
              <span className="quiet">{info?.tools ?? 0} tool calls{info?.running ? ' · working' : ''} · click for full log</span>
            </button>
          );
        })}
      </div>
      <h3 className="lab-h">Agent activity</h3>
      {activity.length === 0 ? <EmptyState title="No agent activity yet" body="The Omnigent event log for this source is empty." /> : (
        <ul className="lab-feed">{activity.slice(-60).reverse().map((x, i) => <ActivityRow key={`${x.t}-${i}`} item={x} />)}</ul>
      )}
    </section>
  );
}

function ActivityRow({ item }: { item: LabActivity }) {
  return (
    <li className={`lab-act lab-act-${item.kind}`}>
      <span className="mono quiet">{time(item.t)}</span>
      {item.kind === 'handoff' ? <span><strong>{item.from}</strong> → <strong>{item.to}</strong> · {item.title} <em>{item.state}</em></span> : null}
      {item.kind === 'tool' ? <span><strong>{item.agent}</strong> called <code>{item.name}</code> <span className="quiet mono">{item.args}</span></span> : null}
      {item.kind === 'say' ? <span><strong>{item.agent}</strong>: {item.text}</span> : null}
      {item.kind === 'approval' ? <span><strong>{item.agent}</strong> requested approval: {item.text}</span> : null}
    </li>
  );
}

/* ----------------------------------------------------------- Hypotheses */

function Trajectory({ points }: { points: { posterior: number; label: string }[] }) {
  if (points.length < 2) return null;
  const w = 160, h = 40;
  const d = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${(i / (points.length - 1)) * w},${h - p.posterior * h}`).join(' ');
  return (
    <svg className="lab-traj" viewBox={`-4 -4 ${w + 8} ${h + 8}`} role="img" aria-label={`Posterior trajectory: ${points.map((p) => `${p.label} ${pct(p.posterior)}`).join(', ')}`}>
      <line x1="0" x2={w} y1={h / 2} y2={h / 2} className="lab-traj-mid" />
      <path d={d} />
      {points.map((p, i) => <circle key={i} cx={(i / (points.length - 1)) * w} cy={h - p.posterior * h} r="3" />)}
    </svg>
  );
}

export function LiveHypotheses() {
  const { state } = useLab();
  const { setInspector, setInspectorOpen } = useShell();
  const [selected, setSelected] = useState<LabHypothesis | null>(null);

  useEffect(() => {
    if (!selected || !state) return;
    const ev = state.evidence.filter((e) => e.hypothesis_id === selected.id);
    setInspector(
      <ObjectInspector
        kind={`Hypothesis · ${selected.family}`}
        title={selected.id}
        status={selected.status}
        details={(
          <div className="lab-inspect">
            <p className="lab-statement"><ScientificText>{selected.statement}</ScientificText></p>
            <p className="stat-line"><span>Posterior probability</span><PosteriorProbability id={selected.id} value={selected.posterior} /></p>
            <p className="quiet">Origin: {selected.origin}</p>
            <h4>Linked evidence ({ev.length})</h4>
            {ev.length ? ev.map((e, i) => <EvidenceItem key={i} e={e} />) : <p className="quiet">No evidence recorded for this hypothesis.</p>}
          </div>
        )}
      />,
    );
    return () => setInspector(null);
  }, [selected, setInspector, state]);

  if (!state) return <Loading label="Loading hypotheses…" />;
  const rounds = [...state.rounds].reverse();

  return (
    <section className="experience experience-workspace lab-view">
      <aside className="stat-key" aria-label="Statistical notation">
        <span><strong>Pr(<i>H</i> | <i>D</i>)</strong> posterior probability after the observed data</span>
        <span><strong><i>p</i>-value</strong> not supplied by this lab feed; never inferred from the posterior</span>
      </aside>
      <div className="lab-hyps">
        {state.hypotheses.map((h) => (
          <button key={h.id} type="button" className={`lab-hyp${selected?.id === h.id ? ' is-selected' : ''}`} onClick={() => { setSelected(h); setInspectorOpen(true); }}>
            <div className="lab-hyp-head">
              <strong><HypothesisSymbol id={h.id} /></strong>
              <StatusBadge tone={verdictTone(h.status)}>{h.status}</StatusBadge>
              <span className="quiet">{h.family}</span>
            </div>
            <p><ScientificText>{h.statement}</ScientificText></p>
            <div className="lab-post">
              <div className="lab-post-bar"><i style={{ width: pct(h.posterior) }} /></div>
              <PosteriorProbability id={h.id} value={h.posterior} />
            </div>
            <Trajectory points={state.trajectories[h.id] ?? []} />
            <small className="quiet">{h.n_direct_tests} direct test{h.n_direct_tests === 1 ? '' : 's'}{h.last ? ` · last ${h.last.experiment}: ${h.last.verdict}` : ''}</small>
          </button>
        ))}
      </div>
      <h3 className="lab-h">Experiment selection rounds</h3>
      <p className="quiet"><span className="math-expression"><i>U</i> = EIG − compute cost − held-out data used</span>. EIG is expected information gain in bits. The PI may deviate from the top-scoring candidate, with a recorded justification.</p>
      {rounds.length === 0 ? <EmptyState title="No scoring rounds yet" /> : rounds.map((r) => (
        <article key={r.round} className="lab-round">
          <header><strong>Round {r.round}</strong> {r.selected ? <StatusBadge tone={r.followed_argmax ? 'ok' : 'warn'}>{r.followed_argmax ? 'followed top score' : 'deviated from top score'}</StatusBadge> : null}</header>
          <div className="lab-table-wrap">
            <table className="lab-table">
              <thead><tr><th>Experiment</th><th>Tests</th><th>EIG (bits)</th><th>Utility</th><th>Est. compute</th><th /></tr></thead>
              <tbody>
                {[...r.rows].sort((a, b) => b.utility - a.utility).map((row) => (
                  <tr key={row.id} className={row.id === r.selected ? 'is-selected' : row.feasible ? undefined : 'is-infeasible'}>
                    <td><strong>{row.id}</strong> {row.title}</td>
                    <td>{row.hypotheses.join(', ')}</td>
                    <td className="mono">{fmt(row.eig_bits)}</td>
                    <td className="mono">{fmt(row.utility)}</td>
                    <td className="mono">{fmt(row.est_wall_seconds, 1)} s</td>
                    <td>{row.id === r.argmax ? <StatusBadge tone="idle">top</StatusBadge> : null}{row.id === r.selected ? <StatusBadge tone="ok">chosen</StatusBadge> : null}{!row.feasible ? <StatusBadge tone="bad">infeasible</StatusBadge> : null}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {r.justification ? <p className="lab-just"><span className="eyebrow">PI justification</span>{r.justification}</p> : null}
        </article>
      ))}
    </section>
  );
}

/* --------------------------------------------------- Human Approval Gate */

export function LiveApproval() {
  const { state, activity, source } = useLab();
  if (!state) return <Loading label="Loading approval state…" />;
  const approvals = activity.filter((a): a is Extract<LabActivity, { kind: 'approval' }> => a.kind === 'approval');
  const blocked = state.candidates.filter((c) => c.feasible === false || (c.violations?.length ?? 0) > 0);
  const pending = state.hypotheses.filter((h) => h.status === 'supported' && h.last?.stage === 'development');
  const used = state.compute_seconds.used;
  const budget = state.compute_seconds.budget || 1;

  return (
    <section className="experience experience-workspace lab-view">
      <article className="lab-card">
        <p className="eyebrow">Policy</p>
        <strong>Confirmatory runs on held-out landscapes need human approval</strong>
        <p>Held-out data can only be seen once, so the lab pauses and asks before the principal investigator spends it. Approval is given in the lab terminal; this view shows what was requested.</p>
      </article>
      <h3 className="lab-h">Approval requests ({approvals.length})</h3>
      {approvals.length === 0 ? (
        <EmptyState title="No approvals requested" body={source?.kind === 'live' ? 'New requests appear here as soon as the lab asks.' : 'This recorded run never reached a confirmatory run.'} />
      ) : (
        <ul className="lab-feed">{approvals.slice().reverse().map((a, i) => <ActivityRow key={i} item={a} />)}</ul>
      )}
      <h3 className="lab-h">Waiting for confirmatory approval ({pending.length})</h3>
      <p className="quiet">These hypotheses were supported only on development landscapes. Confirming them needs a held-out run, and that run needs your approval.</p>
      {pending.length === 0 ? <p className="quiet">No hypothesis is waiting for confirmation.</p> : (
        <ul className="lab-list">{pending.map((h) => <li key={h.id}><strong>{h.id}</strong> <StatusBadge tone="warn">needs approval to confirm</StatusBadge><br />{h.statement}<br /><span className="quiet">Posterior {pct(h.posterior)} · last tested in {h.last?.experiment}</span></li>)}</ul>
      )}
      <h3 className="lab-h">Experiments by gate</h3>
      <div className="lab-table-wrap"><table className="lab-table"><thead><tr><th>Experiment</th><th>Stage</th><th>Gate</th><th>Status</th></tr></thead><tbody>
        {state.candidates.map((c) => {
          const gated = c.stage === 'confirmatory';
          return <tr key={c.id}><td><strong>{c.id}</strong> {c.title}</td><td>{c.stage ?? '—'}</td><td>{gated ? <StatusBadge tone="warn">human approval</StatusBadge> : c.feasible === false ? <StatusBadge tone="bad">blocked by rule</StatusBadge> : <StatusBadge tone="ok">automatic</StatusBadge>}</td><td>{c.status}</td></tr>;
        })}
      </tbody></table></div>
      <h3 className="lab-h">Compute budget</h3>
      <div className="lab-post lab-budget">
        <div className="lab-post-bar"><i style={{ width: pct(Math.min(1, used / budget)) }} /></div>
        <span className="mono">{fmt(used, 1)} s of {fmt(budget, 0)} s</span>
      </div>
      <h3 className="lab-h">Blocked by constraints ({blocked.length})</h3>
      {blocked.length === 0 ? <p className="quiet">No candidate was blocked by the planner's hard constraints.</p> : (
        <ul className="lab-list">{blocked.map((c) => <li key={c.id}><strong>{c.id}</strong> {c.title}<br /><span className="quiet">{(c.violations ?? []).join('; ') || 'infeasible'}</span></li>)}</ul>
      )}
    </section>
  );
}

/* ------------------------------------------------------- Research Record */

function EvidenceItem({ e }: { e: LabEvidence }) {
  const href = sourceHref(e);
  return (
    <article className="research-entry lab-evidence">
      <p className="eyebrow">{e.source} · {e.relation ?? 'related'}{e.hypothesis_id ? ` · ${e.hypothesis_id}` : ''}</p>
      <p>{e.claim}</p>
      <cite>{href ? <a href={href} target="_blank" rel="noreferrer">{e.title}</a> : e.title}{e.year ? ` (${e.year})` : ''}</cite>
    </article>
  );
}

function Curves({ curves }: { curves: Record<string, CurveSet> }) {
  const landscapes = Object.keys(curves);
  const [land, setLand] = useState(landscapes[0] ?? '');
  const set = curves[land];
  if (!set) return null;
  const series = Object.entries(set.controllers);
  const all = series.flatMap(([, c]) => c.log10_best_err_mean);
  const min = Math.min(...all), max = Math.max(...all);
  const n = series[0]?.[1].log10_best_err_mean.length ?? 0;
  const w = 520, h = 180;
  const x = (i: number) => (n > 1 ? (i / (n - 1)) * w : 0);
  const y = (v: number) => (max === min ? h / 2 : h - ((v - min) / (max - min)) * h);
  return (
    <figure className="lab-curves">
      <figcaption>
        <span>Best error per generation (log10, mean over runs)</span>
        <select value={land} onChange={(event) => setLand(event.target.value)} aria-label="Landscape">{landscapes.map((l) => <option key={l}>{l}</option>)}</select>
      </figcaption>
      <svg viewBox={`-30 -8 ${w + 40} ${h + 28}`} role="img" aria-label={`Error curves on ${land}`}>
        {set.shifts.map((s) => <line key={s} className="lab-shift" x1={x(s)} x2={x(s)} y1={0} y2={h} />)}
        {series.map(([name, c], i) => (
          <path key={name} className={`lab-series s${i % 6}`} d={c.log10_best_err_mean.map((v, j) => `${j ? 'L' : 'M'}${x(j)},${y(v)}`).join(' ')} />
        ))}
        <text x={-6} y={6} textAnchor="end">{fmt(max, 1)}</text>
        <text x={-6} y={h} textAnchor="end">{fmt(min, 1)}</text>
        <text x={w} y={h + 18} textAnchor="end">generation {n}</text>
      </svg>
      <ul className="lab-legend">{series.map(([name, c], i) => <li key={name}><i className={`s${i % 6}`} />{name} <span className="quiet">n={c.n_runs}</span></li>)}</ul>
    </figure>
  );
}

function CriticAnalysis({ analysis }: { analysis: NonNullable<LabExperiment['analysis']> }) {
  const sections = analysis.interpretation
    .split(/\b(?=(?:RESULT|INTERPRETATION|CONCLUSION|LIMITATION|RECOMMENDATION):?\s)/i)
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const match = part.match(/^(RESULT|INTERPRETATION|CONCLUSION|LIMITATION|RECOMMENDATION):?\s*([\s\S]*)$/i);
      return match ? { label: match[1] ?? 'Assessment', text: match[2] ?? part } : { label: 'Assessment', text: part };
    });

  return (
    <section className="lab-analysis" aria-label="Critic analysis">
      <header className="lab-analysis-head">
        <div>
          <p className="eyebrow">Independent review</p>
          <h4>Critic analysis</h4>
        </div>
        <StatusBadge tone="info">{analysis.by}</StatusBadge>
      </header>
      <div className="lab-analysis-sections">
        {sections.map((section, index) => (
          <section key={`${section.label}-${index}`} className="lab-analysis-section">
            <h5>{section.label}</h5>
            <p className="lab-longform"><ScientificText>{section.text}</ScientificText></p>
          </section>
        ))}
      </div>
      <div className="lab-threats">
        <h5>Threats to validity <span>{analysis.threats_to_validity.length}</span></h5>
        {analysis.threats_to_validity.length ? (
          <ol>
            {analysis.threats_to_validity.map((threat, index) => (
              <li key={index}><span aria-hidden="true">{index + 1}</span><p><ScientificText>{threat}</ScientificText></p></li>
            ))}
          </ol>
        ) : <p className="quiet">No threats to validity were recorded.</p>}
      </div>
    </section>
  );
}

function ExperimentEntry({ id, title }: { id: string; title: string }) {
  const { baseUrl, sourceId } = useLab();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<LabExperiment | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || data || !sourceId) return;
    labApi.experiment(baseUrl, sourceId, id).then(setData).catch((r: unknown) => setError(r instanceof ApiError ? r.message : String(r)));
  }, [baseUrl, data, id, open, sourceId]);

  return (
    <article className="research-entry lab-exp">
      <button type="button" className="lab-exp-head" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className="eyebrow">Experiment · {id}</span>
        <strong>{title}</strong>
        <span className="quiet">{open ? 'Hide result' : 'Show result'}</span>
      </button>
      {open ? (
        <div className="lab-exp-body">
          {error ? <p className="alert">{error}</p> : null}
          {!data && !error ? <p className="quiet">Loading result…</p> : null}
          {data ? (
            <>
              <p className="quiet">{data.kind} · {data.stage} stage{data.runtime_sec != null ? ` · ${fmt(data.runtime_sec, 1)} s compute` : ''}</p>
              {data.verdicts ? (
            <ul className="lab-verdicts">
                  {Object.entries(data.verdicts).map(([h, v]) => (
                    <li key={h}>
                       <StatusBadge tone={verdictTone(v.verdict)}><HypothesisSymbol id={h} /> {v.verdict}</StatusBadge>
                       <span><strong>Outcome:</strong> <ScientificText>{v.measure}</ScientificText></span>
                       <span className="result-stat"><span><i>θ̂</i> effect estimate</span><strong>{fmt(v.effect.estimate)}</strong></span>
                       <span className="result-stat"><span>95% confidence interval</span><strong>{v.effect.ci95 ? `[${fmt(v.effect.ci95[0])}, ${fmt(v.effect.ci95[1])}]` : 'not reported'}</strong></span>
                       <span className="result-stat"><span><i>n</i> experimental units</span><strong>{v.n_units}</strong></span>
                       <span className="result-stat"><span><i>p</i>-value</span><strong>not reported</strong></span>
                    </li>
                  ))}
                </ul>
              ) : null}
              {data.auroc ? (
                <table className="lab-table"><thead><tr><th>Feature set</th><th>AUROC estimate [95% CI]</th></tr></thead>
                  <tbody>{Object.entries(data.auroc).map(([k, v]) => <tr key={k}><td>{k}</td><td className="mono">{fmtCI(v)}</td></tr>)}</tbody></table>
              ) : null}
              {data.per_controller ? (
                <table className="lab-table"><thead><tr><th>Controller</th><th>Recovery time (gens)</th><th>Recovery rate [95% CI]</th></tr></thead>
                  <tbody>{Object.entries(data.per_controller).map(([k, v]) => <tr key={k}><td>{k}</td><td className="mono">{fmt(v.rmst_gens, 2)}</td><td className="mono">{fmtCI(v.recovery_rate)}</td></tr>)}</tbody></table>
              ) : null}
              {data.curves ? <Curves curves={data.curves} /> : null}
              {data.analysis ? <CriticAnalysis analysis={data.analysis} /> : null}
            </>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <details className="lab-section" open>
      <summary><span className="lab-h">{title}</span><span className="lab-chev" aria-hidden="true">›</span></summary>
      <div className="lab-section-body">{children}</div>
    </details>
  );
}

export function LiveRecord() {
  const { state, ledger } = useLab();
  if (!state) return <Loading label="Loading research record…" />;
  const titles = Object.fromEntries(state.candidates.map((c) => [c.id, c.title]));

  return (
    <section className="experience experience-workspace lab-view lab-record">
      <p className="lab-question"><span className="eyebrow">Question · pre-registered{state.prereg_sha256 ? ` · ${state.prereg_sha256.slice(0, 10)}` : ''}</span>{state.question}</p>
      <Section title={`Evidence (${state.evidence.length})`}>
        {state.evidence.length ? state.evidence.map((e, i) => <EvidenceItem key={i} e={e} />) : <p className="quiet">No evidence recorded yet.</p>}
      </Section>
      <Section title={`Hypotheses (${state.hypotheses.length})`}>
        {state.hypotheses.map((h) => <article key={h.id} className="research-entry"><p className="eyebrow"><HypothesisSymbol id={h.id} /> · {h.family} · {h.status}</p><p><ScientificText>{h.statement}</ScientificText></p><p className="stat-line"><span>Posterior probability</span><PosteriorProbability id={h.id} value={h.posterior} /></p></article>)}
      </Section>
      <Section title={`Experiments & results (${state.completed.length})`}>
        {state.completed.length ? state.completed.map((id) => <ExperimentEntry key={id} id={id} title={titles[id] ?? id} />) : <p className="quiet">No experiment has completed yet.</p>}
      </Section>
      <Section title={`Updated decisions (${state.decisions.length})`}>
        {state.decisions.length ? <div className="lab-decisions">{state.decisions.map((d, index) => (
          <article key={d.seq} className="research-entry decision">
            <header className="decision-head">
              <span className="decision-index">{index + 1}</span>
              <div><p className="eyebrow">Decision #{d.seq}</p><span className="quiet">Made by {d.by}</span></div>
            </header>
            <div className="decision-outcome">
              <span className="eyebrow">Decision</span>
              <strong>{d.decision || 'No decision statement recorded'}</strong>
            </div>
            {d.rationale ? (
              <div className="decision-rationale">
                <h5>Why this decision</h5>
                <p className="lab-longform"><ScientificText>{d.rationale}</ScientificText></p>
              </div>
            ) : null}
            <footer className="decision-next">
              <span>Next action</span>
              <strong>{d.next_experiment ? `Run ${d.next_experiment}` : 'No further experiment selected'}</strong>
            </footer>
          </article>
        ))}</div> : <p className="quiet">No updated decision has been recorded yet.</p>}
      </Section>
      {ledger.length ? (
        <>
          <h3 className="lab-h">New ledger events</h3>
          <ul className="lab-feed compact">{ledger.slice().reverse().map((e) => <li key={e.seq} className="lab-act"><span className="mono quiet">#{e.seq}</span><span><strong>{e.actor}</strong> {e.type}{e.id ? ` · ${e.id}` : ''}</span></li>)}</ul>
        </>
      ) : null}
    </section>
  );
}
