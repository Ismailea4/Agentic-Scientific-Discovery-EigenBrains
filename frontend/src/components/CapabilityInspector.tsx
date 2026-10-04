import { CapabilityBadge, type CapabilityState } from './ui';

export type LeaseStatus = 'active' | 'expired' | 'exhausted' | 'denied' | 'inactive' | 'none';

const LEASE_LABEL: Record<LeaseStatus, string> = {
  active: 'Active',
  expired: 'Expired',
  exhausted: 'Limited',
  denied: 'Denied',
  inactive: 'Idle',
  none: 'None',
};

function Row({ label, names, state }: { label: string; names: string[]; state: CapabilityState }) {
  if (names.length === 0) return null;
  return (
    <div className="cap-row">
      <span className="eyebrow">{label}</span>
      <span className="node-badges">
        {names.map((name) => (
          <CapabilityBadge key={`${state}-${name}`} name={name} state={state} />
        ))}
      </span>
    </div>
  );
}

export function CapabilityInspector({
  agent,
  granted,
  denied,
  mandatory,
  optional,
  taskScope,
  leaseStatus,
}: {
  agent: string;
  granted: string[];
  denied: string[];
  mandatory: string[];
  optional: string[];
  taskScope: string | null;
  leaseStatus: LeaseStatus;
}) {
  const empty = granted.length + denied.length + mandatory.length + optional.length === 0;
  return (
    <div className="inspector-body">
      <div className="kv-inline">
        <strong>{agent}</strong>
        <span className="quiet">{LEASE_LABEL[leaseStatus]}</span>
      </div>
      <p className="quiet">{taskScope ?? 'Any task'}</p>
      {empty && <p className="quiet">No capabilities</p>}
      <Row label="Granted" names={granted} state="granted" />
      <Row label="Denied" names={denied} state="denied" />
      <details className="disclosure">
        <summary>Approval requirements</summary>
        <Row label="Mandatory" names={mandatory} state="mandatory" />
        <Row label="Optional" names={optional} state="optional" />
        {mandatory.length === 0 && optional.length === 0 && <p className="quiet">None</p>}
      </details>
    </div>
  );
}
