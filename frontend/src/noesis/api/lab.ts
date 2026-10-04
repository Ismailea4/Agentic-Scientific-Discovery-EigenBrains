import { api } from './client';
import type { LabActivity, LabExperiment, LabSource, LabState } from './lab-types';

export const LAB_URL_KEY = 'noesis-lab-url';

export const LOCAL_LAB_URL = 'http://127.0.0.1:8765';

/** Build a URL for a lab feed path. Requests go through the app's
 * `/lab-proxy` relay so browsers are not blocked by the feed's missing CORS
 * headers. An empty base targets the feed on this machine. */
export function labUrl(base: string, path: string, params: Record<string, string> = {}): string {
  const search = new URLSearchParams(params);
  search.set('target', base || LOCAL_LAB_URL);
  return `/lab-proxy/${path}?${search.toString()}`;
}

export const labApi = {
  sources: (base: string) => api.get<{ sources: LabSource[] }>(labUrl(base, 'sources')),
  state: (base: string, source: string) => api.get<LabState>(labUrl(base, 'state', { source })),
  activity: (base: string, source: string) => api.get<{ activity: LabActivity[] }>(labUrl(base, 'activity', { source })),
  experiment: (base: string, source: string, id: string) => api.get<LabExperiment>(labUrl(base, 'experiment', { source, id })),
  streamUrl: (base: string, source: string) => labUrl(base, 'stream', { source }),
};
