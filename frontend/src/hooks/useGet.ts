import { useEffect, useState } from 'react';
import { api, ApiError } from '../api/client';

export interface GetState<T> {
  loading: boolean;
  data: T | null;
  error: string | null;
}

export function useGet<T>(path: string): GetState<T> {
  const [state, setState] = useState<GetState<T>>({
    loading: true,
    data: null,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;
    setState({ loading: true, data: null, error: null });
    api
      .get<T>(path)
      .then((data) => {
        if (!cancelled) setState({ loading: false, data, error: null });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof ApiError ? err.message : String(err);
        setState({ loading: false, data: null, error: message });
      });
    return () => {
      cancelled = true;
    };
  }, [path]);

  return state;
}
