import type { ApiErrorBody } from './types';

/** Error thrown for non-2xx API responses, carrying the backend's
 * structured error body ({ error: { code, message, details } }). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody | null, fallbackMessage: string) {
    super(body?.error.message ?? fallbackMessage);
    this.name = 'ApiError';
    this.status = status;
    this.code = body?.error.code ?? 'unknown_error';
    this.details = body?.error.details ?? {};
  }
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null) return false;
  const error = (value as ApiErrorBody).error;
  return (
    typeof error === 'object' &&
    error !== null &&
    typeof error.code === 'string' &&
    typeof error.message === 'string'
  );
}

/** Same-origin request — in dev the Vite proxy forwards /api and /health to
 * the backend. Parses JSON and throws ApiError on non-2xx. */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (cause) {
    throw new ApiError(
      0,
      null,
      `Network error reaching ${path}: ${cause instanceof Error ? cause.message : String(cause)}`,
    );
  }

  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      // Non-JSON response body; leave as null.
    }
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      isApiErrorBody(body) ? body : null,
      `Request to ${path} failed with status ${response.status}`,
    );
  }
  return body as T;
}

export const api = {
  get<T>(path: string, init?: RequestInit): Promise<T> {
    return request<T>(path, { ...init, method: 'GET' });
  },
  post<T>(path: string, data?: unknown, init?: RequestInit): Promise<T> {
    const requestInit: RequestInit = {
      ...init,
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    };
    if (data !== undefined) requestInit.body = JSON.stringify(data);
    return request<T>(path, requestInit);
  },
};
