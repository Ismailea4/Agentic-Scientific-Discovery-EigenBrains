import { useEffect, useState } from 'react';

const QUERY = '(prefers-reduced-motion: reduce), (max-width: 860px)';

function readMatch(): boolean {
  return typeof window !== 'undefined' && window.matchMedia(QUERY).matches;
}

export function useQuietMotion(): boolean {
  const [quiet, setQuiet] = useState(false);

  useEffect(() => {
    const media = window.matchMedia(QUERY);
    setQuiet(readMatch());
    const update = () => setQuiet(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  return quiet;
}
