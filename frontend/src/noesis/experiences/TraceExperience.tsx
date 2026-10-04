import { useEffect, useRef, useState } from 'react';
import { systemApi } from '../api/system';
import { subscribeSSE } from '../api/sse';
import type { FallbackDecisionResponse, HeartbeatEvent } from '../api/types';
import { IconPlay, IconStop } from '../components/icons';
import { ObjectInspector } from '../components/ObjectInspector';
import { Tooltip, TooltipContent, TooltipTrigger } from '../components/overlay';
import { AgentResult, AgentRun, CriticFinding, ExecutionSummary, ResultStack, VerificationResult } from '../components/results';
import { SampleMark } from '../components/SampleMark';
import { ScientificText } from '../components/ScientificText';
import { useShell } from '../components/shell';
import { EmptyState, GlassButton, SegmentedControl } from '../components/ui';
import { fixtureExecution, fixtureFallback } from '../dev/fixtures';

type TracePane = 'sample' | 'live';

export function TraceExperience({ mode }: { mode: 'narrative' | 'workspace' }) {
  const { setInspector, setInspectorOpen } = useShell();
  const [pane, setPane] = useState<TracePane>('sample');
  const [fallback, setFallback] = useState<FallbackDecisionResponse | null>(null);
  const [events, setEvents] = useState<HeartbeatEvent[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [failed, setFailed] = useState(false);
  const [selected, setSelected] = useState<HeartbeatEvent | null>(null);
  const unsubscribeRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (mode !== 'workspace') return;
    let cancelled = false;
    systemApi.resolveFallback(fixtureFallback).then((result) => {
      if (!cancelled) setFallback(result);
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [mode]);

  useEffect(() => () => unsubscribeRef.current?.(), []);

  useEffect(() => {
    if (mode !== 'workspace' || !selected) return;
    setInspector(
      <ObjectInspector kind="Research event" title={`Live event ${selected.tick}`} status="Observed" details={<p className="mono">Recorded at {selected.time}</p>} />,
    );
    return () => setInspector(null);
  }, [mode, selected, setInspector]);

  const stopStream = () => {
    unsubscribeRef.current?.();
    unsubscribeRef.current = null;
    setStreaming(false);
  };

  const startStream = () => {
    unsubscribeRef.current?.();
    setEvents([]);
    setSelected(null);
    setFailed(false);
    setStreaming(true);
    unsubscribeRef.current = subscribeSSE('/api/stream/heartbeat', {
      events: ['heartbeat'],
      onEvent: (_name, data) => setEvents((current) => [...current.slice(-49), data as HeartbeatEvent]),
      onError: () => { setFailed(true); stopStream(); },
    });
  };

  if (mode === 'narrative') {
    return (
      <section className="experience experience-narrative trace-narrative" aria-label="Research record sample">
        <div className="experience-mark"><SampleMark /></div>
        <div className="trace-chain">
          <TraceStep label="Question" detail="mechanism registered" />
          <span className="trace-link" aria-hidden="true" />
          <TraceStep label="Evidence" detail="literature synthesized" />
          <span className="trace-link" aria-hidden="true" />
          <TraceStep label="Hypothesis" detail="candidate proposed" />
          <span className="trace-link" aria-hidden="true" />
          <TraceStep label="Experiment" detail="approval required" rejected />
          <span className="trace-link is-stopped" aria-hidden="true"><i /></span>
          <div className="trace-result is-withheld"><span>Decision</span><strong>Paused</strong></div>
        </div>
      </section>
    );
  }

  return (
    <section className="experience experience-workspace trace-workspace">
      <div className="view-toolbar experience-toolbar">
        <SegmentedControl label="Record source" value={pane} options={[{ value: 'sample', label: 'Sample' }, { value: 'live', label: 'Live' }]} onChange={(next) => { stopStream(); setPane(next); }} />
        {pane === 'sample' ? <SampleMark /> : null}
        {pane === 'live' ? (
          <Tooltip>
            <TooltipTrigger>
              {streaming ? <GlassButton type="button" variant="icon" aria-label="Stop" onClick={stopStream}><IconStop /></GlassButton> : <GlassButton type="button" variant="icon" aria-label="Start" onClick={startStream}><IconPlay /></GlassButton>}
            </TooltipTrigger>
            <TooltipContent>{streaming ? 'Stop live record' : 'Listen for live research events'}</TooltipContent>
          </Tooltip>
        ) : null}
      </div>
      {pane === 'sample' ? (
        <ResultStack>
          <ExecutionSummary task={fixtureExecution.task} architecture={fixtureExecution.architecture} agents={[fixtureExecution.agent, 'Experiment designer', 'Scientific Critic']} quality={fixtureExecution.quality} risk={fixtureExecution.risk} />
          <AgentRun agent={fixtureExecution.agent} model={fixtureExecution.model} status="complete" duration="18s" />
          <article className="research-entry"><p className="eyebrow">Evidence · SAMPLE</p><strong>Evolutionary computation literature synthesis</strong><p>Population entropy has been used as a direct indicator of diversity and convergence, and to adapt mutation rates so a genetic algorithm avoids premature convergence.</p><cite>[1] An adaptive genetic algorithm based on information entropy (2007). OpenAlex W2387338990</cite></article>
           <article className="research-entry"><p className="eyebrow">Hypothesis · SAMPLE</p><strong><ScientificText>H_1: Adding population-entropy features to fitness-history features improves out-of-sample AUROC for predicting stagnation onset.</ScientificText></strong><p>Entropy should fall before fitness plateaus, giving an earlier warning.</p><p className="stat-line"><span>Prior probability</span><span className="math-expression">Pr(<i>H</i><sub>1</sub>) = 0.50</span></p><p className="stat-line"><span>Smallest effect of interest</span><span className="math-expression">ΔAUROC = 0.01</span></p></article>
          <AgentResult title="Experiment protocol" body="Run the GA on shifted Rastrigin and Ackley landscapes with common random numbers; compare leave-one-landscape-out AUROC for fitness-only vs fitness+entropy features with a run-clustered bootstrap." />
          <CriticFinding severity="warn" label="Development-stage landscapes were also used to design the features, so the estimate is likely optimistic until held-out landscapes are tested." />
          <VerificationResult passed label="Hypothesis is pre-registered, falsifiable and tied to a reproducible AUROC contrast" />
          <article className="research-entry decision"><p className="eyebrow">Updated decision · SAMPLE</p><strong>Test whether entropy adds beyond genotypic dispersion before building a controller.</strong><p>Confirmatory runs on held-out landscapes require researcher approval.</p></article>
          {fallback ? <p className="experience-footnote">Adapted plan: {fallback.selected_id ?? 'none'} · {fallback.reason}</p> : null}
        </ResultStack>
      ) : (
        <div className="live-trace">
          {failed ? <p className="quiet" role="status">Stream closed.</p> : null}
          {events.length === 0 && !streaming ? <EmptyState title="Idle" body="Start to listen." mark="⌁" /> : null}
          {streaming && events.length === 0 ? <p className="quiet">Waiting…</p> : null}
          <ul className="event-list">
            {events.map((event) => (
              <li key={`${event.tick}-${event.time}`}><button type="button" className={selected?.tick === event.tick ? 'is-selected' : undefined} onClick={() => { setSelected(event); setInspectorOpen(true); }}><span>tick {event.tick}</span><span className="quiet">{event.time}</span></button></li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function TraceStep({ label, detail, rejected = false }: { label: string; detail: string; rejected?: boolean }) {
  return (
    <div className={rejected ? 'trace-step is-rejected' : 'trace-step'}>
      <span className="trace-state" aria-hidden="true" />
      <span><strong>{label}</strong><small>{detail}</small></span>
    </div>
  );
}
