/** Response types mirroring the backend API contract. Keep in sync with
 * `backend/app/api/routes/*` and `backend/app/core/errors.py`. */

export interface HealthStatus {
  status: string;
  version: string;
  time: string;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
}

export interface HeartbeatEvent {
  tick: number;
  time: string;
}

/* --- Capability catalogue ------------------------------------------------ */

/** GET /api/system/capabilities → CapabilitiesResponse */
export interface CapabilityDescriptor {
  name: string;
  description: string | null;
  implies: string[];
}

export interface CapabilitiesResponse {
  capabilities: CapabilityDescriptor[];
}

/* --- Architecture candidates --------------------------------------------- */

/** A candidate multi-agent architecture with multi-objective metrics. */
export interface ArchitectureCandidateApi {
  id: string;
  name: string;
  quality: number;
  cost: number;
  latency: number;
  risk: number;
  metadata: Record<string, unknown> | null;
}

/** GET /api/system/architectures → ArchitecturesResponse */
export interface ArchitecturesResponse {
  architectures: ArchitectureCandidateApi[];
}

/* --- Pareto frontier ----------------------------------------------------- */

export interface ParetoCandidate {
  id: string;
  quality: number;
  cost: number;
  latency: number;
  risk: number;
  metadata: Record<string, unknown> | null;
}

export interface ParetoFrontierRequest {
  candidates: ParetoCandidate[];
}

/** POST /api/system/pareto-frontier → ParetoFrontierResponse */
export interface ParetoFrontierResponse {
  frontier: string[];
  dominated: string[];
}

/* --- Policy evaluation --------------------------------------------------- */

export interface PolicyRequirement {
  capability: string;
  mandatory: boolean;
}

export interface CapabilityLease {
  capability: string;
  allowed: boolean;
  task_scope: string | null;
  /** ISO-8601 timestamp, or null for no expiry. */
  expires_at: string | null;
  max_calls: number | null;
  calls_used: number;
  source: string;
}

export interface EvaluatePolicyRequest {
  capabilities: CapabilityDescriptor[];
  requirements: PolicyRequirement[];
  denied: string[];
  leases: CapabilityLease[];
  task_scope: string | null;
}

/** POST /api/system/evaluate-policy → PolicyEvaluationResponse */
export interface PolicyEvaluationResponse {
  allowed: boolean;
  granted: string[];
  denied: string[];
  missing_mandatory: string[];
  missing_optional: string[];
  reasons: string[];
}

/* --- Fallback resolution ------------------------------------------------- */

export interface FallbackCandidateRequest {
  id: string;
  available: boolean;
  capabilities: string[];
  privacy_class: string;
  allowed_tasks: string[];
}

/** POST /api/system/resolve-fallback */
export interface ResolveFallbackRequest {
  candidates: FallbackCandidateRequest[];
  mandatory_capabilities: string[];
  accepted_privacy_classes: string[];
  task: string;
  preference_order: string[];
  capabilities: CapabilityDescriptor[];
}

export interface FallbackRejection {
  id: string;
  reason: string;
}

export interface FallbackDecisionResponse {
  selected_id: string | null;
  considered: string[];
  rejected: FallbackRejection[];
  reason: string;
}
