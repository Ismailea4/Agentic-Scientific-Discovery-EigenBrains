/**
 * DEVELOPMENT ONLY.
 *
 * Hand-written examples for the showcase page. These numbers are not
 * benchmarks, not measurements, and not production defaults. Production
 * views must not import this module.
 */
import type {
  EvaluatePolicyRequest,
  ParetoCandidate,
  ResolveFallbackRequest,
} from '../api/types';
import type { AgentGraphNode } from '../components/AgentGraph';
import type { LeaseStatus } from '../components/CapabilityInspector';

export const DEV_FIXTURE_BANNER =
  'Development fixtures. These figures are hand-written layout examples, not benchmarks.';

export interface ShowcaseAgent extends AgentGraphNode {
  mandatory: string[];
  optional: string[];
  taskScope: string | null;
  leaseStatus: LeaseStatus;
}

export const fixtureGraph: ShowcaseAgent[] = [
  {
    id: 'task',
    label: 'Task',
    role: 'task',
    active: true,
    granted: [],
    denied: [],
    fallback: false,
    onPath: true,
    mandatory: ['read'],
    optional: ['export'],
    taskScope: 'showcase',
    leaseStatus: 'none',
  },
  {
    id: 'router',
    label: 'Router',
    role: 'router',
    active: true,
    granted: ['route'],
    denied: [],
    fallback: false,
    onPath: true,
    mandatory: ['route'],
    optional: [],
    taskScope: 'showcase',
    leaseStatus: 'active',
  },
  {
    id: 'alpha',
    label: 'Agent Alpha',
    role: 'agent',
    active: true,
    granted: ['draft', 'read'],
    denied: ['export'],
    fallback: false,
    onPath: true,
    durationLabel: '18s',
    qualityLabel: '1',
    mandatory: ['read'],
    optional: ['export'],
    taskScope: 'showcase',
    leaseStatus: 'active',
  },
  {
    id: 'beta',
    label: 'Agent Beta',
    role: 'agent',
    active: false,
    granted: [],
    denied: ['write'],
    fallback: true,
    onPath: false,
    mandatory: ['read'],
    optional: [],
    taskScope: 'showcase',
    leaseStatus: 'inactive',
  },
  {
    id: 'verifier',
    label: 'Verifier',
    role: 'verifier',
    active: true,
    granted: ['verify'],
    denied: [],
    fallback: false,
    onPath: true,
    mandatory: ['verify'],
    optional: [],
    taskScope: 'showcase',
    leaseStatus: 'active',
  },
];

export const fixturePath = ['task', 'router', 'alpha', 'verifier'];
export const fixtureFallbackPath = ['task', 'router', 'beta', 'verifier'];

export const fixtureExecution = {
  task: 'Fixture task',
  architecture: 'careful',
  agent: 'Agent Alpha',
  model: 'unspecified',
  quality: '1',
  risk: '0.125',
};

export const fixtureFrontier: ParetoCandidate[] = [
  { id: 'lean', quality: 0.5, cost: 1, latency: 10, risk: 0.25, metadata: { source: 'development-fixture' } },
  { id: 'careful', quality: 1, cost: 2, latency: 20, risk: 0.125, metadata: { source: 'development-fixture' } },
  { id: 'heavy', quality: 0.75, cost: 4, latency: 40, risk: 0.5, metadata: { source: 'development-fixture' } },
];

export const fixturePolicy: EvaluatePolicyRequest = {
  capabilities: [
    { name: 'read', description: 'Read a supplied artifact', implies: [] },
    { name: 'draft', description: 'Draft from something already read', implies: ['read'] },
    { name: 'export', description: 'Send work outside the task', implies: [] },
  ],
  requirements: [
    { capability: 'read', mandatory: true },
    { capability: 'export', mandatory: false },
  ],
  denied: ['export'],
  leases: [
    {
      capability: 'draft',
      allowed: true,
      task_scope: 'showcase',
      expires_at: null,
      max_calls: null,
      calls_used: 0,
      source: 'development-fixture',
    },
  ],
  task_scope: 'showcase',
};

export const fixtureFallback: ResolveFallbackRequest = {
  candidates: [
    {
      id: 'primary',
      available: false,
      capabilities: ['read'],
      privacy_class: 'restricted',
      allowed_tasks: ['showcase'],
    },
    {
      id: 'open-model',
      available: true,
      capabilities: ['draft'],
      privacy_class: 'public',
      allowed_tasks: ['showcase'],
    },
    {
      id: 'local',
      available: true,
      capabilities: ['read'],
      privacy_class: 'restricted',
      allowed_tasks: ['showcase'],
    },
  ],
  mandatory_capabilities: ['read'],
  accepted_privacy_classes: ['restricted'],
  task: 'showcase',
  preference_order: ['primary', 'local', 'open-model'],
  capabilities: [{ name: 'draft', description: null, implies: ['read'] }],
};
