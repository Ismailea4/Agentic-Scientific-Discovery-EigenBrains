import { useCallback, useEffect, useState } from 'react';

export type AppView = 'home' | 'agents' | 'estimation' | 'security' | 'trace';

const ROUTES: Record<string, AppView> = {
  '': 'home',
  home: 'home',
  workspace: 'estimation',
  showcase: 'agents',
  stream: 'trace',
  app: 'agents',
  'app/agents': 'agents',
  'app/estimation': 'estimation',
  'app/security': 'security',
  'app/trace': 'trace',
  agents: 'agents',
  estimation: 'estimation',
  security: 'security',
  trace: 'trace',
};

function parseHash(): AppView {
  const value = window.location.hash.replace(/^#\/?/, '').replace(/\/$/, '');
  return ROUTES[value] ?? 'home';
}

/** Hash routing without an extra dependency. Legacy routes remain aliases. */
export function useHashView(): [AppView, (view: AppView) => void] {
  const [view, setView] = useState<AppView>(parseHash);

  useEffect(() => {
    const onChange = () => setView(parseHash());
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  const navigate = useCallback((next: AppView) => {
    const hash = `#/${next}`;
    if (window.location.hash !== hash) {
      window.location.hash = hash;
    }
    setView(next);
  }, []);

  return [view, navigate];
}
