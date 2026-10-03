import { useEffect, useRef, useState } from 'react';
import { systemApi } from '../api/system';
import { subscribeSSE } from '../api/sse';
import type { FallbackDecisionResponse, HeartbeatEvent } from '../api/types';
import { IconPlay, IconStop } from '../components/icons';
import { ObjectInspector } from '../components/ObjectInspector';
import { Tooltip, TooltipContent, TooltipTrigger } from '../components/overlay';
import { AgentResult, AgentRun, CriticFinding, ExecutionSummary, ResultStack, VerificationResult } from '../components/results';
import { SampleMark } from '../components/SampleMark';
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
      <ObjectInspector kind="Trace event" title={`Heartbeat ${selected.tick}`} status="Observed" details={<p className="mono">{selected.time}</p>} />,
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
      <section className="experience experience-narrative trace-narrative" aria-label="Execution trace sample">
        <div className="experience-mark"><SampleMark /></div>
        <div className="trace-chain">
          <TraceStep label="Task" detail="registered input" />
          <span className="trace-link" aria-hidden="true" />
          <TraceStep label="Architecture" detail="policy selected" />
          <span className="trace-link" aria-hidden="true" />
          <TraceStep label="Agents" detail="least privilege" />
          <span className="trace-link" aria-hidden="true" />
          <TraceStep label="Verification" detail="constraint failed" rejected />
          <span className="trace-link is-stopped" aria-hidden="true"><i /></span>
          <div className="trace-result is-withheld"><span>Result</span><strong>Withheld</strong></div>
        </div>
      </section>
    );
  }

  return (
    <section className="experience experience-workspace trace-workspace">
      <div className="view-toolbar experience-toolbar">
        <SegmentedControl label="Trace source" value={pane} options={[{ value: 'sample', label: 'Sample' }, { value: 'live', label: 'Live' }]} onChange={(next) => { stopStream(); setPane(next); }} />
        {pane === 'sample' ? <SampleMark /> : null}
        {pane === 'live' ? (
          <Tooltip>
            <TooltipTrigger>
              {streaming ? <GlassButton type="button" variant="icon" aria-label="Stop" onClick={stopStream}><IconStop /></GlassButton> : <GlassButton type="button" variant="icon" aria-label="Start" onClick={startStream}><IconPlay /></GlassButton>}
            </TooltipTrigger>
            <TooltipContent>{streaming ? 'Stop heartbeat' : 'Listen · /api/stream/heartbeat'}</TooltipContent>
          </Tooltip>
        ) : null}
      </div>
      {pane === 'sample' ? (
        <ResultStack>
          <ExecutionSummary task={fixtureExecution.task} architecture={fixtureExecution.architecture} agents={[fixtureExecution.agent, 'Verifier']} quality={fixtureExecution.quality} risk={fixtureExecution.risk} />
          <AgentRun agent={fixtureExecution.agent} model={fixtureExecution.model} status="complete" duration="18s" />
          <AgentResult title="Fixture output" body="Hand-written layout sample. Not a model response." />
          <CriticFinding severity="note" label="Optional export is absent." />
          <VerificationResult passed label="Mandatory read holds" />
          {fallback ? <p className="experience-footnote">Fallback: {fallback.selected_id ?? 'none'} · {fallback.reason}</p> : null}
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
