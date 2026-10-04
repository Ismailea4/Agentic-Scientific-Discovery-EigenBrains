import { useEffect, useMemo, useState } from 'react';
import { systemApi } from '../api/system';
import type { ArchitectureCandidateApi, ParetoFrontierResponse } from '../api/types';
import { FrontierChart, type FrontierCandidate } from '../components/FrontierChart';
import { IconMode, IconPlay } from '../components/icons';
import { ObjectInspector } from '../components/ObjectInspector';
import { Popover, PopoverContent, PopoverTrigger, Tooltip, TooltipContent, TooltipTrigger } from '../components/overlay';
import { SampleMark } from '../components/SampleMark';
import { useShell } from '../components/shell';
import { SegmentedControl, cx, formatPlain } from '../components/ui';
import { fixtureFrontier } from '../dev/fixtures';
import { useGet } from '../hooks/useGet';

type RunMode = 'fast' | 'balanced' | 'reliability';

const MODES: { value: RunMode; label: string }[] = [
  { value: 'fast', label: 'Fast' },
  { value: 'balanced', label: 'Balanced' },
  { value: 'reliability', label: 'Reliable' },
];

const STEPS = [
  ['Question', 'Research objective'], ['Evidence', 'Cited literature and data'],
  ['Hypothesis', 'Falsifiable mechanism'], ['Experiment', 'Discriminating protocol'],
  ['Result', 'Observed evidence'], ['Decision', 'Updated next action'],
] as const;

export function EstimationExperience({ mode }: { mode: 'narrative' | 'workspace' }) {
  const { setInspector, setInspectorOpen } = useShell();
  const architectures = useGet<Awaited<ReturnType<typeof systemApi.architectures>>>('/api/system/architectures');
  const capabilities = useGet<Awaited<ReturnType<typeof systemApi.capabilities>>>('/api/system/capabilities');
  const [runMode, setRunMode] = useState<RunMode>('balanced');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [compareId, setCompareId] = useState<string | null>(null);
  const [pareto, setPareto] = useState<ParetoFrontierResponse | null>(null);

  const liveRows = architectures.data?.architectures ?? [];
  const useSample = liveRows.length === 0;
  const candidates = useSample ? fixtureFrontier : liveRows;

  useEffect(() => {
    if (!architectures.data && mode === 'workspace') return;
    let cancelled = false;
    systemApi.pareto({ candidates: candidates.map((row) => ({
      id: row.id,
      quality: row.quality,
      cost: row.cost,
      latency: row.latency,
      risk: row.risk,
      metadata: row.metadata,
    })) }).then((result) => {
      if (!cancelled) setPareto(result);
    }).catch(() => {
      if (!cancelled) setPareto(null);
    });
    return () => { cancelled = true; };
  }, [architectures.data, candidates, mode]);

  const points = useMemo<FrontierCandidate[]>(() => candidates.map((row) => ({
    id: row.id,
    label: row.id,
    quality: row.quality,
    cost: row.cost,
    latency: row.latency,
    risk: row.risk,
    dominated: pareto ? pareto.dominated.includes(row.id) : null,
  })), [candidates, pareto]);

  const selected = liveRows.find((row) => row.id === selectedId) ?? null;
  const compared = liveRows.find((row) => row.id === compareId) ?? null;

  useEffect(() => {
    if (mode !== 'workspace' || !selected) return;
    setInspector(
      <ObjectInspector
        kind="Hypothesis"
        title={selected.name}
        status={pareto?.frontier.includes(selected.id) ? 'Priority candidate' : pareto?.dominated.includes(selected.id) ? 'Lower priority' : 'Registered'}
        capabilities={(capabilities.data?.capabilities ?? []).map((item) => ({ name: item.name, state: 'neutral' }))}
        details={(
          <div className="inspector-body">
            <dl className="kv">
              <div><dt>Confidence</dt><dd>{Math.round(selected.quality * 100)}%</dd></div>
              <div><dt>Uncertainty</dt><dd>{formatPlain(selected.risk)}</dd></div>
              <div><dt>Evidence burden</dt><dd>{formatPlain(selected.cost)}</dd></div>
              <div><dt>Experiment horizon</dt><dd>{formatPlain(selected.latency)} days</dd></div>
              {compared && compared.id !== selected.id ? <div><dt>Δ confidence</dt><dd>{Math.round((selected.quality - compared.quality) * 100)} pp</dd></div> : null}
            </dl>
          </div>
        )}
      />,
    );
    return () => setInspector(null);
  }, [capabilities.data, compared, mode, pareto, selected, setInspector]);

  if (mode === 'narrative') {
    return (
      <section className="experience experience-narrative estimation-narrative" aria-label="Hypothesis prioritization sample">
        <div className="experience-mark"><SampleMark /></div>
        <FrontierChart candidates={points} selectedId="entropy-features" onSelect={() => undefined} reveal />
      </section>
    );
  }

  return (
    <section className="experience experience-workspace estimation-workspace">
      <div className="view-toolbar experience-toolbar">
        <SegmentedControl label="Prioritization" value={runMode} options={MODES} onChange={setRunMode} />
        <Tooltip>
          <TooltipTrigger>
            <button type="button" className="btn btn-icon" aria-disabled="true" aria-label="Run" onClick={(event) => event.preventDefault()}><IconPlay /></button>
          </TooltipTrigger>
          <TooltipContent>No experiment is connected yet</TooltipContent>
        </Tooltip>
        <Popover>
          <PopoverTrigger label="About this mode"><IconMode /></PopoverTrigger>
          <PopoverContent title="Prioritization"><p className="quiet">Compare confidence, uncertainty, evidence burden, and experiment horizon.</p></PopoverContent>
        </Popover>
        {useSample ? <SampleMark /> : null}
      </div>
      {architectures.loading ? <p className="quiet">Loading…</p> : null}
      {architectures.error ? <p className="quiet experience-footnote">Core API offline — showing the labelled sample.</p> : null}
      {useSample && architectures.data ? <p className="experience-footnote">No live hypotheses received. Showing a clearly labeled scientific sample.</p> : null}
      {!useSample ? (
        <div className="card-grid">
          {liveRows.map((row) => (
            <ArchitectureButton
              key={row.id}
              row={row}
              selected={selectedId === row.id}
              compared={compareId === row.id}
              marker={pareto?.frontier.includes(row.id) ? 'Frontier' : pareto?.dominated.includes(row.id) ? 'Dominated' : 'Registered'}
              onSelect={() => { setSelectedId(row.id); setInspectorOpen(true); }}
              onCompare={() => setCompareId(row.id)}
            />
          ))}
        </div>
      ) : null}
      <FrontierChart candidates={points} selectedId={selectedId ?? (useSample ? 'entropy-features' : null)} reveal onSelect={(id) => {
        if (!useSample) { setSelectedId(id); setInspectorOpen(true); }
      }} />
      <ol className="stepper" aria-label="Scientific discovery loop">
        {STEPS.map(([label, hint]) => <li key={label}><Tooltip><TooltipTrigger><span className="step" tabIndex={0}>{label}</span></TooltipTrigger><TooltipContent>{hint}</TooltipContent></Tooltip></li>)}
      </ol>
    </section>
  );
}

function ArchitectureButton({ row, selected, compared, marker, onSelect, onCompare }: {
  row: ArchitectureCandidateApi;
  selected: boolean;
  compared: boolean;
  marker: string;
  onSelect: () => void;
  onCompare: () => void;
}) {
  return (
    <button type="button" className={cx('agent-node', selected && 'is-inspected', compared && 'is-compared')} aria-pressed={selected} onClick={onSelect} onDoubleClick={onCompare}>
      <span className="node-status">{marker}</span>
      <span className="node-label">{row.name}</span>
      <span className="node-metrics"><span>{Math.round(row.quality * 100)}% confidence</span><span>U {formatPlain(row.risk)}</span><span>{formatPlain(row.latency)}d</span></span>
    </button>
  );
}
