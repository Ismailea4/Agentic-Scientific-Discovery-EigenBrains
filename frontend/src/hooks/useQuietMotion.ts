import { useEffect, useState } from 'react';

const QUERY = '(prefers-reduced-motion: reduce), (max-width: 860px)';

function readMatch(): boolean {
  return window.matchMedia(QUERY).matches;
}

export function useQuietMotion(): boolean {
  const [quiet, setQuiet] = useState(readMatch);

  useEffect(() => {
    const media = window.matchMedia(QUERY);
    const update = () => setQuiet(media.matches);
    media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  return quiet;
}
