import { useCallback, useEffect, useState } from 'react';

export type AppView = 'home' | 'discovery' | 'hypotheses' | 'approval' | 'record';

const ROUTES: Record<string, AppView> = {
  '': 'home',
  home: 'home',
  workspace: 'hypotheses',
  showcase: 'discovery',
  stream: 'record',
  app: 'discovery',
  'app/discovery': 'discovery',
  'app/hypotheses': 'hypotheses',
  'app/approval': 'approval',
  'app/record': 'record',
  discovery: 'discovery',
  hypotheses: 'hypotheses',
  approval: 'approval',
  record: 'record',
};

function parseHash(): AppView {
  if (typeof window === 'undefined') return 'home';
  const value = window.location.hash.replace(/^#\/?/, '').replace(/\/$/, '');
  return ROUTES[value] ?? 'home';
}

/** Hash routing without an extra dependency. Legacy routes remain aliases. */
export function useHashView(): [AppView, (view: AppView) => void] {
  const [view, setView] = useState<AppView>('home');

  useEffect(() => {
    setView(parseHash());
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
