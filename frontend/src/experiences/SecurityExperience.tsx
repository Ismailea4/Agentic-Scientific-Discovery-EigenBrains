import { useEffect, useState } from 'react';
import { ApiError } from '../api/client';
import { systemApi } from '../api/system';
import type { PolicyEvaluationResponse } from '../api/types';
import { CapabilityInspector } from '../components/CapabilityInspector';
import { ObjectInspector } from '../components/ObjectInspector';
import { SampleMark } from '../components/SampleMark';
import { useShell } from '../components/shell';
import { CapabilityBadge } from '../components/ui';
import { fixtureGraph, fixturePolicy } from '../dev/fixtures';

export function SecurityExperience({ mode }: { mode: 'narrative' | 'workspace' }) {
  const { setInspector, setInspectorOpen } = useShell();
  const [decision, setDecision] = useState<PolicyEvaluationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alpha = fixtureGraph.find((node) => node.id === 'alpha') ?? fixtureGraph[0];

  useEffect(() => {
    let cancelled = false;
    systemApi.evaluatePolicy(fixturePolicy).then((result) => {
      if (!cancelled) setDecision(result);
    }).catch((reason: unknown) => {
      if (!cancelled) setError(reason instanceof ApiError ? reason.message : String(reason));
    });
    return () => { cancelled = true; };
  }, []);

  const inspect = (name: string, denied: boolean) => {
    setInspector(
      <ObjectInspector
        kind="Capability"
        title={name}
        status={denied ? 'Denied' : 'Granted'}
        capabilities={[{ name, state: denied ? 'denied' : 'granted' }]}
        details={<p className="quiet">Scope: {fixturePolicy.task_scope ?? 'Any task'} · Lease: {denied ? 'policy denial' : 'active sample lease'}</p>}
      />,
    );
    setInspectorOpen(true);
  };

  if (mode === 'narrative') {
    return (
      <section className="experience experience-narrative security-path" aria-label="Capability policy sample">
        <div className="security-agent agent-node"><span className="node-status"><i className="live-dot is-running" />Agent</span><strong>Research</strong></div>
        <div className="security-stem" aria-hidden="true"><span /></div>
        <div className="security-branches">
          <div className="security-branch is-allowed">
            <span className="branch-rail" aria-hidden="true" />
            <button type="button" className="security-capability" onClick={() => inspect('evidence.read', false)}><CapabilityBadge name="evidence.read" state="granted" /></button>
            <small>resolved</small>
          </div>
          <div className="security-branch is-allowed">
            <span className="branch-rail" aria-hidden="true" />
            <button type="button" className="security-capability" onClick={() => inspect('web.search', false)}><CapabilityBadge name="web.search" state="granted" /></button>
            <small>resolved</small>
          </div>
          <div className="security-branch is-denied">
            <span className="branch-rail"><i aria-hidden="true" /></span>
            <button type="button" className="security-capability denied" onClick={() => inspect('filesystem.write', true)}><CapabilityBadge name="filesystem.write" state="denied" /></button>
            <small>not issued</small>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="experience experience-workspace security-workspace">
      <div className="view-toolbar experience-toolbar"><SampleMark /></div>
      {error ? <p className="alert" role="alert">{error}</p> : null}
      <div className="security-layout">
        <CapabilityInspector
          agent={alpha.label}
          granted={decision?.granted ?? alpha.granted}
          denied={decision?.denied ?? alpha.denied}
          mandatory={fixturePolicy.requirements.filter((item) => item.mandatory).map((item) => item.capability)}
          optional={fixturePolicy.requirements.filter((item) => !item.mandatory).map((item) => item.capability)}
          taskScope={fixturePolicy.task_scope}
          leaseStatus="active"
        />
        <div className="capability-actions" aria-label="Capability decisions">
          {(decision?.granted ?? alpha.granted).map((name) => <button type="button" key={name} onClick={() => inspect(name, false)}><CapabilityBadge name={name} state="granted" /></button>)}
          {(decision?.denied ?? alpha.denied).map((name) => <button type="button" key={name} onClick={() => inspect(name, true)}><CapabilityBadge name={name} state="denied" /></button>)}
        </div>
      </div>
      <p className="experience-footnote">{decision?.allowed ? 'Mandatory capability satisfied; the optional export path remains structurally denied.' : 'Waiting for the policy engine.'}</p>
    </section>
  );
}
