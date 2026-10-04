import { Fragment, type ReactNode } from 'react';

const SUBSCRIPTED_SYMBOL = /\b([A-Za-z])_\{?([A-Za-z0-9*+−-]+)\}?/g;

export function ScientificText({ children }: { children: string }) {
  const parts: ReactNode[] = [];
  let cursor = 0;

  for (const match of children.matchAll(SUBSCRIPTED_SYMBOL)) {
    const index = match.index;
    if (index == null) continue;
    if (index > cursor) parts.push(children.slice(cursor, index));
    parts.push(
      <span className="math-symbol" key={`${index}-${match[0]}`}>
        <i>{match[1]}</i><sub>{match[2]}</sub>
      </span>,
    );
    cursor = index + match[0].length;
  }
  if (cursor < children.length) parts.push(children.slice(cursor));

  return <>{parts.map((part, index) => <Fragment key={index}>{part}</Fragment>)}</>;
}

export function HypothesisSymbol({ id }: { id: string }) {
  const match = /^H(\d+)$/.exec(id);
  if (!match) return <span className="math-symbol">{id}</span>;
  return <span className="math-symbol"><i>H</i><sub>{match[1]}</sub></span>;
}

export function PosteriorProbability({ id, value }: { id: string; value: number }) {
  return (
    <span className="math-expression" aria-label={`Posterior probability of ${id} given the observed data: ${value.toFixed(3)}`}>
      Pr(<HypothesisSymbol id={id} /> | <i>D</i>) = {value.toFixed(3)}
    </span>
  );
}