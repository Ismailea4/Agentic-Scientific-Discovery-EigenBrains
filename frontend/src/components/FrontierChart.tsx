import { useId, useState, type CSSProperties } from 'react';
import { SegmentedControl } from './ui';

export interface FrontierCandidate {
  id: string;
  label: string;
  quality: number;
  cost: number;
  latency: number;
  risk: number;
  /** null while the server has not classified the point. */
  dominated: boolean | null;
}

type Axis = 'cost' | 'latency' | 'risk';

const AXES: { value: Axis; label: string }[] = [
  { value: 'cost', label: 'Cost' },
  { value: 'latency', label: 'Latency' },
  { value: 'risk', label: 'Risk' },
];

const WIDTH = 640;
const HEIGHT = 360;
const PAD = { left: 52, right: 20, top: 28, bottom: 42 };

function domain(values: number[]): [number, number] {
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) {
    const pad = Math.abs(min) * 0.15 || 1;
    return [min - pad, max + pad];
  }
  const pad = (max - min) * 0.12;
  return [min - pad, max + pad];
}

function ticks(min: number, max: number): number[] {
  return [0, 1, 2, 3].map((step) => min + ((max - min) * step) / 3);
}

function formatTick(value: number): string {
  if (Math.abs(value) >= 100) return value.toFixed(0);
  if (Math.abs(value) >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

export function FrontierChart({
  candidates,
  selectedId,
  onSelect,
  note,
  reveal = false,
}: {
  candidates: FrontierCandidate[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  note?: string;
  reveal?: boolean;
}) {
  const [axis, setAxis] = useState<Axis>('cost');
  const titleId = useId();
  const plotW = WIDTH - PAD.left - PAD.right;
  const plotH = HEIGHT - PAD.top - PAD.bottom;

  if (candidates.length === 0) {
    return <p className="quiet">No candidates to plot.</p>;
  }

  const xs = candidates.map((candidate) => candidate[axis]);
  const ys = candidates.map((candidate) => candidate.quality);
  const [xMin, xMax] = domain(xs);
  const [yMin, yMax] = domain(ys);
  const xOf = (value: number) => PAD.left + ((value - xMin) / (xMax - xMin)) * plotW;
  const yOf = (value: number) => PAD.top + (1 - (value - yMin) / (yMax - yMin)) * plotH;
  const frontier = candidates
    .filter((candidate) => candidate.dominated === false)
    .slice()
    .sort((left, right) => left[axis] - right[axis]);
  const line =
    frontier.length > 1
      ? frontier
          .map((candidate, index) => {
            const command = index === 0 ? 'M' : 'L';
            return `${command} ${xOf(candidate[axis])} ${yOf(candidate.quality)}`;
          })
          .join(' ')
      : '';

  return (
    <div className={reveal ? 'chart-wrap is-revealing' : 'chart-wrap'}>
      <SegmentedControl label="Frontier axis" value={axis} options={AXES} onChange={setAxis} />
      <svg key={axis} role="img" aria-labelledby={titleId} viewBox={`0 0 ${WIDTH} ${HEIGHT}`}>
        <title id={titleId}>Quality versus {axis}. Higher quality is up. Lower {axis} is left.</title>
        {ticks(yMin, yMax).map((tick) => (
          <g className="chart-grid-line" key={`y-${tick}`}>
            <line className="grid" x1={PAD.left} x2={WIDTH - PAD.right} y1={yOf(tick)} y2={yOf(tick)} />
            <text className="axis" x={PAD.left - 8} y={yOf(tick) + 4} textAnchor="end">
              {formatTick(tick)}
            </text>
          </g>
        ))}
        {ticks(xMin, xMax).map((tick) => (
          <text key={`x-${tick}`} className="axis chart-axis-tick" x={xOf(tick)} y={HEIGHT - 16} textAnchor="middle">
            {formatTick(tick)}
          </text>
        ))}
        <text className="axis chart-axis-label" x={PAD.left} y={12}>
          Quality
        </text>
        <text className="axis chart-axis-label" x={WIDTH - PAD.right} y={HEIGHT - 4} textAnchor="end">
          {AXES.find((item) => item.value === axis)?.label}
        </text>
        {line && <path className="frontier-line" d={line} pathLength={1} />}
        {candidates.map((candidate, index) => {
          const selected = candidate.id === selectedId;
          const kind =
            candidate.dominated === null ? 'point-unknown' : candidate.dominated ? 'point-dominated' : 'point-frontier';
          return (
            <g
              key={candidate.id}
              role="button"
              tabIndex={0}
              aria-label={`${candidate.label}, ${candidate.dominated === null ? 'unclassified' : candidate.dominated ? 'dominated' : 'non-dominated'}`}
              aria-pressed={selected}
              className="chart-point"
              style={{ ['--point-index' as string]: index } as CSSProperties}
              onClick={() => onSelect(candidate.id)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelect(candidate.id);
                }
              }}
            >
              {selected ? <circle className="point-halo" cx={xOf(candidate[axis])} cy={yOf(candidate.quality)} r="13" /> : null}
              <circle
                className={cxPoint(kind, selected)}
                cx={xOf(candidate[axis])}
                cy={yOf(candidate.quality)}
                r={selected ? 7 : 5}
              />
              <text className="point-label" x={xOf(candidate[axis]) + 10} y={yOf(candidate.quality) - 8}>
                {candidate.label}
              </text>
            </g>
          );
        })}
      </svg>
      {note && <p className="quiet">{note}</p>}
      <div className="legend">
        <span><i className="swatch" /> Non-dominated</span>
        <span><i className="swatch hollow" /> Dominated</span>
        <span><i className="swatch dashed" /> Unclassified</span>
      </div>
    </div>
  );
}

function cxPoint(kind: string, selected: boolean): string {
  return selected ? `${kind} point-selected` : kind;
}
