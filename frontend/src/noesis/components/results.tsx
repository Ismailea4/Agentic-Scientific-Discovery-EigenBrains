import type { ReactNode } from 'react';

export function ExecutionSummary({
  task,
  architecture,
  agents,
  quality,
  risk,
}: {
  task: string;
  architecture: string;
  agents: string[];
  quality?: string;
  risk?: string;
}) {
  return (
    <div className="result-summary">
      <p className="eyebrow">Run</p>
      <strong>{task}</strong>
      <dl className="kv">
        <div><dt>Discovery plan</dt><dd>{architecture}</dd></div>
        <div><dt>Specialists</dt><dd>{agents.join(' · ')}</dd></div>
        {quality && <div><dt>Confidence</dt><dd>{quality}</dd></div>}
        {risk && <div><dt>Uncertainty</dt><dd>{risk}</dd></div>}
      </dl>
    </div>
  );
}

export function AgentRun({
  agent,
  model,
  status,
  duration,
  cost,
}: {
  agent: string;
  model: string;
  status: 'running' | 'complete' | 'failed' | 'fallback';
  duration?: string;
  cost?: string;
}) {
  return (
    <article className="result-row">
      <span className={`live-dot is-${status}`} aria-hidden="true" />
      <div>
        <strong>{agent}</strong>
        <p className="quiet">{model}</p>
      </div>
      <span className="quiet">{status}</span>
      {duration && <span className="mono">{duration}</span>}
      {cost && <span className="mono">{cost}</span>}
    </article>
  );
}

export function AgentResult({ title, body }: { title: string; body: string }) {
  return (
    <article className="result-block">
      <p className="eyebrow">Output</p>
      <strong>{title}</strong>
      <p className="quiet">{body}</p>
    </article>
  );
}

export function EvidenceItem({ label, detail }: { label: string; detail: string }) {
  return (
    <article className="result-row">
      <span className="badge badge-granted">evidence</span>
      <strong>{label}</strong>
      <span className="quiet">{detail}</span>
    </article>
  );
}

export function CriticFinding({ severity, label }: { severity: 'note' | 'warn' | 'block'; label: string }) {
  const tone = severity === 'block' ? 'bad' : severity === 'warn' ? 'warn' : 'idle';
  return (
    <article className="result-row">
      <span className={`badge badge-${tone}`}>{severity}</span>
      <span>{label}</span>
    </article>
  );
}

export function VerificationResult({ passed, label }: { passed: boolean; label: string }) {
  return (
    <article className="result-row">
      <span className={`badge ${passed ? 'badge-ok' : 'badge-bad'}`}>{passed ? 'verified' : 'rejected'}</span>
      <span>{label}</span>
    </article>
  );
}

export function ResultStack({ children }: { children: ReactNode }) {
  return <div className="result-stack">{children}</div>;
}
