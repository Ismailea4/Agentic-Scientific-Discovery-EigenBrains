import type { ReactNode } from 'react';
import { CapabilityBadge, StatusBadge } from './ui';

export interface InspectorCapability {
  name: string;
  state: 'granted' | 'denied' | 'mandatory' | 'optional' | 'neutral';
}

export function ObjectInspector({
  kind,
  title,
  status,
  model,
  latency,
  cost,
  capabilities = [],
  action,
  details,
}: {
  kind: string;
  title: string;
  status?: string;
  model?: string;
  latency?: string;
  cost?: string;
  capabilities?: InspectorCapability[];
  action?: ReactNode;
  details?: ReactNode;
}) {
  return (
    <div className="inspector-body object-inspector">
      <p className="eyebrow">{kind}</p>
      <div className="kv-inline">
        <strong>{title}</strong>
        {status ? <StatusBadge tone={status.toLowerCase().includes('den') ? 'bad' : 'idle'}>{status}</StatusBadge> : null}
      </div>
      {model || latency || cost ? (
        <dl className="kv">
          {model ? <div><dt>Model</dt><dd>{model}</dd></div> : null}
          {latency ? <div><dt>Latency</dt><dd>{latency}</dd></div> : null}
          {cost ? <div><dt>Cost</dt><dd>{cost}</dd></div> : null}
        </dl>
      ) : null}
      {capabilities.length > 0 ? (
        <div className="cap-row">
          <span className="eyebrow">Capabilities</span>
          <span className="node-badges">
            {capabilities.map((item) => <CapabilityBadge key={`${item.state}-${item.name}`} name={item.name} state={item.state} />)}
          </span>
        </div>
      ) : null}
      {action}
      {details ? <details className="disclosure" open><summary>Scientific record</summary>{details}</details> : null}
    </div>
  );
}
