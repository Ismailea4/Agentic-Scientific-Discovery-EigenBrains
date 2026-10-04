import { useEffect, useMemo, useState } from 'react';
import { ApiError } from '../api/client';
import { systemApi } from '../api/system';
import type { FallbackDecisionResponse, PolicyEvaluationResponse } from '../api/types';
import { AgentGraph } from '../components/AgentGraph';
import { CapabilityInspector } from '../components/CapabilityInspector';
import { ObjectInspector } from '../components/ObjectInspector';
import type { MenuItem } from '../components/overlay';
import { SampleMark } from '../components/SampleMark';
import { useShell } from '../components/shell';
import { SegmentedControl, StatusBadge } from '../components/ui';
import {
  fixtureFallback,
  fixtureFallbackPath,
  fixtureGraph,
  fixturePath,
  fixturePolicy,
} from '../dev/fixtures';

type Route = 'primary' | 'fallback';

export function AgentsExperience({ mode }: { mode: 'narrative' | 'workspace' }) {
  const { navigate, setInspector, setInspectorOpen } = useShell();
  const [route, setRoute] = useState<Route>('primary');
  const [activeId, setActiveId] = useState('alpha');
  const [comparedId, setComparedId] = useState<string | null>(null);
  const [policy, setPolicy] = useState<PolicyEvaluationResponse | null>(null);
  const [fallback, setFallback] = useState<FallbackDecisionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (mode !== 'workspace') return;
    let cancelled = false;
    Promise.all([
      systemApi.evaluatePolicy(fixturePolicy),
      systemApi.resolveFallback(fixtureFallback),
    ]).then(([policyResult, fallbackResult]) => {
      if (cancelled) return;
      setPolicy(policyResult);
      setFallback(fallbackResult);
    }).catch((reason: unknown) => {
      if (!cancelled) setError(reason instanceof ApiError ? reason.message : String(reason));
    });
    return () => { cancelled = true; };
  }, [mode]);

  const path = route === 'primary' ? fixturePath : fixtureFallbackPath;
  const nodes = useMemo(() => fixtureGraph.map((node) => mode === 'workspace'
    ? { ...node, onPath: path.includes(node.id) }
    : {
        id: node.id,
        label: node.label,
        role: node.role,
        active: node.active,
        granted: node.granted,
        denied: node.denied,
        fallback: node.fallback,
        onPath: path.includes(node.id),
      }), [mode, path]);

  useEffect(() => {
    if (mode !== 'workspace') return;
    const node = fixtureGraph.find((item) => item.id === activeId) ?? fixtureGraph[0];
    if (!node) return;
    setInspector(
      <ObjectInspector
        kind="Specialist agent"
        title={node.label}
        status={node.active ? 'Available' : 'Idle'}
        capabilities={[
          ...node.granted.map((name) => ({ name, state: 'granted' as const })),
          ...node.denied.map((name) => ({ name, state: 'denied' as const })),
        ]}
        action={<button type="button" className="inspector-action" onClick={() => navigate('record')}>Open research record ›</button>}
        details={(
          <CapabilityInspector
            agent={node.label}
            granted={node.granted}
            denied={node.denied}
            mandatory={node.mandatory}
            optional={node.optional}
            taskScope={node.taskScope}
            leaseStatus={node.leaseStatus}
          />
        )}
      />,
    );
    return () => setInspector(null);
  }, [activeId, mode, navigate, setInspector]);

  const menuFor = (node: { id: string }): MenuItem[] => [
    { id: 'inspect', label: 'Inspect', onSelect: () => { setActiveId(node.id); setInspectorOpen(true); } },
    { id: 'trace', label: 'Open research record', onSelect: () => navigate('record') },
    { id: 'caps', label: 'View capabilities', onSelect: () => { setActiveId(node.id); setInspectorOpen(true); } },
    { id: 'compare', label: 'Compare', onSelect: () => setComparedId(node.id) },
  ];

  return (
    <section className={mode === 'workspace' ? 'experience experience-workspace agents-workspace' : 'experience experience-narrative'} aria-label="Discovery loop orchestration">
      {mode === 'workspace' ? (
        <div className="view-toolbar experience-toolbar">
          <SegmentedControl
            label="Plan"
            value={route}
            options={[{ value: 'primary', label: 'Active plan' }, { value: 'fallback', label: 'Adapted plan' }]}
            onChange={setRoute}
          />
          <SampleMark />
          {fallback?.selected_id ? <StatusBadge tone="ok">adapted via {fallback.selected_id}</StatusBadge> : null}
        </div>
      ) : null}
      {error ? <p className="quiet experience-footnote">Core API offline — showing the labelled sample.</p> : null}
      {mode === 'workspace' ? (
        <AgentGraph
          nodes={nodes}
          selectedPath={path}
          activeId={activeId}
          comparedId={comparedId}
          draw={false}
          onSelect={(id) => { setActiveId(id); setInspectorOpen(true); }}
          menuFor={menuFor}
        />
      ) : (
        <AgentGraph
          nodes={nodes}
          selectedPath={path}
          activeId={activeId}
          comparedId={comparedId}
          draw
          onSelect={setActiveId}
        />
      )}
      {mode === 'workspace' && policy ? (
        <p className="experience-footnote">{policy.allowed ? 'The evidence plan satisfies its mandatory tool policy.' : 'The policy blocked this sample plan.'}</p>
      ) : null}
    </section>
  );
}
