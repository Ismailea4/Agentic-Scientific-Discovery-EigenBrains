import { useEffect, useMemo, useState } from 'react';
import { systemApi } from '../api/system';
import type { ArchitectureCandidateApi, ParetoFrontierResponse } from '../api/types';
import { FrontierChart, type FrontierCandidate } from '../components/FrontierChart';
import { IconMode, IconPlay } from '../components/icons';
import { ObjectInspector } from '../components/ObjectInspector';
import { Popover, PopoverContent, PopoverTrigger, Tooltip, TooltipContent, TooltipTrigger } from '../components/overlay';
import { SampleMark } from '../components/SampleMark';
import { useShell } from '../components/shell';
import { CostLatencyMetric, SegmentedControl, cx, formatPlain } from '../components/ui';
import { fixtureFrontier } from '../dev/fixtures';
import { useGet } from '../hooks/useGet';

type RunMode = 'fast' | 'balanced' | 'reliability';

const MODES: { value: RunMode; label: string }[] = [
  { value: 'fast', label: 'Fast' },
  { value: 'balanced', label: 'Balanced' },
  { value: 'reliability', label: 'Reliable' },
];

const STEPS = [
  ['Bench', 'Benchmark'], ['Measure', 'Quality, cost, latency, risk'],
  ['Feasible', 'Capability constraint'], ['Pareto', 'Non-dominated set'],
  ['Execute', 'Least privilege'], ['Fallback', 'Only if authorized'], ['Trace', 'Audit record'],
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
        kind="Architecture"
        title={selected.name}
        status={pareto?.frontier.includes(selected.id) ? 'Frontier' : pareto?.dominated.includes(selected.id) ? 'Dominated' : 'Registered'}
        latency={formatPlain(selected.latency)}
        cost={formatPlain(selected.cost)}
        capabilities={(capabilities.data?.capabilities ?? []).map((item) => ({ name: item.name, state: 'neutral' }))}
        details={(
          <div className="inspector-body">
            <CostLatencyMetric cost={formatPlain(selected.cost)} latency={formatPlain(selected.latency)} />
            <dl className="kv">
              <div><dt>Quality</dt><dd>{formatPlain(selected.quality)}</dd></div>
              <div><dt>Risk</dt><dd>{formatPlain(selected.risk)}</dd></div>
              {compared && compared.id !== selected.id ? <div><dt>Δ quality</dt><dd>{formatPlain(selected.quality - compared.quality)}</dd></div> : null}
            </dl>
          </div>
        )}
      />,
    );
    return () => setInspector(null);
  }, [capabilities.data, compared, mode, pareto, selected, setInspector]);

  if (mode === 'narrative') {
    return (
      <section className="experience experience-narrative estimation-narrative" aria-label="Architecture estimation sample">
        <div className="experience-mark"><SampleMark /></div>
        <FrontierChart candidates={points} selectedId="careful" onSelect={() => undefined} reveal />
      </section>
    );
  }

  return (
    <section className="experience experience-workspace estimation-workspace">
      <div className="view-toolbar experience-toolbar">
        <SegmentedControl label="Run mode" value={runMode} options={MODES} onChange={setRunMode} />
        <Tooltip>
          <TooltipTrigger>
            <button type="button" className="btn btn-icon" aria-disabled="true" aria-label="Run" onClick={(event) => event.preventDefault()}><IconPlay /></button>
          </TooltipTrigger>
          <TooltipContent>No task registered</TooltipContent>
        </Tooltip>
        <Popover>
          <PopoverTrigger label="About this mode"><IconMode /></PopoverTrigger>
          <PopoverContent title="Mode"><p className="quiet">Weights stay unset.</p></PopoverContent>
        </Popover>
        {useSample ? <SampleMark /> : null}
      </div>
      {architectures.loading ? <p className="quiet">Loading…</p> : null}
      {architectures.error ? <p className="alert" role="alert">{architectures.error}</p> : null}
      {useSample && architectures.data ? <p className="experience-footnote">No live architectures registered. Showing a hand-written layout sample.</p> : null}
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
      <FrontierChart candidates={points} selectedId={selectedId ?? (useSample ? 'careful' : null)} reveal onSelect={(id) => {
        if (!useSample) { setSelectedId(id); setInspectorOpen(true); }
      }} />
      <ol className="stepper" aria-label="Pipeline">
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
      <span className="node-metrics"><span>q {formatPlain(row.quality)}</span><span>c {formatPlain(row.cost)}</span><span>L {formatPlain(row.latency)}</span></span>
    </button>
  );
}
