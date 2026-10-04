import { api } from './client';
import type {
  ArchitecturesResponse,
  CapabilitiesResponse,
  EvaluatePolicyRequest,
  ParetoFrontierRequest,
  ParetoFrontierResponse,
  PolicyEvaluationResponse,
  ResolveFallbackRequest,
  FallbackDecisionResponse,
} from './types';

/** Typed calls for the generic system routes. Payloads are caller-supplied. */
export const systemApi = {
  capabilities(): Promise<CapabilitiesResponse> {
    return api.get('/api/system/capabilities');
  },
  architectures(): Promise<ArchitecturesResponse> {
    return api.get('/api/system/architectures');
  },
  pareto(body: ParetoFrontierRequest): Promise<ParetoFrontierResponse> {
    return api.post('/api/system/pareto-frontier', body);
  },
  evaluatePolicy(body: EvaluatePolicyRequest): Promise<PolicyEvaluationResponse> {
    return api.post('/api/system/evaluate-policy', body);
  },
  resolveFallback(body: ResolveFallbackRequest): Promise<FallbackDecisionResponse> {
    return api.post('/api/system/resolve-fallback', body);
  },
};
