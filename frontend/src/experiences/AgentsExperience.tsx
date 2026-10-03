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
  const nodes = useMemo(() => fixtureGraph.map((node) => ({
    ...node,
    onPath: path.includes(node.id),
    durationLabel: mode === 'workspace' ? node.durationLabel : undefined,
    costLabel: mode === 'workspace' ? node.costLabel : undefined,
    qualityLabel: mode === 'workspace' ? node.qualityLabel : undefined,
  })), [mode, path]);

  useEffect(() => {
    if (mode !== 'workspace') return;
    const node = fixtureGraph.find((item) => item.id === activeId) ?? fixtureGraph[0];
    setInspector(
      <ObjectInspector
        kind="Agent"
        title={node.label}
        status={node.active ? 'Available' : 'Idle'}
        capabilities={[
          ...node.granted.map((name) => ({ name, state: 'granted' as const })),
          ...node.denied.map((name) => ({ name, state: 'denied' as const })),
        ]}
        action={<button type="button" className="inspector-action" onClick={() => navigate('trace')}>View full trace ›</button>}
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
    { id: 'trace', label: 'View trace', onSelect: () => navigate('trace') },
    { id: 'caps', label: 'View capabilities', onSelect: () => { setActiveId(node.id); setInspectorOpen(true); } },
    { id: 'compare', label: 'Compare', onSelect: () => setComparedId(node.id) },
  ];

  return (
    <section className={mode === 'workspace' ? 'experience experience-workspace agents-workspace' : 'experience experience-narrative'} aria-label="Agent architecture">
      {mode === 'workspace' ? (
        <div className="view-toolbar experience-toolbar">
          <SegmentedControl
            label="Route"
            value={route}
            options={[{ value: 'primary', label: 'Primary' }, { value: 'fallback', label: 'Fallback' }]}
            onChange={setRoute}
          />
          <SampleMark />
          {fallback?.selected_id ? <StatusBadge tone="ok">fallback {fallback.selected_id}</StatusBadge> : null}
        </div>
      ) : null}
      {error ? <p className="alert" role="alert">{error}</p> : null}
      <AgentGraph
        nodes={nodes}
        selectedPath={path}
        activeId={activeId}
        comparedId={comparedId}
        draw={mode === 'narrative'}
        onSelect={(id) => {
          setActiveId(id);
          if (mode === 'workspace') setInspectorOpen(true);
        }}
        menuFor={mode === 'workspace' ? menuFor : undefined}
      />
      {mode === 'workspace' && policy ? (
        <p className="experience-footnote">{policy.allowed ? 'Mandatory capability set is allowed.' : 'The policy blocked this sample.'}</p>
      ) : null}
    </section>
  );
}
