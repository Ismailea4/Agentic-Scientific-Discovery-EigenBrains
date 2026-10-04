/** Shapes served by the discovery lab's read-only feed
 * (`discolab/discolab/bridge.py` + `views.py`). Keep in sync with those files. */

export interface CI {
  estimate: number | null;
  ci95: [number, number] | null;
}

export interface LabSource {
  id: string;
  kind: 'live' | 'record';
  events: number;
  experiments: number;
  prereg_sha256: string | null;
}

export interface LabHypothesis {
  id: string;
  family: string;
  origin: string;
  statement: string;
  status: string;
  posterior: number;
  n_direct_tests: number;
  last: { experiment: string; verdict: string; stage: string | null } | null;
}

export interface LabEvidence {
  source_id: string | null;
  source: 'OpenAlex' | 'arXiv';
  title: string | null;
  year: number | null;
  relation: string | null;
  hypothesis_id: string | null;
  claim: string | null;
}

export interface LabCandidate {
  id: string;
  title: string;
  kind: string;
  stage: string | null;
  hypotheses: string[];
  status: string;
  proposed_by: string;
  utility: number | null;
  eig_bits: number | null;
  est_wall_seconds: number | null;
  feasible: boolean | null;
  violations: string[] | null;
}

export interface TrajectoryPoint {
  seq: number;
  posterior: number;
  label: string;
  verdict?: string | null;
  experiment?: string | null;
}

export interface ScoringRow {
  id: string;
  title: string;
  kind: string;
  stage: string | null;
  eig_bits: number;
  utility: number;
  feasible: boolean;
  violations: string[];
  est_wall_seconds: number;
  hypotheses: string[];
}

export interface ScoringRound {
  round: number;
  seq: number;
  argmax: string | null;
  selected: string | null;
  followed_argmax: boolean | null;
  justification: string | null;
  rows: ScoringRow[];
}

export interface LabDecision {
  seq: number;
  by: string;
  decision: string | null;
  rationale: string | null;
  next_experiment: string | null;
}

export interface LabAnalysis {
  by: string;
  interpretation: string;
  threats_to_validity: string[];
}

export interface LabState {
  question: string;
  compute_seconds: { used: number; budget: number };
  hypotheses: LabHypothesis[];
  evidence: LabEvidence[];
  candidates: LabCandidate[];
  selected: string | null;
  latest_scoring_round: { round: number; argmax: string | null } | null;
  next_decision: { decision?: string; rationale?: string; next_experiment?: string | null } | null;
  events: number;
  prereg_sha256: string | null;
  trajectories: Record<string, TrajectoryPoint[]>;
  rounds: ScoringRound[];
  decisions: LabDecision[];
  analyses: Record<string, LabAnalysis>;
  completed: string[];
}

export type LabActivity =
  | { t: number; kind: 'handoff'; from: string; to: string | null; title: string; state: 'running' | 'finished' }
  | { t: number; kind: 'approval'; agent: string; text: string }
  | { t: number; kind: 'tool'; agent: string; name: string; args: string }
  | { t: number; kind: 'say'; agent: string; text: string };

export interface LabVerdict {
  verdict: string;
  measure: string;
  effect: CI;
  standardised_effect: number | null;
  n_units: number;
}

export interface CurveSet {
  shifts: number[];
  controllers: Record<string, { n_runs: number; log10_best_err_mean: number[]; entropy_mean: number[]; p_mut_mean: number[] }>;
}

export interface LabExperiment {
  id: string;
  title?: string;
  kind?: string;
  stage?: string;
  status?: string;
  runtime_sec?: number | null;
  verdicts?: Record<string, LabVerdict>;
  auroc?: Record<string, CI>;
  per_controller?: Record<string, { rmst_gens: number | null; recovery_rate: CI; cvar90_recovery_gens: number | null; mean_p_mut: number | null }>;
  analysis?: LabAnalysis;
  curves?: Record<string, CurveSet> | null;
  spec?: Record<string, unknown>;
  score?: { eig_bits: number | null; utility: number | null };
  result?: null;
  error?: string | null;
}

export interface LedgerEvent {
  seq: number;
  ts: string;
  type: string;
  actor: string;
  id: string | null;
}
