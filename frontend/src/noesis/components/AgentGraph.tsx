import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import { CapabilityBadge, cx } from './ui';
import { ContextMenu, type MenuItem } from './overlay';
import { Tooltip, TooltipContent, TooltipTrigger } from './overlay';

export type AgentRole = 'task' | 'router' | 'agent' | 'verifier';

export interface AgentGraphNode {
  id: string;
  label: string;
  role: AgentRole;
  active: boolean;
  granted: string[];
  denied: string[];
  fallback: boolean;
  onPath: boolean;
  durationLabel?: string;
  costLabel?: string;
  qualityLabel?: string;
}

const ROLE_ORDER: AgentRole[] = ['task', 'router', 'agent', 'verifier'];
const ROLE_LABEL: Record<AgentRole, string> = {
  task: 'Question',
  router: 'Orchestrator',
  agent: 'Specialists',
  verifier: 'Validation',
};

interface Edge {
  d: string;
  to: string;
}

function curve(from: DOMRect, to: DOMRect, origin: DOMRect): string {
  const round = (value: number) => Math.round(value * 10) / 10;
  const fromCenter = from.left + from.width / 2;
  const toCenter = to.left + to.width / 2;
  const sameColumn = Math.abs(fromCenter - toCenter) < Math.min(from.width, to.width) * 0.45;

  if (sameColumn && to.top >= from.bottom) {
    const x1 = round(fromCenter - origin.left);
    const y1 = round(from.bottom - origin.top);
    const x2 = round(toCenter - origin.left);
    const y2 = round(to.top - origin.top);
    const handle = round(Math.max(18, (y2 - y1) * 0.5));
    return `M ${x1} ${y1} C ${x1} ${round(y1 + handle)}, ${x2} ${round(y2 - handle)}, ${x2} ${y2}`;
  }

  const movesRight = toCenter >= fromCenter;
  const x1 = round((movesRight ? from.right : from.left) - origin.left);
  const y1 = round(from.top - origin.top + from.height / 2);
  const x2 = round((movesRight ? to.left : to.right) - origin.left);
  const y2 = round(to.top - origin.top + to.height / 2);
  const handle = round(Math.max(24, Math.abs(x2 - x1) * 0.48));
  return `M ${x1} ${y1} C ${round(x1 + (movesRight ? handle : -handle))} ${y1}, ${round(x2 - (movesRight ? handle : -handle))} ${y2}, ${x2} ${y2}`;
}

export function AgentGraph({
  nodes,
  selectedPath,
  activeId,
  comparedId,
  onSelect,
  menuFor,
  draw = false,
}: {
  nodes: AgentGraphNode[];
  selectedPath: string[];
  activeId: string | null;
  comparedId?: string | null;
  onSelect: (id: string) => void;
  menuFor?: (node: AgentGraphNode) => MenuItem[];
  draw?: boolean;
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const nodeRefs = useRef(new Map<string, HTMLButtonElement>());
  const [edges, setEdges] = useState<Edge[]>([]);
  const [menu, setMenu] = useState<{ x: number; y: number; items: MenuItem[] } | null>(null);
  const closeMenu = useCallback(() => setMenu(null), []);
  const columns = ROLE_ORDER.map((role) => nodes.filter((node) => node.role === role)).filter(
    (column) => column.length > 0,
  );

  useLayoutEffect(() => {
    const frame = frameRef.current;
    if (!frame) return;

    const measure = () => {
      const origin = frame.getBoundingClientRect();
      const next: Edge[] = [];
      for (let index = 0; index < selectedPath.length - 1; index += 1) {
        const fromId = selectedPath[index];
        const toId = selectedPath[index + 1];
        if (!fromId || !toId) continue;
        const from = nodeRefs.current.get(fromId);
        const to = nodeRefs.current.get(toId);
        if (!from || !to) continue;
        next.push({
          d: curve(from.getBoundingClientRect(), to.getBoundingClientRect(), origin),
          to: toId,
        });
      }
      setEdges(next);
    };

    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(frame);
    return () => observer.disconnect();
  }, [nodes, selectedPath]);

  return (
    <div
      className="graph-frame"
      ref={frameRef}
      role="group"
      aria-label="Omnigent discovery orchestration"
      style={{ ['--cols' as string]: columns.length }}
    >
      <svg className="graph-edges" aria-hidden="true">
        {edges.map((edge) => {
          const target = nodes.find((node) => node.id === edge.to);
          const flowing = target?.active && edge.to === activeId;
          return <path key={`${edge.to}-${edge.d}`} d={edge.d} pathLength={draw ? 1 : undefined} className={cx(flowing && 'is-flow', target?.fallback && 'is-fallback-edge', draw && 'is-draw')} />;
        })}
      </svg>
      <div className="graph-columns">
        {columns.map((column) => {
          const firstNode = column[0];
          if (!firstNode) return null;
          return (
          <div className="graph-column" key={firstNode.role}>
            <p className="eyebrow">{ROLE_LABEL[firstNode.role]}</p>
            {column.map((node) => (
              <Tooltip key={node.id}>
                <TooltipTrigger>
                  <button
                    type="button"
                    ref={(element) => {
                      if (element) nodeRefs.current.set(node.id, element);
                      else nodeRefs.current.delete(node.id);
                    }}
                    className={cx(
                      'agent-node',
                      node.onPath && 'is-on-path',
                      node.fallback && 'is-fallback',
                      !node.active && 'is-inactive',
                      node.denied.length > 0 && 'is-denied',
                      activeId === node.id && 'is-inspected',
                      activeId === node.id && node.active && 'is-live',
                      comparedId === node.id && 'is-compared',
                    )}
                    aria-pressed={activeId === node.id}
                    onClick={() => onSelect(node.id)}
                    onContextMenu={(event) => {
                      if (!menuFor) return;
                      event.preventDefault();
                      setMenu({ x: event.clientX, y: event.clientY, items: menuFor(node) });
                    }}
                  >
                    <span className="node-status">
                      <i className="live-dot" aria-hidden="true" />
                      {node.fallback ? 'Alternate' : node.active ? 'Active' : 'Idle'}
                    </span>
                    <span className="node-label">{node.label}</span>
                    {(node.durationLabel || node.costLabel || node.qualityLabel) && (
                      <span className="node-metrics">
                        {node.durationLabel && <span>{node.durationLabel}</span>}
                        {node.costLabel && <span>{node.costLabel}</span>}
                        {node.qualityLabel && <span>q {node.qualityLabel}</span>}
                      </span>
                    )}
                    <span className="node-badges">
                      {node.granted.slice(0, 2).map((name) => (
                        <CapabilityBadge key={name} name={name} state="granted" />
                      ))}
                      {node.denied.slice(0, 1).map((name) => (
                        <CapabilityBadge key={name} name={name} state="denied" />
                      ))}
                    </span>
                  </button>
                </TooltipTrigger>
                <TooltipContent>{node.label} · {ROLE_LABEL[node.role]}</TooltipContent>
              </Tooltip>
            ))}
          </div>
        );})}
      </div>
      <ContextMenu point={menu} items={menu?.items ?? []} onClose={closeMenu} />
    </div>
  );
}
