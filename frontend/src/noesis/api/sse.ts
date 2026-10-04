export interface SSEHandlers {
  /** Called for each event; `data` is JSON.parsed when possible. */
  onEvent: (name: string, data: unknown) => void;
  onError?: (event: Event) => void;
  /** Named events to listen for. Defaults to ['message']. */
  events?: string[];
}

/** Subscribe to a Server-Sent Events endpoint. Returns an unsubscribe
 * function that closes the connection and removes all listeners. */
export function subscribeSSE(path: string, handlers: SSEHandlers): () => void {
  const source = new EventSource(path);
  const names = handlers.events ?? ['message'];

  const makeListener = (name: string) => (event: Event) => {
    const raw = (event as MessageEvent<string>).data;
    let data: unknown = raw;
    try {
      data = JSON.parse(raw);
    } catch {
      // Keep the raw string when the payload is not JSON.
    }
    handlers.onEvent(name, data);
  };

  const listeners = names.map((name) => {
    const listener = makeListener(name);
    source.addEventListener(name, listener);
    return [name, listener] as const;
  });

  const errorListener = handlers.onError;
  if (errorListener) {
    source.addEventListener('error', errorListener);
  }

  return () => {
    for (const [name, listener] of listeners) {
      source.removeEventListener(name, listener);
    }
    if (errorListener) {
      source.removeEventListener('error', errorListener);
    }
    source.close();
  };
}
