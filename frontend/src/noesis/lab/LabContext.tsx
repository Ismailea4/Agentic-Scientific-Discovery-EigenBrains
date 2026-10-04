import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ApiError } from '../api/client';
import { LAB_URL_KEY, labApi } from '../api/lab';
import type { LabActivity, LabSource, LabState, LedgerEvent } from '../api/lab-types';
import { subscribeSSE } from '../api/sse';

export type LabStatus = 'checking' | 'connected' | 'offline';

export interface LabContextValue {
  baseUrl: string;
  setBaseUrl: (url: string) => void;
  status: LabStatus;
  error: string | null;
  sources: LabSource[];
  sourceId: string | null;
  setSourceId: (id: string | null) => void;
  source: LabSource | null;
  state: LabState | null;
  activity: LabActivity[];
  ledger: LedgerEvent[];
  streaming: boolean;
  refresh: () => void;
}

const LabContext = createContext<LabContextValue | null>(null);

const message = (reason: unknown) => (reason instanceof ApiError ? reason.message : String(reason));

export function LabProvider({ children }: { children: ReactNode }) {
  const [baseUrl, setBaseUrlState] = useState('');
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState<LabStatus>('checking');
  const [error, setError] = useState<string | null>(null);
  const [sources, setSources] = useState<LabSource[]>([]);
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [state, setState] = useState<LabState | null>(null);
  const [activity, setActivity] = useState<LabActivity[]>([]);
  const [ledger, setLedger] = useState<LedgerEvent[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [tick, setTick] = useState(0);
  const refetchTimer = useRef<number | null>(null);

  useEffect(() => {
    setBaseUrlState(window.localStorage.getItem(LAB_URL_KEY) ?? (import.meta.env['VITE_LAB_URL'] as string | undefined) ?? '');
    setReady(true);
  }, []);

  const setBaseUrl = useCallback((url: string) => {
    const clean = url.trim().replace(/\/$/, '');
    window.localStorage.setItem(LAB_URL_KEY, clean);
    setBaseUrlState(clean);
    setSourceId(null);
  }, []);

  // Discover sources.
  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    setStatus('checking');
    labApi.sources(baseUrl).then((res) => {
      if (cancelled) return;
      const list = Array.isArray(res?.sources) ? res.sources : [];
      setSources(list);
      setStatus('connected');
      setError(null);
      setSourceId((current) => current && list.some((s) => s.id === current)
        ? current
        : (list.find((s) => s.kind === 'live') ?? list[list.length - 1])?.id ?? null);
    }).catch((reason: unknown) => {
      if (cancelled) return;
      setStatus('offline');
      setSources([]);
      setSourceId(null);
      setError(message(reason));
    });
    return () => { cancelled = true; };
  }, [baseUrl, ready, tick]);

  const load = useCallback((id: string) => {
    Promise.all([labApi.state(baseUrl, id), labApi.activity(baseUrl, id)]).then(([s, a]) => {
      setState(s);
      setActivity(a.activity ?? []);
      setError(null);
    }).catch((reason: unknown) => setError(message(reason)));
  }, [baseUrl]);

  // Load the selected source and follow its stream.
  useEffect(() => {
    setState(null);
    setActivity([]);
    setLedger([]);
    if (!sourceId || status !== 'connected') return;
    load(sourceId);
    setStreaming(true);
    const unsubscribe = subscribeSSE(labApi.streamUrl(baseUrl, sourceId), {
      events: ['ledger', 'agent', 'heartbeat'],
      onEvent: (name, data) => {
        if (name === 'agent') setActivity((current) => [...current, data as LabActivity]);
        if (name === 'ledger') {
          setLedger((current) => [...current.slice(-199), data as LedgerEvent]);
          if (refetchTimer.current) window.clearTimeout(refetchTimer.current);
          refetchTimer.current = window.setTimeout(() => load(sourceId), 400);
        }
      },
      onError: () => setStreaming(false),
    });
    return () => {
      unsubscribe();
      setStreaming(false);
      if (refetchTimer.current) window.clearTimeout(refetchTimer.current);
    };
  }, [baseUrl, load, sourceId, status]);

  const value = useMemo<LabContextValue>(() => ({
    baseUrl,
    setBaseUrl,
    status,
    error,
    sources,
    sourceId,
    setSourceId,
    source: sources.find((s) => s.id === sourceId) ?? null,
    state,
    activity,
    ledger,
    streaming,
    refresh: () => setTick((n) => n + 1),
  }), [activity, baseUrl, error, ledger, setBaseUrl, sourceId, sources, state, status, streaming]);

  return <LabContext.Provider value={value}>{children}</LabContext.Provider>;
}

export function useLab(): LabContextValue {
  const ctx = useContext(LabContext);
  if (!ctx) throw new Error('useLab must be used inside LabProvider');
  return ctx;
}
