import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

export const GlassButton = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost' | 'icon' | 'destructive';
}>(function GlassButton({
  variant = 'secondary',
  className,
  children,
  ...props
}, ref) {
  return (
    <button ref={ref} className={cx('btn', `btn-${variant}`, className)} {...props}>
      {children}
    </button>
  );
});

export function EmptyState({ title, body, mark }: { title: string; body?: string; mark?: ReactNode }) {
  return (
    <div className="empty">
      {mark && <div className="empty-mark" aria-hidden="true">{mark}</div>}
      <h3>{title}</h3>
      {body && <p className="quiet">{body}</p>}
    </div>
  );
}

export function StatusCapsule({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={cx('capsule', `capsule-${tone}`)}>
      <i aria-hidden="true" />
      {children}
    </span>
  );
}

type Tone = 'ok' | 'warn' | 'bad' | 'idle' | 'info';

export function StatusBadge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={cx('badge', `badge-${tone}`)}>{children}</span>;
}

export type CapabilityState = 'granted' | 'denied' | 'mandatory' | 'optional' | 'neutral';

export function CapabilityBadge({ name, state }: { name: string; state: CapabilityState }) {
  return <span className={cx('badge', `badge-${state}`)}>{name}</span>;
}

export function MetricCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
      {hint && <p className="quiet">{hint}</p>}
    </div>
  );
}

export function RiskIndicator({ score }: { score: number | null }) {
  const known = score !== null && Number.isFinite(score);
  const width = known ? Math.max(0, Math.min(100, score * 100)) : 0;
  return (
    <div>
      <div className="risk-top">
        <span className="metric-label">Risk</span>
        <strong>{known ? score.toFixed(2) : '—'}</strong>
      </div>
      <div className="risk-track" aria-hidden="true">
        <span style={{ width: `${width}%` }} />
      </div>

    </div>
  );
}

export function CostLatencyMetric({ cost, latency }: { cost: string; latency: string }) {
  return (
    <div className="pair">
      <div>
        <div className="metric-label">Cost</div>
        <strong>{cost}</strong>
      </div>
      <div>
        <div className="metric-label">Latency</div>
        <strong>{latency}</strong>
      </div>
    </div>
  );
}

export function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={option.value === value}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function formatPlain(value: number): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 3 }).format(value);
}
